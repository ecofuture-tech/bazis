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

from django.contrib.gis.db.models import PointField
from django.core.exceptions import FieldError
from django.db.models import F, QuerySet
from django.utils.translation import gettext as _

from bazis.core.errors import JsonApiBazisError, JsonApiBazisException
from bazis.core.routes_abstract.initial import InitialRouteBase
from bazis.core.services.route_ctx import REQUEST_SCOPE, request_query_scope
from bazis.core.utils.geo import parse_point, point_distance
from bazis.core.utils.model_meta import FieldsInfo
from bazis.core.utils.query_complex import QueryScope, translated_lookup


# the commas of `sort` that separate its terms: not the one in the point of a distance term
_TERMS_SEP = re.compile(r',(?![^(]*\))')
# the distance from a point: `<point field>__distance(<lon>,<lat>)`
_DISTANCE_TERM = re.compile(r'(?P<field>\w+?)__distance\((?P<point>[^)]*)\)')


class SortingSearching:
    """
    Class responsible for handling sorting and searching operations on querysets.

    Tags: RAG, EXPORT
    """

    terms: list[str]
    route_cls: type[InitialRouteBase]

    def __init__(self, sort: str = None):
        """
        Initializes the SortingSearching instance with sorting terms parsed from a
        comma-separated string (a distance term `location__distance(<lon>,<lat>)` keeps its
        comma).
        """
        self.terms = []
        if sort:
            self.terms = [it.strip() for it in _TERMS_SEP.split(sort) if it.strip()]

    def apply(self, queryset: QuerySet, scope: QueryScope | None = REQUEST_SCOPE):
        """
        Applies the sorting terms to the given queryset. With a scope (by default the scope
        of the route of the request) a term is a field of the route that can order, or a
        field of an object a to-one relation of the route leads to (null if the user cannot
        see the object); without one (None) any field path of the model. A term
        `<point field>__distance(<lon>,<lat>)` sorts by the distance from the point (a
        point field of the model in the scope; the nearest first, the objects without a
        point last). Invalid terms are 400 ERR_FILTER.
        """
        if not self.terms:
            return queryset
        scope = request_query_scope(scope)
        try:
            ordering = [self._ordering(queryset.model, t, scope) for t in self.terms]
            # the primary key makes the order deterministic when the sorted values are not
            # unique, otherwise pagination may skip or repeat items between pages
            pk_names = {'pk', queryset.model._meta.pk.name}
            if not any(t.lstrip('-') in pk_names for t in self.terms):
                ordering.append('pk')
            return queryset.order_by(*ordering)
        except (FieldError, ValueError):
            raise JsonApiBazisException(
                JsonApiBazisError(
                    detail=_('Invalid sorting parameters: `%s`') % self.terms,
                    loc=('query', 'sort'),
                    code='ERR_FILTER',
                    title=_('Invalid filter'),
                    status=400,
                ),
                status=400,
            ) from None

    @staticmethod
    def _ordering(model, term: str, scope: QueryScope | None):
        """
        The ordering of a term (`-` for the descending order, nulls last).
        """
        path = term.removeprefix('-')
        if match := _DISTANCE_TERM.fullmatch(path):
            expr = SortingSearching._distance(model, match['field'], match['point'], scope)
        elif scope is None:
            # a translated field by its column of the language of the request
            expr = translated_lookup(model, path)
        else:
            expr = scope.order_expression(model, path)
        if isinstance(expr, F):
            # a field of the model, by its name: order_by checks it
            expr = expr.name
        if term.startswith('-'):
            return (F(expr) if isinstance(expr, str) else expr).desc(nulls_last=True)
        return expr if isinstance(expr, str) else expr.asc()

    @staticmethod
    def _distance(model, name: str, point: str, scope: QueryScope | None):
        """
        The distance from the point to a point field of the model that the scope allows to
        sort by (any point field without a scope). Raises ValueError for any other field.
        """
        field = FieldsInfo.get_fields_info(model).attributes.get(name)
        if not isinstance(field, PointField) or (
            scope is not None and not scope.allows(name, model, order=True)
        ):
            raise ValueError(f'Unknown point field {name!r} of {model._meta.label}')
        return point_distance(field, parse_point(point))
