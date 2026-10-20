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

import re
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Avg, Count, F, Max, Min, QuerySet, Sum
from django.db.models.functions import Trunc
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from fastapi import Query

from pydantic import BaseModel

from bazis.core.errors import JsonApiBazisError, JsonApiBazisException
from bazis.core.services.route_ctx import REQUEST_SCOPE, request_query_scope
from bazis.core.utils.query_complex import QueryScope


#: a value of an aggregate: a count, a sum or an average, a minimum or a maximum of a
#: number or a date; None over no object (a count is 0)
AggregateValue = int | float | Decimal | datetime | date | None

NUMBERS = (models.IntegerField, models.DecimalField, models.FloatField)
#: the functions of a field and the fields they apply to
FUNCTIONS = {
    'sum': (Sum, NUMBERS),
    'avg': (Avg, NUMBERS),
    'min': (Min, (*NUMBERS, models.DateField)),
    'max': (Max, (*NUMBERS, models.DateField)),
    'count': (Count, (models.Field,)),
}
BUCKETS = ('day', 'week', 'month')
TERM = re.compile(r'^(?P<func>\w+)\((?P<field>\w+)\)$')
COUNT = 'count'


class AggregatesGroup(BaseModel):
    """
    The aggregates of the objects of one value of the `group` field.

    Tags: RAG, EXPORT
    """

    #: the value as a string: the choice, `true`/`false`, the id of the related object, the
    #: ISO date of the start of the bucket; None for the objects without a value
    group: str | None
    values: dict[str, AggregateValue]


#: `meta.aggregates`: the aggregates by their terms, or a list of the groups ordered by
#: their value (None last) with `group`
AggregatesMeta = dict[str, AggregateValue] | list[AggregatesGroup]


def aggregate_error(param: str, detail) -> JsonApiBazisException:
    """400 `ERR_AGGREGATE` at the query parameter."""
    return JsonApiBazisException(
        JsonApiBazisError(
            detail=str(detail),
            loc=('query', param),
            code='ERR_AGGREGATE',
            title=_('Invalid aggregate'),
            status=400,
        ),
        status=400,
    )


class ServiceAggregating:
    """
    The aggregates of the objects of a list (`meta=aggregates`): `aggregate` names the
    functions of the fields, `group` the field that groups the objects. A field is one the
    filter of the route may reach for the user (its query scope): an aggregate tells no
    more than a filter of the list.

    Tags: RAG, EXPORT
    """

    def __init__(
        self,
        aggregate: str | None = Query(
            None,
            description=_(
                'The aggregates of meta=aggregates: count, sum(f), avg(f), min(f), max(f), '
                'count(f), separated by commas'
            ),
        ),
        group: str | None = Query(
            None,
            description=_(
                'The field that groups meta=aggregates: a choice, a boolean, a to-one '
                'relation, or a date with :day, :week or :month'
            ),
        ),
    ):
        self.aggregate = aggregate
        self.group = group

    @staticmethod
    def _field(name: str, model: type[models.Model], scope: QueryScope | None, param: str):
        """The column of the model the scope reaches by the name, or 400."""
        try:
            field = model._meta.get_field(name)
        except FieldDoesNotExist:
            field = None
        if (
            field is None
            or not field.concrete
            or field.many_to_many
            or (scope is not None and not scope.allows(name, model))
        ):
            raise aggregate_error(
                param,
                format_lazy(
                    _("Unknown aggregate field '{field}' of {model}"),
                    field=name,
                    model=model._meta.label,
                ),
            )
        return field

    def _terms(self, model: type[models.Model], scope: QueryScope | None) -> dict:
        """The expressions of the terms of `aggregate` (`count` without it) by the term."""
        terms = {}
        for term in (it.strip() for it in (self.aggregate or COUNT).split(',')):
            if term == COUNT:
                terms[term] = Count('pk')
                continue
            match = TERM.match(term)
            if match is None or match['func'] not in FUNCTIONS:
                raise aggregate_error(
                    'aggregate',
                    format_lazy(
                        _(
                            "Invalid aggregate '{term}': count, or sum, avg, min, max or "
                            'count of a field, such as sum(amount)'
                        ),
                        term=term,
                    ),
                )
            func, kinds = FUNCTIONS[match['func']]
            name = match['field']
            field = self._field(name, model, scope, 'aggregate')
            if not isinstance(field, kinds):
                raise aggregate_error(
                    'aggregate',
                    format_lazy(
                        _("The aggregate '{term}' does not apply to the field '{field}'"),
                        term=term,
                        field=name,
                    ),
                )
            terms[term] = func(name)
        return terms

    def _group(self, model: type[models.Model], scope: QueryScope | None):
        """The expression of `group`, None without it."""
        if not self.group:
            return None
        name, __, bucket = self.group.strip().partition(':')
        field = self._field(name, model, scope, 'group')
        if isinstance(field, models.DateField):
            if bucket in BUCKETS:
                return Trunc(name, bucket, output_field=models.DateField())
        elif not bucket and (
            field.choices
            or isinstance(field, models.BooleanField)
            or field.many_to_one
            or field.one_to_one
        ):
            return F(name)
        raise aggregate_error(
            'group',
            format_lazy(
                _(
                    "Cannot group by '{group}': group by a choice field, a boolean, a to-one "
                    'relation, or a date field by day, week or month (such as {field}:month)'
                ),
                group=self.group,
                field=name,
            ),
        )

    @staticmethod
    def _group_key(value) -> str | None:
        """The value of a group as a string."""
        if value is None:
            return None
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def apply(self, queryset: QuerySet, scope: QueryScope | None = REQUEST_SCOPE) -> AggregatesMeta:
        """
        The aggregates of the objects of the queryset (one query): by the term without
        `group`, else a list of the groups. The objects are taken by their keys, so the
        annotations of the queryset (the calculated fields, a permission) change nothing.

        :param scope: what the fields may reach; by default the scope of the route of the
            request (`query_scope`), None: not restricted.
        """
        scope = request_query_scope(scope)
        model = queryset.model
        terms = self._terms(model, scope)
        group = self._group(model, scope)
        aliases = {f'_aggregate_{i}': term for i, term in enumerate(terms)}
        exprs = {alias: terms[term] for alias, term in aliases.items()}
        qs = model._default_manager.filter(pk__in=queryset.order_by().values('pk'))
        if group is None:
            row = qs.aggregate(**exprs)
            return {term: row[alias] for alias, term in aliases.items()}
        rows = (
            qs.annotate(_aggregate_group=group)
            .values('_aggregate_group')
            .annotate(**exprs)
            .order_by(F('_aggregate_group').asc(nulls_last=True))
        )
        return [
            AggregatesGroup(
                group=self._group_key(row['_aggregate_group']),
                values={term: row[alias] for alias, term in aliases.items()},
            )
            for row in rows
        ]
