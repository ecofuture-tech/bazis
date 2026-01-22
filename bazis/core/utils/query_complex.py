"""
Module for parsing complex query strings into Django ORM Q objects.
Provides functionality to handle logical operators (AND, OR), negations,
and nested conditions.

Tags: RAG, EXPORT
"""

import copy
import dataclasses
import operator
from enum import Enum
from functools import reduce
from hashlib import md5
from itertools import chain
from typing import Union
from urllib.parse import unquote, urlencode

from django.contrib.gis.db.models import PointField
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.contrib.postgres.fields import ArrayField, RangeField
from django.db import models
from django.db.models import Exists, Q, QuerySet
from django.db.models.constants import LOOKUP_SEP
from django.utils.dateparse import parse_date, parse_datetime

from bazis.core.models_abstract import InitialBase
from bazis.core.utils.functools import get_attr
from bazis.core.utils.model_meta import FieldsInfo
from bazis.core.utils.orm import apply_calc_queryset, calc_cached_property


OP_NEG = '~'
SEARCH_TERM = '$search'
RANGE_SUFFIX = {'gt', 'gte', 'lt', 'lte'}
BOOL_SUFFIX = {'isnull'}
BOOLS = {
    'true': True,
    '1': True,
    '': False,
    'false': False,
    '0': False,
    True: True,
    False: False,
}
BOOLS_NEG = {k for k, v in BOOLS.items() if v is False}
NULL = 'null'

LOOKUP_PREFIXES: dict[str, str] = {
    '^': 'istartswith',
    '=': 'iexact',
    '@': 'search',
    '$': 'iregex',
}

DJANGO_SEARCH_FIELDS = [
    models.CharField,
    models.TextField,
    models.IntegerField,
]


class QueryOp(Enum):
    AND = 'and'
    OR = 'or'


@dataclasses.dataclass
class FieldDummy:
    name: str
    model: type[models.Model] = None
    related_model: type[models.Model] = None


# QueryComplexItem = namedtuple('QueryComplexItem', ['key', 'value', 'is_neg'])


class QueryComplexExpression:
    """Represents a set of QueryComplexItems, logical operators (AND, OR) and QueryComplexExpression."""

    is_neg: bool
    conditions_set: list['QueryComplexItem | QueryComplexExpression | QueryOp']

    def __init__(
        self,
        conditions_set: list['QueryComplexItem | QueryComplexExpression | QueryOp'],
        is_neg: bool = False,
    ) -> None:
        """
        Initializes a QueryComplexExpression with a set of conditions.

        :param conditions_set: A set of QueryComplexItems, QueryComplexExpression, or QueryOps.
        :param is_neg: Indicates whether the condition set is negated.
        """
        self.is_neg = is_neg
        self.conditions_set = conditions_set

    def __str__(self) -> str:
        """
        Returns a string representation of the conditions set.

        :return: A formatted string containing the conditions.
        """
        return f'QueryComplexExpression({self.conditions_set}, is_neg={self.is_neg})'

    __repr__ = __str__


class QueryComplexItem:
    """Represents a single query condition consisting of a key-value pair."""

    is_neg: bool
    key: str
    value: str
    parent: 'QueryComplex | None'

    def __init__(
        self, key: str, value: str, is_neg: bool = False, parent: 'QueryComplex | None' = None
    ) -> None:
        """
        Initializes a QueryComplexItem with a key, value, and optional negation.

        :param is_neg: Indicates whether the condition is negated.
        :param key: The field name of the query condition.
        :param value: The corresponding value of the condition.
        :param parent: The parent QueryComplex instance, if applicable.
        """
        self.is_neg = is_neg
        self.key = key
        self.value = value
        self.parent = parent

    def __hash__(self):
        return int(md5(str(self).encode()).hexdigest(), 16)

    def __eq__(self, other):
        return type(self) is type(other) and hash(self) == hash(other)

    def __str__(self):
        return urlencode({self.key: self.value}) + f'?{self.is_neg}'

    def __deepcopy__(self, memo):
        return QueryComplexItem(key=self.key, value=self.value, is_neg=self.is_neg)

    __repr__ = __str__

    def delete(self):
        self.parent.remove(self)

    def replace(self, key: str, value: str, is_neg: bool = False):
        self.key = key
        self.value = value
        self.is_neg = is_neg
        self.parent.rebalanced()

    def add_node(self, node: Union[str, dict, 'QueryComplex'], op: QueryOp):
        if isinstance(node, str | dict):
            node = QueryComplex.from_data(node)

        # if node has only one condition
        if not node.right:
            node = node.left

        current_parent = self.parent
        node_union = QueryComplex(left=self, right=node, op=op, parent=current_parent)

        if current_parent.left == self:
            current_parent.set_left(node_union)
        else:
            current_parent.set_right(node_union)

        next_node = current_parent
        while parent := next_node.parent:
            parent.rebalanced()
            next_node = parent
        return node_union

    def __and__(self, new: Union[str, dict, 'QueryComplexItem', 'QueryComplex']):
        """
        Overloads the & operator to add a condition using 'and'.
        """
        return self.add_node(new, QueryOp.AND)

    def __or__(self, new: Union[str, dict, 'QueryComplexItem', 'QueryComplex']):
        """
        Overloads the | operator to add a condition using 'or'.
        """
        return self.add_node(new, QueryOp.OR)


class QueryComplex:
    parent: Union['QueryComplex', type[None]] = None
    right: Union['QueryComplex', QueryComplexItem, type[None]] = None
    op: QueryOp | type[None] = None
    left: Union['QueryComplex', QueryComplexItem, type[None]] = None
    is_neg: bool = False

    _hash = None
    _dict = {}

    @classmethod
    def _parse_query(cls, query: str) -> QueryComplexExpression:
        """
        Parses the query string containing conditions with logical operators and nesting,
        and converts it into a QueryComplexExpression object.
        """
        query = query.replace('[', '(').replace(']', ')')
        query = query.replace('|&', '|').replace('&|', '|')

        struct = {
            'conditions': QueryComplexExpression(conditions_set=[], is_neg=False),
            'stack': [],
            'key': '',
            'value': None,
            'is_neg': False,
        }
        struct['stack'].append(struct['conditions'])

        def add_cond() -> None:
            """
            If the key and value variables are set, creates a QueryComplexItem with the given is_neg flag
            and appends it to conditions.conditions_set.
            """
            if struct['key'] and struct['value'] is not None:
                struct['conditions'].conditions_set.append(
                    QueryComplexItem(
                        key=struct['key'].strip(),
                        value=unquote(struct['value']).strip().replace('"', '').replace("'", ''),
                        is_neg=struct['is_neg'],
                    )
                )
            struct['key'] = ''
            struct['value'] = None
            struct['is_neg'] = False

        def add_op(op) -> None:
            """
            Appends the operator (AND/OR).
            """
            struct['conditions'].conditions_set.append(op)

        def add_neg() -> None:
            """
            Sets is_neg to True, indicating that the next condition should be negated.
            """
            struct['is_neg'] = True

        def open_nested() -> None:
            """
            Creates a new QueryComplexExpression for nested conditions and pushes it onto the stack.
            """
            struct['conditions'] = QueryComplexExpression(
                conditions_set=[], is_neg=struct['is_neg']
            )
            struct['stack'].append(struct['conditions'])

        def close_nested() -> None:
            """
            Pops the last nested level from the stack and appends it to the parent's conditions_set.
            """
            nested = struct['stack'].pop()
            struct['conditions'] = struct['stack'][-1]
            struct['conditions'].conditions_set.append(nested)

        for ch in query:
            if ch == '&':
                add_cond()
                add_op(QueryOp.AND)
            elif ch == '|':
                add_cond()
                add_op(QueryOp.OR)
            elif ch == OP_NEG:
                add_neg()
            elif ch == '(':
                open_nested()
                add_cond()
            elif ch == ')':
                add_cond()
                close_nested()
            elif ch == '=':
                struct['value'] = ''
            elif struct['value'] is not None:
                struct['value'] += ch
            else:
                struct['key'] += ch
        else:
            add_cond()

        return struct['conditions']

    @classmethod
    def from_data(cls, data: str | dict) -> Union['QueryComplex', QueryComplexItem]:
        def get_condition_pairs(conditions: QueryComplexExpression) -> QueryComplexExpression:
            """Splits a list of conditions into nested condition pairs for further processing in QueryComplex."""
            pair = []

            for condition in conditions.conditions_set:
                if isinstance(condition, QueryComplexExpression):
                    condition = get_condition_pairs(condition)

                if len(pair) < 3:
                    pair.append(condition)
                else:
                    pair = [pair, condition]

            return QueryComplexExpression(conditions_set=pair, is_neg=conditions.is_neg)

        def make_query_complex(
            conditions: QueryComplexExpression,
        ) -> QueryComplex | QueryComplexItem | None:
            """Constructs a QueryComplex object from a conditions_hierarchy of conditions."""
            if isinstance(conditions, QueryComplexItem) or conditions is None:
                return conditions
            elif isinstance(conditions, QueryComplexExpression):
                is_neg = conditions.is_neg
                conditions_set = conditions.conditions_set
            elif isinstance(conditions, list):
                is_neg = False
                conditions_set = conditions

            left, op, right = (conditions_set + [None] * 3)[:3]
            assert op is None or op in QueryOp

            left = make_query_complex(left)
            right = make_query_complex(right)

            return QueryComplex(left=left, right=right, op=op, is_neg=is_neg)

        if isinstance(data, dict):
            data = {k: ','.join(v) if isinstance(v, list | tuple) else v for k, v in data.items()}
            data = urlencode(data)

        parsed_conditions = cls._parse_query(data)
        splited_conditions = get_condition_pairs(conditions=parsed_conditions)
        query_complex = make_query_complex(conditions=splited_conditions)
        return query_complex

    def __init__(
        self,
        left: Union['QueryComplex', QueryComplexItem] = None,
        right: Union['QueryComplex', QueryComplexItem] = None,
        op: QueryOp = None,
        parent: 'QueryComplex' = None,
        is_neg=False,
    ):
        self.left = left
        self.right = right
        self.op = op
        self.parent = parent
        self.is_neg = is_neg
        self.rebalanced()

    def __hash__(self):
        return self._hash or 0

    def __bool__(self):
        return bool(self.left or self.right)

    def __deepcopy__(self, memo):
        def _query_perform(query: QueryComplex, parent: QueryComplex | None):
            left = query.left
            right = query.right
            return QueryComplex(
                left=(
                    _query_perform(left, query)
                    if isinstance(left, QueryComplex)
                    else copy.deepcopy(left)
                ),
                op=query.op,
                right=(
                    _query_perform(right, query)
                    if isinstance(right, QueryComplex)
                    else copy.deepcopy(right)
                ),
                parent=parent,
                is_neg=query.is_neg,
            )

        return _query_perform(self, None)

    def rebalanced(self):
        if not self.left and not self.right:
            self.op = None
            self.parent = None
            self.is_neg = False
            self._hash = None
            return

        if self.left and self.right:
            pair = sorted([self.left, self.right], key=lambda x: hash(x))
        elif self.left:
            pair = [self.left, None]
            self.op = None
        else:
            pair = [self.right, None]
            self.op = None

        self.left = pair[0]
        self.right = pair[1]

        if self.left:
            self.left.parent = self
        if self.right:
            self.right.parent = self

        left_hash = '0' if self.left is None else hash(self.left)
        op_value = '' if self.op is None else self.op.value
        right_hash = '0' if self.right is None else hash(self.right)

        self._hash = int(md5(f'{left_hash}.{op_value}.{right_hash}'.encode()).hexdigest(), 16)

    def set_left(self, node: Union['QueryComplex', QueryComplexItem]):
        self.left = node
        self.rebalanced()

    def set_right(self, node: Union['QueryComplex', QueryComplexItem]):
        self.right = node
        self.rebalanced()

    def add_node(self, node: Union[str, dict, 'QueryComplex'], op: QueryOp):
        if isinstance(node, str | dict):
            node = QueryComplex.from_data(node)

        # for cases when the structure is either empty, has only one element, or has no parent
        if not self:
            self.left = node.left
            self.right = node.right
            self.op = node.op
            self.is_neg = node.is_neg
            self.rebalanced()
            return self
        elif not self.right:
            self.right = node
            self.op = op
            self.rebalanced()
            return self
        elif not self.parent:
            self.left = QueryComplex(
                left=self.left, right=self.right, op=self.op, is_neg=self.is_neg, parent=self
            )
            self.right = node
            self.op = op
            self.is_neg = node.is_neg
            self.rebalanced()
            return self

        # if node has only one condition
        if not node.right:
            node = node.left

        current_parent = self.parent
        node_union = QueryComplex(left=self, right=node, op=op, parent=current_parent)

        if current_parent.left == self:
            current_parent.set_left(node_union)
        else:
            current_parent.set_right(node_union)

        next_node = current_parent
        while parent := next_node.parent:
            parent.rebalanced()
            next_node = parent
        return node_union

    def __and__(self, new: Union[str, dict, QueryComplexItem, 'QueryComplex']):
        """
        Overloads the & operator to add a condition using 'and'.
        """
        obj = copy.deepcopy(self)
        return obj.add_node(new, QueryOp.AND)

    def __iadd__(self, new: Union[str, dict, QueryComplexItem, 'QueryComplex']):
        """
        Overloads the += operator to add a condition using 'and'.
        """
        return self.add_node(new, QueryOp.AND)

    def __or__(self, new: Union[str, dict, QueryComplexItem, 'QueryComplex']):
        """
        Overloads the | operator to add a condition using 'or'.
        """
        obj = copy.deepcopy(self)
        return obj.add_node(new, QueryOp.OR)

    def __ior__(self, new: Union[str, dict, QueryComplexItem, 'QueryComplex']):
        """
        Overloads the |= operator to add a condition using 'or'.
        """
        return self.add_node(new, QueryOp.OR)

    def remove(self, node: Union[QueryComplexItem, 'QueryComplex']):
        """
        Removes a condition from the internal structure.
        """
        if hash(node) not in (hash(self.left), hash(self.right)):
            raise ValueError('Node not found in the structure.')

        if hash(self.left) == hash(node):
            alive = self.right
        else:
            alive = self.left

        if self.parent:
            if self == self.parent.left:
                self.parent.set_left(alive)
            else:
                self.parent.set_right(alive)

            next_node = self.parent
            while parent := next_node.parent:
                parent.rebalanced()
                next_node = parent
        elif alive:
            self.left = alive
            self.right = None
            self.rebalanced()
        else:
            self.left = None
            self.right = None
            self.rebalanced()

        return alive or self

    def dump(self):
        """
        Converts the internal structure to a dictionary for easier visualization.
        """

        def _query_perform(query: QueryComplex):
            left = query.left
            right = query.right
            return [
                _query_perform(left) if isinstance(left, QueryComplex) else left,
                query.op.value if query.op else None,
                _query_perform(right) if isinstance(right, QueryComplex) else right,
            ]

        return _query_perform(self)

    # def _to_dict(self):
    #     """
    #     Transforms the structure to the desired dictionary format.
    #     """
    #     result = defaultdict(list)
    #
    #     def transform_structure(conditions=None, prefix=None, op=QueryOp.AND):
    #         if conditions is None:
    #             conditions = self
    #
    #         nested_count = 0
    #
    #         for cond in conditions:
    #             if isinstance(cond, QueryComplexItem):
    #                 full_key = ['', op.value]
    #                 if prefix:
    #                     full_key.append(prefix)
    #                 full_key.append(cond.key)
    #                 if cond.is_neg:
    #                     full_key.append('is_neg')
    #                 result['__'.join(full_key)].append(cond.value)
    #             elif cond in QueryOp:
    #                 op = cond
    #             elif isinstance(cond, QueryComplex):
    #                 nested_prefix = []
    #                 if prefix:
    #                     nested_prefix.append(prefix)
    #                 nested_prefix.append(f'{nested_count}')
    #                 nested_count += 1
    #                 transform_structure(cond, '__'.join(nested_prefix), op)
    #
    #     transform_structure()
    #     self._dict = result

    # def __getitem__(self, item):
    #     return self._dict[item]
    #
    # def keys(self):
    #     return self._dict.keys()


class QueryToOrm:
    q: Q
    fields_calc: list

    @classmethod
    def qs_apply(
        cls,
        queryset: QuerySet,
        query_complex: QueryComplex | str,
        filters_aliases: dict[str, str] = None,
        fiter_context: dict = None,
    ):
        """
        Applies the filtering logic to the given QuerySet based on the provided query string,
        filter aliases, and context.

        :param queryset: The Django QuerySet to filter.
        :param query_complex: The query string to parse and apply as filters.
        :param filters_aliases: Optional dictionary mapping filter aliases to actual field names.
        :param fiter_context: Optional context dictionary for additional filtering logic.
        :return: Filtered QuerySet.
        """
        if not query_complex:
            return queryset

        q_orm = cls(query_complex, queryset.model, filters_aliases, fiter_context)
        if q_orm.fields_calc:
            queryset = apply_calc_queryset(queryset, q_orm.fields_calc, context=fiter_context)
        queryset = queryset.filter(q_orm.q)
        return queryset

    def __init__(
        self,
        query_complex: QueryComplex | str,
        model: type[models.Model],
        filters_aliases: dict[str, str] = None,
        fiter_context: dict = None,
    ):
        """
        Initializes the Filtering instance with the model, query string, filter aliases, and context.

        :param model: The Django model to filter.
        :param query_str: The query string to parse and apply as filters.
        :param filters_aliases: Optional dictionary mapping filter aliases to actual field names.
        :param fiter_context: Optional context dictionary for additional filtering logic.
        """
        if isinstance(query_complex, str):
            query_complex = QueryComplex.from_data(query_complex)

        self.model = model
        self.query_complex = query_complex
        self.filters_aliases = filters_aliases or {}
        self.fiter_context = fiter_context or {}
        self.q, self.fields_calc = self._query_perform(self.query_complex)

    def _query_perform(self, query: QueryComplex):
        fields_calc = []
        q_result = []
        q = Q()

        if not query:
            return q, fields_calc

        for node in (query.left, query.right):
            if not node:
                q_result.append(Q())
                continue

            if isinstance(node, QueryComplexItem):
                q, sub_fields_calc = self._lookup_parse(node.key, node.value)
                fields_calc.extend(sub_fields_calc)
            else:
                q, sub_fields_calc = self._query_perform(node)
                fields_calc.extend(sub_fields_calc)

            if node.is_neg:
                q = ~q

            q_result.append(q)

        if query.op == QueryOp.AND:
            q = q_result[0] & q_result[1]
        else:
            q = q_result[0] | q_result[1]

        return q, fields_calc

    def _lookup_parse(self, key: str, value: str):
        """
        Parses the lookup key and value, and applies the appropriate filters to the model.

        :param key: The lookup key (e.g., 'author__name').
        :param value: The value to filter by.
        :return: A tuple containing the Q object and fields calculation list.
        """
        params = key.split(LOOKUP_SEP)
        params = list(chain(*[self.filters_aliases.get(p, p).split(LOOKUP_SEP) for p in params]))
        return self._filters_apply(params, value, self.model)

    def _filters_apply(self, params, value, model):
        """
        Applies the filters based on the parsed parameters and value to the specified model.

        :param params: List of parameters derived from the lookup key.
        :param value: The value to filter by.
        :param model: The Django model to filter.
        :return: A tuple containing the Q object and fields calculation list.
        """
        queries = [Q(), []]

        fields_info = FieldsInfo.get_fields_info(model)
        param, *params = params

        def queries_add(_q, _f=None):
            """
            Adds the given Q object and fields to the current queries list.

            :param _q: The Q object to add.
            :param _f: The fields to add.
            """
            queries[0] &= _q
            if _f:
                queries[1].extend(_f)

        if '.' in param:
            q = self._filter_by_type(param, value, model)
            if q:
                queries_add(q)

        if field_info := fields_info.fields.get(param):
            if params and param in fields_info.relations:
                queries_add(self._filters_apply_relation(params, value, field_info))
            else:
                queries_add(self._filters_apply_native(params, value, field_info))
        elif param == SEARCH_TERM and value:
            queries_add(self._filters_apply_search(model, value))
        elif func_calc := get_attr(model, param):
            if isinstance(func_calc, calc_cached_property) and func_calc.as_filter:
                if func_calc.response_type is bool or value in ('true', 'false'):
                    value = BOOLS.get(value)

                type_calc = func_calc.filter_field or FieldDummy

                type_obj = type_calc(name=param)
                type_obj.model = model

                queries_add(
                    self._filters_apply_native(params, value, type_obj), func_calc.fields_calc
                )

        return queries

    def _filter_by_type(self, model_label, ids, target_model):
        source_model = InitialBase.get_model_by_label(model_label)
        if not source_model:
            return None

        ids = ids.split(',')

        q = Q()
        rels = source_model.get_fields_info().relations_by_model[target_model]
        for rel in rels:
            q |= Q(**{f'{rel.related_field.name}__in': ids})

        return q

    def _filters_apply_relation(self, params, value, field_info):
        """
        Applies filters to a related model field and constructs an Exists subquery.

        :param params: List of parameters derived from the lookup key.
        :param value: The value to filter by.
        :param field_info: Field information for the related model.
        :return: An Exists subquery representing the filter condition.
        """
        exists_qs = field_info.get_subqueryset()
        q, fields_calc = self._filters_apply(params, value, exists_qs.model)
        if fields_calc:
            exists_qs = apply_calc_queryset(exists_qs, fields_calc, context=self.fiter_context)

        # expression of the existence of a nested query
        exists_qs = Exists(exists_qs.filter(q).values('id'))

        # if the query contains an existence expression - handle it separately
        if 'exists' == params[0]:
            if value in BOOLS_NEG:
                exists_qs = ~exists_qs

        return exists_qs

    def _filters_apply_native(self, params, value, field):
        """
        For the final value, perform null conversion and apply the appropriate filter based on
        the field type.

        :param params: list of parameters derived from the lookup key.
        :param value: the value to filter by.
        :param field: the model field to apply the filter to.
        :return: a q object representing the filter condition.
        """
        if value == NULL or (
            value == '' and not isinstance(field, models.CharField | models.TextField)
        ):
            value = None

        if isinstance(field, PointField):
            func = self._func_geo
        elif isinstance(field, RangeField):
            func = self._func_range
        elif isinstance(field, models.BooleanField):
            func = self._func_bool
        elif isinstance(field, ArrayField):
            func = self._func_overlap
        elif isinstance(field, models.TextField):
            func = self._func_text
        else:
            func = self._func_exact

        return func(value, params, field)

    def _filters_apply_search(self, model, value, field_name=None):
        """
        Applies full-text search filters to the specified model based on the given value and
        optional field name.

        :param model: The Django model to filter.
        :param value: The search value.
        :param field_name: Optional field name to restrict the search to.
        :return: A Q object representing the search condition.
        """
        search = SearchToOrm(model, value, [field_name] if field_name else None)
        return search.q

    def _func_exact(self, value, params, field):
        """
        Applies exact match filters to the specified field based on the given value and parameters.

        :param value: The value to filter by.
        :param params: List of parameters derived from the lookup key.
        :param field: The model field to apply the filter to.
        :return: A Q object representing the filter condition.
        """
        if action := get_attr(params, 0):
            if action in RANGE_SUFFIX:
                return Q(**{f'{field.name}__{action}': value})
            if action in LOOKUP_PREFIXES.values():
                field_name = f'{field.name}__{action}'
                return self._filters_apply_search(field.model, value, field_name)
            if action == SEARCH_TERM:
                return self._filters_apply_search(field.model, value, field.name)
            if action in BOOL_SUFFIX:
                return self._func_bool(value, params, field)
        if isinstance(value, list | set | tuple):
            return Q(**{f'{field.name}__in': value})
        return Q(**{field.name: value})

    def _func_geo(self, value, params, field):
        """
        Applies geographic filters to the specified field based on the given value and parameters.

                Supported filters:
                - point=49.124,55.76480
                - point__near=49.124,55.76480[,100]
                - point__in_bbox=160.6,-55.95,-170,-25.89

                :param value: The geographic value to filter by.
                :param params: List of parameters derived from the lookup key.
                :param field: The geographic model field to apply the filter to.
                :return: A Q object representing the geographic filter condition.
        """
        # TODO: implement full geojson support, handle finding the nearest object,
        # inclusion in the object, etc.

        def point_near(lon, lat, distance=10):
            """
            Creates a geo-point and searches for objects within a specified radius from the target point.

            :param lon: longitude of the target point.
            :param lat: latitude of the target point.
            :param distance: radius in meters for the search (default is 10 meters).
            :return: a q object representing the geographic filter condition.
            """
            geo_point = GEOSGeometry(f'POINT({lon} {lat})', srid=4326)
            # search for objects within n-meters radius from the target
            return Q(**{f'{field.name}__distance_lte': (geo_point, distance)})

        def point_in_bbox(bbox):
            """
            Creates a bounding box polygon and searches for objects contained within the specified bounding box.

            :param bbox: List of coordinates defining the bounding box.
            :return: A Q object representing the geographic filter condition.
            """
            bbox_polygon = Polygon.from_bbox(bbox)
            return Q(**{f'{field.name}__contained': bbox_polygon})

        if value:
            if 'in_bbox' in params:
                return point_in_bbox(value.split(','))
            elif 'near' in params:
                lon, lat, *p = value.split(',')
                if p:
                    distance = int(p[0])
                else:
                    distance = 100
                return point_near(lon, lat, distance)
            else:
                lon, lat = value.split(',')
                return point_near(lon, lat, 10)
        return Q()

    def _func_overlap(self, value, params, field):
        """
        Applies overlap filters to the specified field based on the given value and parameters.

        :param value: The value to filter by, as a comma-separated string.
        :param params: List of parameters derived from the lookup key.
        :param field: The array model field to apply the filter to.
        :return: A Q object representing the overlap filter condition.
        """
        if isinstance(value, str):
            values = value.split(',')
        else:
            values = list(value)
        if values:
            if action := get_attr(params, 0):
                return Q(**{f'{field.name}__{action}': values})
            return Q(**{f'{field.name}__overlap': values})
        return Q()

    def _func_range(self, value, params, field):
        """
        Applies range filters to the specified field based on the given value and parameters.

        :param value: The range value to filter by, as a comma-separated string.
        :param params: List of parameters derived from the lookup key.
        :param field: The range model field to apply the filter to.
        :return: A Q object representing the range filter condition.
        """
        if value and params:
            action = params[0]
            if action in RangeField.class_lookups:
                start, end = value.split(',')

                if field.base_field.get_internal_type() == 'DateRangeField':
                    start = parse_date(start)
                    end = parse_date(end)
                elif field.base_field.get_internal_type() == 'DateTimeRangeField':
                    start = parse_datetime(start)
                    end = parse_datetime(end)

                return Q(**{f'{field.name}__{action}': (start, end)})
        return Q()

    def _func_bool(self, value, params, field):
        """
        Applies boolean filters to the specified field based on the given value and parameters.

        :param value: The boolean value to filter by.
        :param params: List of parameters derived from the lookup key.
        :param field: The boolean model field to apply the filter to.
        :return: A Q object representing the boolean filter condition.
        """
        is_true = value not in BOOLS_NEG
        if action := get_attr(params, 0):
            if action in BOOL_SUFFIX:
                return Q(**{f'{field.name}__{action}': is_true})
        return Q(**{field.name: is_true})

    def _func_text(self, value, params, field):
        """
        Applies text search filters to the specified field based on the given value and parameters.

        :param value: The text value to filter by.
        :param params: List of parameters derived from the lookup key.
        :param field: The text model field to apply the filter to.
        :return: A Q object representing the text search filter condition.
        """
        field_name = field.name
        if action := get_attr(params, 0):
            if action in LOOKUP_PREFIXES.values():
                field_name = f'{field_name}__{action}'
        return self._filters_apply_search(field.model, value, field_name)


class SearchToOrm:
    """
    Searching constructs a Q object based on the provided model, search string, and
    search fields. It is used to filter querysets according to the search criteria.
    """

    q: Q

    def __init__(self, model, search, search_fields=None):
        """
        Initializes the Searching class with the model, search string, and optional
        search fields. If no search fields are provided, it defaults to fields of types
        defined in DJANGO_SEARCH_FIELDS.
        """
        self.search = search and search.strip()
        self.search_fields = search_fields or [
            f.name for f in model._meta.get_fields() if type(f) in DJANGO_SEARCH_FIELDS
        ]
        if self.search_fields is None or not self.search:
            self.q = Q()
            return

        terms = self._get_terms()

        orm_lookups = [
            self._construct_search(str(search_field)) for search_field in self.search_fields
        ]

        conditions = []
        for term in terms:
            queries = [models.Q(**{orm_lookup: term}) for orm_lookup in orm_lookups]
            conditions.append(reduce(operator.or_, queries))

        self.q = reduce(operator.and_, conditions)

    def _construct_search(self, field_name):
        """
        Constructs the appropriate search lookup for a given field name. It handles
        field name prefixes and appends the correct lookup type.
        """
        if LOOKUP_SEP in field_name:
            return field_name
        lookup = LOOKUP_PREFIXES.get(field_name[0])
        if lookup:
            field_name = field_name[1:]
        else:
            lookup = 'icontains'
        return LOOKUP_SEP.join([field_name, lookup])

    def _get_terms(self) -> list[str]:
        """
        Splits the search string into individual search terms, removing any null
        characters and replacing commas with spaces.
        """
        search = self.search.replace('\x00', '')  # strip null characters
        search = search.replace(',', ' ')
        return search.split()


# # Example usage
# query_str = "contract__author=__selector__&(label=manager|~label=director|[slug=1&~slug=2]&[moon=1&~moon=2])"
# # query_str = "contract__author=__selector__&(label=manager|~label=director)"
# parser = QueryComplex.from_data(query_str)
# print(parser.dump())
#
# # Adding conditions
# parser &= {'f1': 'v1'}
# parser |= {'f2': 'v2'}
# parser &= {'f2': 'v2'}
#
# print(parser.dump())
#
# parser.left &= {'f3': 'v3'}
# print(parser.dump())
