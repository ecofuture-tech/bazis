# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import dataclasses
import datetime
import decimal
import importlib
import inspect
import json
import logging
import os
from collections.abc import Callable
from copy import deepcopy
from functools import wraps
from hashlib import md5
from typing import Any, get_type_hints

from django.apps import apps
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.postgres.expressions import ArraySubquery
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import FieldDoesNotExist
from django.db import connections, models, router, transaction
from django.db.models import (
    Aggregate,
    Count,
    Exists,
    F,
    ForeignKey,
    Func,
    IntegerField,
    ManyToOneRel,
    Model,
    OneToOneField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.expressions import Expression
from django.db.models.functions import JSONObject
from django.utils.functional import Promise, cached_property
from django.utils.text import capfirst, slugify

from pydantic import BaseModel, create_model

from translated_fields import TranslatedField, to_attribute

from bazis.core.utils.imp import import_class
from bazis.core.utils.model_meta import RelationInfo


logger = logging.getLogger()


def close_old_connections(**kwargs):
    """
    Close all old database connections that are unusable or obsolete, unless inside
    a transaction.

    Tags: RAG, EXPORT
    """
    for conn in connections.all(initialized_only=True):
        # If we are inside a transaction, do not close the connection
        if conn.in_atomic_block:
            continue
        conn.close_if_unusable_or_obsolete()


def get_file_path(instance, filename):
    """
    Generate a file path for the given instance and filename, incorporating a hashed
    version of the filename.

    Tags: RAG, EXPORT
    """
    subpath = instance.__class__.__name__.lower()
    name, ext = os.path.splitext(filename)
    hash_code = md5((settings.SECRET_KEY + name).encode('utf-8')).hexdigest()
    path = os.path.join('files', subpath, hash_code[0], hash_code[1], hash_code[2])
    return os.path.join(path, f'{hash_code[:16]}.{slugify(name, allow_unicode=True)}{ext}')


class CountAll(Func):
    """
    Custom SQL function to count all rows.

    Tags: RAG, EXPORT
    """

    template = 'COUNT(*)'

    def __init__(self):
        """
        Initialize the CountAll function with an output field of IntegerField.
        """
        super().__init__(output_field=IntegerField())


class SumNoGroup(Sum):
    """
    Custom Sum aggregate function that does not require grouping.

    Tags: RAG, EXPORT
    """

    contains_aggregate = False


class CountNoGroup(Count):
    """
    Custom Count aggregate function that does not require grouping.

    Tags: RAG, EXPORT
    """

    contains_aggregate = False


class ArrayCat(Func):
    """
    Custom function for concatenating arrays in PostgreSQL,
    using the "||" operator.

    Tags: RAG, EXPORT
    """

    # We do not set a function name because we use an expression with the "||" operator
    template = '%(expressions)s'

    def __init__(self, *expressions, field_type=None, **extra):
        """
        :param expressions: Expressions (usually ArrayAgg) that need to be concatenated.
        :param field_type: Field type for array elements. IntegerField by default.
        :param extra: Additional keyword arguments.
        """
        if field_type is None:
            field_type = IntegerField()
        super().__init__(*expressions, output_field=ArrayField(field_type), **extra)

    def as_sql(self, compiler, connection, **extra_context):
        sql_parts = []
        params = []
        # Compile each expression and collect SQL parts with parameters
        for expr in self.source_expressions:
            expr_sql, expr_params = compiler.compile(expr)
            sql_parts.append(expr_sql)
            params.extend(expr_params)
        # Join SQL parts using the array concatenation operator "||"
        sql = ' || '.join(sql_parts)
        return sql, params


class UniqueArray(Func):
    """
    A function that takes an SQL expression returning an array
    and returns an array with unique values.

    Generates SQL of the form:
      (SELECT array_agg(DISTINCT x) FROM unnest(<array_expression>) AS x)

    Tags: RAG, EXPORT
    """

    template = '(SELECT array_agg(DISTINCT x) FROM unnest(%(expressions)s) AS x)'

    def __init__(self, expression, **extra):
        """
        :param expression: An expression that returns an array (for example, the result of ArrayCat).
        """
        super().__init__(expression, **extra)

    def get_output_field(self):
        """Use the output_field of the first expression so that the data type matches."""
        return self.source_expressions[0].output_field


def dictfetchall(cursor):
    """
    Return all rows from a cursor as a dictionary.

    Tags: RAG, EXPORT
    """
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def duplicate_clear(model, *args, **kwargs):
    """
    Remove duplicate records from the model based on the specified fields.

    Tags: RAG, EXPORT
    """
    qs = (
        model.objects.values(*args).annotate(all_count=Count('*')).filter(all_count__gt=1, **kwargs)
    )
    # iterate through them, deleting the excess
    for it in qs:
        model.objects.filter(
            id__in=model.objects.filter(**{arg: it[arg] for arg in args}).values_list(
                'id', flat=True
            )[1:]
        ).delete()


def set_related_with_delete(rel, objs, *, bulk=True, clear=False):
    """
    Set related objects for a relationship field, deleting any unlinked related
    objects if the relationship is non-nullable.

    Tags: RAG, EXPORT
    """

    db = router.db_for_write(rel.model, instance=rel.instance)
    with transaction.atomic(using=db, savepoint=False):
        # Determine the manager type by the class name
        manager_class_name = rel.__class__.__name__

        if 'ManyRelatedManager' in manager_class_name:
            # For many-to-many relations bulk is not supported
            rel.set(objs, clear=clear)
        else:
            # For one-to-many relations (ForeignKey) bulk is supported
            rel.set(objs, bulk=bulk, clear=clear)

        # Check the possibility of deleting unlinked objects
        # For ForeignKey we use rel.field.null
        # For ManyToMany the field is always nullable (relation via an intermediate table)
        if hasattr(rel, 'field') and not rel.field.null:
            # This is a ForeignKey with null=False - delete objects that are no longer linked
            rel.using(db).exclude(pk__in=[obj.pk for obj in objs]).delete()
        # For ManyToMany we do not delete anything, objects are just unlinked


def point_create(lon, lat):
    """
    Create a GEOSGeometry point object from the given longitude and latitude.

    Tags: RAG, EXPORT
    """
    return GEOSGeometry(f'POINT({lon} {lat})', srid=4326)


def get_model_field_by_name(model, field_name):
    """
    Retrieve a model field by its name.

    Tags: RAG, EXPORT
    """
    for field in model._meta.get_fields():
        if field.name == field_name:
            return field


def batch_qs(qs, batch_size=1000):
    """
    Returns a tuple (start, end, total, queryset) for each batch in the given queryset.

    Each tuple contains the start and end position in the batch, the total number of records,
    and the queryset for the current batch.

    Example usage::

        # Make sure your queryset is sorted
        article_qs = Article.objects.order_by('id')
        for start, end, total, qs_batch in batch_qs(article_qs):
            print(f"Currently processing {start + 1} - {end} out of {total}")
            for article in qs_batch:
                print(article.body)

    :param qs: QuerySet to be processed.
    :param batch_size: Batch size (default is 1000).

    :return: Generator of tuples (start, end, total, queryset) for each batch.

    Tags: RAG, EXPORT
    """
    total = qs.count()
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        yield start, end, total, qs[start:end]


class JsonFieldEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle additional Python data types such as datetime and
    decimal.

    Tags: RAG, EXPORT
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the JsonFieldEncoder with optional arguments.
        """
        super().__init__(*args, **kwargs)
        self.ensure_ascii = False

    def default(self, obj):
        """
        Override the default method to provide custom serialization for datetime, date,
        time, decimal, and Promise objects.
        """
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.strftime('%Y-%m-%d')
        elif isinstance(obj, datetime.time):
            return obj.strftime('%H:%M:%S')
        elif isinstance(obj, decimal.Decimal):
            return str(obj)
        elif isinstance(obj, Promise):
            return str(obj)
        else:
            return super().default(obj)


def verbose_name(app_model, field=None, cap_first=True):
    """
    Get the verbose name of a field or model.

    Tags: RAG, EXPORT
    """
    if isinstance(app_model, str):
        opts = apps.get_model(app_model, require_ready=False)._meta
    else:
        opts = app_model._meta

    if field is not None:
        if isinstance(field, str):
            verbose_name = opts.get_field(field).verbose_name
        else:
            names = []
            for field_name in field:
                verbose_name = opts.get_field(field_name).verbose_name
                names.append(str(capfirst(verbose_name) if cap_first else verbose_name))
            return names
    else:
        verbose_name = opts.verbose_name

    return capfirst(verbose_name) if cap_first else verbose_name


class AbstractForeignKey:
    """
    This variant of the foreign key can be applied to an abstract class.
    It allows creating models for each model that will inherit from the main abstract class.

    Tags: RAG, EXPORT
    """

    def __init__(self, abstract_model, class_abstract_path=None, related_name=None):
        """
        Initialize the AbstractForeignKey with the abstract model and an optional
        related name.
        """
        self.abstract_model = abstract_model
        self.manager_name = related_name
        self.class_abstract_path = class_abstract_path

    def contribute_to_class(self, cls, name):
        """
        Contribute the foreign key field to the given class.
        """
        self.field_name = name
        self.cls = cls
        self.manager_name = self.manager_name or f'{name}s'
        models.signals.class_prepared.connect(self.finalize, weak=False)

    def finalize(self, sender, **kwargs):
        """
        Finalize the foreign key field for the given model class.

        :param sender: Expected model inherited from the related target abstract model
        :return:
        """
        if not issubclass(sender, self.abstract_model):
            return

        # proxy models do not create their own separate transition model
        if sender._meta.proxy:
            return

        # creating a specific model
        specific_model = self.create_specific_model(sender)
        # set the new model in the target model's module
        module = importlib.import_module(sender.__module__)
        setattr(module, specific_model.__name__, specific_model)

    def create_specific_model(self, target_model):
        """
        Create a concrete model based on the abstract class.

        :param target_model: target abstract class
        :return:
        """
        base_cls = self.cls
        if self.class_abstract_path:
            try:
                base_cls = import_class(self.class_abstract_path)
            except ImportError:
                pass

        return type(
            f'{target_model._meta.object_name}{base_cls._meta.object_name}',
            (base_cls,),
            {
                '__module__': target_model.__module__,
                'Meta': type(
                    'Meta',
                    (),
                    {
                        'verbose_name': (
                            f'{target_model._meta.verbose_name}. {base_cls._meta.verbose_name}'
                        ),
                        'verbose_name_plural': (
                            f'{target_model._meta.verbose_name_plural}. '
                            f'{base_cls._meta.verbose_name_plural}'
                        ),
                    },
                ),
                self.field_name: models.ForeignKey(
                    target_model, related_name=self.manager_name, on_delete=models.CASCADE
                ),
            },
        )


@dataclasses.dataclass
class FieldCalc:
    """
    Data class representing a field calculation.

    Tags: RAG, EXPORT
    """

    source: str
    query: Q | Expression = None
    alias: str = None
    context: list[str] = None

    def is_similar(self, other: 'FieldCalc'):
        """
        Check if this FieldCalc is similar to another FieldCalc.
        """
        if type(self) is type(other) and self.source == other.source and self.query == other.query:
            return True
        return False


@dataclasses.dataclass
class FieldRelated(FieldCalc):
    """
    Data class representing a related field calculation.

    Tags: RAG, EXPORT
    """

    nested: list['FieldCalc'] = dataclasses.field(default_factory=list)
    filter_fn: Callable[[QuerySet, dict], QuerySet] = None

    def is_similar(self, other: 'FieldRelated'):
        """
        Check if this FieldRelated is similar to another FieldRelated.
        """
        if super().is_similar(other) and self.filter_fn == other.filter_fn:
            return True
        return False

    def union(self, other: 'FieldRelated'):
        """
        Union this FieldRelated with another FieldRelated.
        """
        self.nested.extend(other.nested)


@dataclasses.dataclass
class FieldAnnotate(FieldCalc):
    """
    Data class representing an annotated field calculation.

    Tags: RAG, EXPORT
    """

    output_field: type[models.Field] = None
    ...


@dataclasses.dataclass
class FieldSubquery(FieldAnnotate):
    """
    Data class representing a subquery field calculation.

    Tags: RAG, EXPORT
    """

    filter_fn: Callable[[QuerySet, dict], QuerySet] = None


@dataclasses.dataclass
class FieldAggr(FieldAnnotate):
    """
    Data class representing an aggregate field calculation.

    Tags: RAG, EXPORT
    """

    func: type[Func] = None
    distinct: bool = False


@dataclasses.dataclass
class FieldIsExists(FieldSubquery):
    """
    Data class representing an existence check field calculation.

    Tags: RAG, EXPORT
    """

    nested: list['FieldSubquery'] = dataclasses.field(default_factory=list)
    is_invert = False

    def __invert__(self):
        """
        Inverts the condition of the FieldIsExists instance, toggling the is_invert
        flag.
        """
        self.is_invert = True
        return self


@dataclasses.dataclass
class FieldValues(FieldSubquery):
    """
    Represents a field that uses a subquery to fetch values, with optional nested
    subqueries.

    Tags: RAG, EXPORT
    """

    nested: list['FieldSubquery'] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class FieldSubAggr(FieldSubquery):
    """
    Represents a field that uses a subquery with an aggregation function.

    Tags: RAG, EXPORT
    """

    func: str = None
    distinct: bool = False


@dataclasses.dataclass
class FieldJson(FieldRelated, FieldSubquery):
    """
    Represents a field that uses a subquery to fetch JSON data, with optional nested
    subqueries and additional fields.

    Tags: RAG, EXPORT
    """

    fields: list[str] = dataclasses.field(default_factory=list)
    slice: slice = None
    order_by: list[str] = None

    def __post_init__(self):
        """
        Initializes the FieldJson instance, setting a default alias if one is not
        provided.
        """
        if not self.alias:
            self.alias = f'_{self.source}'

    def is_similar(self, other: 'FieldJson'):
        """
        Check if this FieldRelated is similar to another FieldRelated.
        """
        if (
            super().is_similar(other)
            and self.slice == other.slice
            and self.order_by == other.order_by
        ):
            return True
        return False

    def union(self, other: 'FieldJson'):
        """
        Union this FieldJson with another FieldJson.
        """
        super().union(other)
        if self.fields:
            self.fields.extend(other.fields)
        elif other.fields:
            self.fields = list(other.fields)


@dataclasses.dataclass
class FieldDynamic:
    """
    Flexible field builder with `nested()` and automatic forwarding into `Field*` classes.

    Tags: RAG, EXPORT
    """

    source: str | None = None
    alias: str | None = None
    query: Q | Expression | None = None
    fields: list[str] = dataclasses.field(default_factory=list)
    nested: list['FieldDynamic', 'FieldCalc'] = dataclasses.field(default_factory=list)
    context: list[str] | None = None
    func: Aggregate | None = None
    is_invert: bool = False
    slice: slice = None
    order_by: list[str] = None
    filter_fn: Callable[[QuerySet, dict], QuerySet] = None

    def _detect_type(
        self,
    ) -> FieldJson | FieldRelated | FieldAggr | FieldIsExists | FieldValues | FieldSubAggr:
        """Determines the field type and forwards `nested` into the appropriate `Field*` class."""

        # If `alias` starts with `has_` -> FieldIsExists
        if self.alias and self.alias.startswith('has_'):
            return FieldIsExists(
                source=self.source,
                alias=self.alias,
                query=self.query,
                context=self.context,
                nested=(
                    [n() if isinstance(n, FieldDynamic) else n for n in self.nested]
                    if self.nested
                    else []
                ),
            )
        # If `func` is set, then depending on the function type -> FieldSubAggr or FieldAggr
        if self.func:
            return FieldSubAggr(
                source=self.source,
                alias=self.alias,
                func=self.func,
                query=self.query,
                context=self.context,
            )
        # If `fields` -> FieldJson
        if self.fields:
            return FieldJson(
                source=self.source,
                alias=self.alias,
                context=self.context,
                fields=self.fields,
                slice=self.slice,
                order_by=self.order_by,
                filter_fn=self.filter_fn,
                nested=(
                    [n() if isinstance(n, FieldDynamic) else n for n in self.nested]
                    if self.nested
                    else []
                ),
                query=self.query,
            )
        # Otherwise FieldRelated
        return FieldRelated(
            source=self.source,
            alias=self.alias,
            context=self.context,
            filter_fn=self.filter_fn,
            nested=(
                [n() if isinstance(n, FieldDynamic) else n for n in self.nested]
                if self.nested
                else []
            ),
        )

    def add_nested(self, fields: list['FieldDynamic']) -> 'FieldDynamic':
        """Converts nested `FieldDynamic` into the required classes."""
        self.nested = fields
        return self

    def __call__(self):
        """Automatically turns into the required `Field*` class and checks `source`."""
        return self._detect_type()


class calc_cached_property(cached_property):  # noqa: N801
    """
    A cached property decorator that supports field calculations and optional
    filtering.

    Tags: RAG, EXPORT
    """

    fields_calc: list[FieldCalc] = []
    as_filter: bool = False
    filter_field: type = None
    response_type: type = None

    # def __set_name__(self, owner, name):
    #     super().__set_name__(owner, name)
    #
    #     # check the new parameter for compatibility with the existing ones
    #     for field_calc in self.fields_calc:
    #         alias = field_calc.alias or field_calc.source
    #
    #         for cl in owner.mro():
    #             if hasattr(cl, '_fields_calc'):
    #                 if last_calc := cl._fields_calc.get(alias):
    #                     if not field_calc.is_similar(last_calc):
    #                         raise Exception(f'Field {field_calc.source} is not similar to {last_calc.source}')
    #
    #         owner._fields_calc[alias] = field_calc


def _fields_related_normalize(fields_calc: list[FieldCalc | str | Callable[[], FieldCalc]]):
    """
    Normalizes a list of field calculations FieldRelated and FieldJSON (child), separating related fields and other
    fields, and handling nested structures.

    Tags: RAG, EXPORT
    """
    fields_related = []
    fields_other = []
    fields_related_new = []

    for it in fields_calc:
        if isinstance(it, FieldRelated):
            fields_related.append(it)
        else:
            fields_other.append(it)

    for field_related in fields_related:
        parts = field_related.source.replace('.', '__').split('__')

        f_next: FieldRelated | None = None
        f_prev: FieldRelated | None = None

        for _i, p in enumerate(parts, 1):
            f_next = type(field_related)(source=p)

            if f_prev:
                f_prev.nested.append(f_next)

                if isinstance(f_prev, FieldJson):
                    f_prev.fields.append(f_next.alias)
            else:
                fields_related_new.append(f_next)

            f_prev = f_next

        if f_next:
            f_next.alias = field_related.alias
            f_next.query = field_related.query
            f_next.filter_fn = field_related.filter_fn
            f_next.context = field_related.context
            if isinstance(field_related, FieldJson):
                f_next.fields = field_related.fields
                f_next.slice = field_related.slice
                f_next.order_by = field_related.order_by

        if field_related.nested:
            f_next.nested.extend(_fields_related_normalize(field_related.nested))
            if isinstance(field_related, FieldJson):
                f_next.fields.extend(list(set([f.alias for f in f_next.nested])))

    return fields_related_new + fields_other


class DependsCalc(BaseModel):
    """
    Analog of FastAPI Depends, but for passing calc_field_data into methods via @calc_property.

    Tags: RAG, EXPORT
    """

    data: list[BaseModel] | None = None

    def build_calc_field_data(self, instance, fields, name='DependsCalc_data') -> None:
        """
        Converts an object with attributes into a Pydantic model, excluding `_` in field names.
        """
        calc_field_data = {}

        def add_values(value):
            """Recursively converts nested data."""
            if isinstance(value, list):
                if value and isinstance(value[0], dict):
                    return [add_values(v) for v in value]
                return value
            if isinstance(value, dict):
                return {k.lstrip('_'): add_values(v) for k, v in value.items()}
            return value

        for field in fields:
            field_name = field.source.lstrip('_')
            if type(field) is FieldRelated:
                if field.source in instance._state.fields_cache:
                    value = getattr(instance, field_name)
                else:
                    value = None
            else:
                value = getattr(instance, f'_{field.source}', None)
            calc_field_data[field_name] = add_values(value)

        self.data = self._to_pydantic(calc_field_data, name)

    def _to_pydantic(
        self, data: dict[str, Any] | list[dict[str, Any]] | Model, name='DependsCalc_data'
    ) -> (BaseModel | list[BaseModel]) | Model:
        """
        Converts an instance of calc_field_data into a dynamic Pydantic model.
        """
        if isinstance(data, list):
            if data and isinstance(data[0], dict):
                nested_model = self._create_pydantic_model(name, data[0])
                return [nested_model(**item) for item in data]
            return data

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, Model):
                    data[key] = self._to_pydantic(value)
            model_type = self._create_pydantic_model(name, data)
            return model_type(**data)

        if isinstance(data, Model):
            converted_value = data.dict_data
            fields_cached = data._state.fields_cache
            for field in data._meta.get_fields():
                if isinstance(field, models.ForeignKey):
                    if field.name in fields_cached:
                        converted_value[field.name] = self._to_pydantic(
                            getattr(data, f'{field.name}')
                        )
            return converted_value

        return data

    def _create_pydantic_model(self, name: str, fields: dict[str, Any]) -> BaseModel:
        """
        Dynamically creates a Pydantic model.
        """
        model_fields = {}

        for k, v in fields.items():
            if isinstance(v, list):
                if v and isinstance(v[0], dict):
                    # nested list of dictionaries — create a submodel
                    nested_model = self._create_pydantic_model(f'{name}_{k}', v[0])
                    model_fields[k] = (list[nested_model], v)
                elif v:
                    # list of primitive values
                    item_type = type(v[0]) if v[0] is not None else Any
                    model_fields[k] = (list[item_type], v)
                else:
                    # empty list — unknown type
                    model_fields[k] = (list[Any], v)

            elif isinstance(v, dict):
                # nested dictionary — create a submodel
                nested_model = self._create_pydantic_model(f'{name}_{k}', v)
                model_fields[k] = (nested_model, v)

            else:
                # primitive value
                field_type = type(v) if v is not None else Any
                model_fields[k] = (field_type, v)

        return create_model(name, **model_fields)


def calc_property(
    fields_calc: list[FieldDynamic | FieldCalc | str | Callable[[], FieldCalc]],
    as_filter: bool = False,
    filter_field: type = None,
):
    """
    Decorator for creating a cached property with field calculations and optional
    filtering.

    Tags: RAG, EXPORT
    """

    def decor(func):
        """
        Inner decorator function that applies the calc_cached_property to the decorated
        function.
        """
        fields_converted = [
            field() if isinstance(field, FieldDynamic) else field for field in fields_calc
        ]
        fields_normalized = _fields_related_normalize(fields_converted)

        @wraps(func)
        def wrapper(instance, *args, **kwargs):
            calc_field_data_param = next(
                (
                    k
                    for k, v in inspect.signature(func).parameters.items()
                    if v.annotation is DependsCalc
                ),
                None,
            )
            if calc_field_data_param:
                depends_calc_model = DependsCalc()
                depends_calc_model.build_calc_field_data(instance, fields_normalized)
                return func(instance, depends_calc_model, *args, **kwargs)
            else:
                return func(instance, *args, **kwargs)

        prop = calc_cached_property(wrapper)
        prop.fields_calc = fields_normalized
        prop.as_filter = as_filter
        prop.filter_field = filter_field

        # Attempt to extract return type annotation for later use in response_type.
        # This may fail if the annotation contains unresolved forward references or unknown types.
        # In such cases, we safely ignore the error and default to None.
        try:
            return_type = get_type_hints(func).get('return', None)
        except Exception:
            return_type = None
        prop.response_type = return_type

        return prop

    return decor


def _apply_calc_queryset(  # noqa: C901
    queryset: QuerySet, fields_calc: list[FieldCalc | str], context: dict = None
) -> QuerySet | list:
    """
    Applies field calculations to a queryset, handling related fields, subqueries,
    and annotations.

    Tags: RAG, EXPORT
    """
    select_related = []
    prefetch_related = []
    annotates = {}

    queryset = queryset.alias(**{k: Value(v) for k, v in context.items() if k.startswith('_')})

    fields_info = queryset.model.get_fields_info()

    # process cache fields
    for field_calc in fields_calc:
        alias = field_calc.alias or field_calc.source

        if isinstance(field_calc, str):
            field_calc = FieldJson(source=field_calc)

        if isinstance(field_calc, FieldSubquery) or isinstance(field_calc, FieldRelated):
            f_model = None
            f_name, f_related = None, None
            f_info: RelationInfo | None = None

            try:
                f_model = apps.get_model(field_calc.source)
            except Exception:
                f_name, f_related = (field_calc.source.split('__', 1) + ['id'])[:2]
                f_info = fields_info.relations.get(f_name)

            if not (f_info or f_model):
                continue

            if isinstance(field_calc, FieldSubquery):
                if isinstance(field_calc, FieldValues):
                    qs_related = (f_model or f_info.related_model).objects.all()
                elif not f_info:
                    continue
                else:
                    qs_related = f_info.get_subqueryset()

                if context:
                    qs_related = qs_related.alias(
                        **{k: Value(v) for k, v in context.items() if k.startswith('_')}
                    )

                if isinstance(field_calc, FieldValues):
                    if field_calc.nested:
                        qs_related, __ = _apply_calc_queryset(
                            qs_related, field_calc.nested, context=context
                        )
                    if field_calc.query:
                        qs_related = qs_related.filter(field_calc.query)
                    if field_calc.filter_fn:
                        qs_related = field_calc.filter_fn(qs_related, context or {})

                    annotates[alias] = ArraySubquery(qs_related.values('id'))

                elif isinstance(field_calc, FieldIsExists):
                    if field_calc.nested:
                        qs_related, __ = _apply_calc_queryset(
                            qs_related, field_calc.nested, context=context
                        )
                    if field_calc.query:
                        qs_related = qs_related.filter(field_calc.query)
                    if field_calc.filter_fn:
                        qs_related = field_calc.filter_fn(qs_related, context or {})

                    qs_exists = Exists(qs_related.values('id'))
                    annotates[alias] = ~qs_exists if field_calc.is_invert else qs_exists

                elif isinstance(field_calc, FieldSubAggr):
                    if field_calc.query:
                        qs_related = qs_related.filter(field_calc.query)
                    if field_calc.filter_fn:
                        qs_related = field_calc.filter_fn(qs_related, context or {})

                    func_kwargs = {}
                    if field_calc.distinct:
                        func_kwargs['distinct'] = True

                    annotates[alias] = Subquery(
                        qs_related.annotate(
                            _resp=Func(F(f_related), function=field_calc.func, **func_kwargs)
                        ).values('_resp'),
                        output_field=IntegerField()
                        if field_calc.func in ['Count']
                        else field_calc.output_field,
                    )

                elif isinstance(field_calc, FieldJson):
                    # processing a special case when only id is needed without additional conditions
                    # for this, it is enough to join only the through model
                    if (
                        f_info.is_m2m
                        and (not field_calc.fields or field_calc.fields == ['id'])
                        and not field_calc.nested
                        and not field_calc.query
                        and not field_calc.order_by
                        and not field_calc.slice
                        and not field_calc.filter_fn
                    ):
                        qs_related = f_info.through_model.objects.filter(
                            **{f_info.m2m_field_self: OuterRef('pk')}
                        ).values(json=JSONObject(id=f_info.m2m_field_rel))
                    else:
                        if field_calc.nested:
                            qs_related, __ = _apply_calc_queryset(
                                qs_related, field_calc.nested, context=context
                            )
                        if field_calc.query:
                            qs_related = qs_related.filter(field_calc.query)
                        if field_calc.filter_fn:
                            qs_related = field_calc.filter_fn(qs_related, context or {})

                        # Check whether the attribute is a TranslatedField
                        fields_sources = []
                        for _f_name in field_calc.fields:
                            try:
                                attr = getattr(qs_related.model, _f_name)
                            except AttributeError:
                                pass
                            else:
                                if isinstance(attr, TranslatedField):
                                    fields_sources.append(to_attribute(_f_name))
                                    continue
                            fields_sources.append(_f_name)

                        qs_related = qs_related.values(
                            json=JSONObject(
                                **dict(zip(field_calc.fields, fields_sources, strict=False))
                            )
                        )

                        if field_calc.order_by:
                            qs_related = qs_related.order_by(*field_calc.order_by)

                        if field_calc.slice:
                            qs_related = qs_related[field_calc.slice]

                    annotates[alias] = ArraySubquery(qs_related)

            elif isinstance(field_calc, FieldRelated):
                if not f_info:
                    continue

                if field_calc.nested:
                    qs_nested, select_related_nested = _apply_calc_queryset(
                        f_info.related_model.objects.all(), field_calc.nested, context=context
                    )

                    if f_info.to_many:
                        prefetch_related.append(Prefetch(f_name, queryset=qs_nested, to_attr=alias))
                    else:
                        for sr in select_related_nested:
                            select_related.append(f'{f_name}__{sr}')
                else:
                    if f_info.to_many:
                        prefetch_related.append(Prefetch(f_name, to_attr=alias))
                    else:
                        select_related.append(f_name)

        elif isinstance(field_calc, FieldAggr):
            annotates[alias] = field_calc.func(
                field_calc.source,
                filter=field_calc.query,
                distinct=field_calc.distinct,
            )

        elif isinstance(field_calc, FieldAnnotate):
            annotates[alias] = field_calc.query

    if prefetch_related:
        queryset = queryset.prefetch_related(*prefetch_related)

    if annotates:
        queryset = queryset.annotate(**annotates)

    return queryset, select_related


def _fields_reduce(fields_calc: list[FieldCalc | str | Callable[[], FieldCalc]]):
    """
    Performs field reduction, merging similar fields and handling nested structures.
    """
    d_fields: dict[tuple[type, str], FieldCalc] = {}

    # reduce annotate fields
    for field in fields_calc:
        if isinstance(field, Callable):
            field = field()

        alias = field.alias or field.source
        key = (type(field), alias)

        if isinstance(field, FieldRelated):
            if field_prev := d_fields.get(key):
                if field.is_similar(field_prev):
                    field_prev.union(deepcopy(field))
                else:
                    raise Exception(f'Field {field.source} is not similar to {field.source}')
            else:
                d_fields[key] = deepcopy(field)
        else:
            d_fields[key] = deepcopy(field)

    fields = list(d_fields.values())
    for field in fields:
        if isinstance(field, FieldRelated):
            if field.nested:
                field.nested = _fields_reduce(field.nested)

    return fields


def apply_calc_queryset(
    queryset: QuerySet,
    fields_calc: list[FieldCalc | str | Callable[[], FieldCalc]],
    context: dict = None,
) -> QuerySet:
    """
    Applies field calculations to a queryset, including related fields and
    subqueries, and returns the modified queryset.

    Tags: RAG, EXPORT
    """
    fields_reduced = _fields_reduce(fields_calc)
    queryset, select_related = _apply_calc_queryset(queryset, fields_reduced, context=context)
    if select_related:
        queryset = queryset.select_related(*select_related)
    return queryset


def qs_fields_calc(
    qs: QuerySet, route_calc_fields_names: list[str], context: dict | None
) -> QuerySet:
    """
    Adds all dependencies declared as calc_property to the base queryset.

    Tags: RAG, EXPORT
    """
    model = qs.model
    fields_calc = []

    for calc_field_name in route_calc_fields_names:
        model_calc_field = getattr(model, calc_field_name)
        fields_calc.extend(model_calc_field.fields_calc)

    return apply_calc_queryset(qs, fields_calc, context=context)


def qs_fields_related(qs: QuerySet, context: dict | None, fields_allowed: list) -> QuerySet:
    """
    Adds related fields declared as calc_property to the base queryset.

    Tags: RAG, EXPORT
    """

    from bazis.core.models_abstract import InitialBase

    model: InitialBase = qs.model
    fields_calc = []

    for f_name, f_rel in model.get_fields_info().relations.items():
        if (
            f_name in fields_allowed
            and f_rel.to_many
            and issubclass(f_rel.related_model, InitialBase)
        ):
            fields_calc.append(
                FieldJson(
                    source=f_name,
                    alias=f'{f_name}__ids',
                    fields=['id', '_jsonapi_type'],
                    filter_fn=lambda _qs, _ctx: _qs.model.set_jsonapi_type(_qs, _ctx),
                )
            )

    return apply_calc_queryset(qs, fields_calc, context=context)


class CalcFieldsValidator:
    """
    Validates declared calc fields in the model.

    Tags: RAG, EXPORT
    """

    @staticmethod
    def check_route_declared_calc_fields(route_calc_fields_names: list[str], model: Model) -> None:
        """Checks if the declared calc fields exist in the model."""
        for calc_field_name in route_calc_fields_names:
            if not hasattr(model, calc_field_name):
                msg = f'Model is missing the calculated field: {calc_field_name}'
                logger.error(msg)
                raise Exception(msg)

    @staticmethod
    def validate_calc_field(
        calc_field_name: str, model_calc_fields: list, model: Model, context: dict
    ) -> None:
        """Validates context and checks structure of related tables and fields."""
        for field_calc in model_calc_fields:
            # If the model field properties specify context, then check that the request context has such keys
            if field_calc.context:
                missing_keys = set(field_calc.context) - context.keys()
                if missing_keys:
                    raise KeyError(f'Missing keys in the request context: {missing_keys}')

            # Split source into parts (for example, "user__profile__age")
            source_parts = field_calc.source.split('__')

            current_model = model  # Start from the provided model

            for source_part in source_parts:
                if type(field_calc) is not FieldAnnotate:
                    try:
                        field = current_model._meta.get_field(source_part)
                    except FieldDoesNotExist:
                        msg = (
                            f'Error in calculated field {calc_field_name}: '
                            f'model {current_model.__name__} does not have related table {source_part}'
                        )
                        logger.warning(msg)
                        # raise AttributeError(msg) from None
                    else:
                        # If the field is a ForeignKey or a related model, move on to it
                        if isinstance(field, ForeignKey | OneToOneField | ManyToOneRel):
                            current_model = field.related_model

            # Recursively check nested calc_fields, if any
            if getattr(field_calc, 'nested', None):
                CalcFieldsValidator.validate_calc_field(
                    calc_field_name,
                    field_calc.nested,
                    model._meta.get_field(source_parts[0]).related_model,
                    context,
                )
