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

from django.core.exceptions import FieldError
from django.db.models import F, QuerySet
from django.utils.translation import gettext as _

from bazis.core.errors import JsonApiBazisError, JsonApiBazisException
from bazis.core.routes_abstract.initial import InitialRouteBase
from bazis.core.services.route_ctx import REQUEST_SCOPE, request_query_scope
from bazis.core.utils.query_complex import QueryScope, translated_lookup


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
        comma-separated string.
        """
        self.terms = []
        if sort:
            self.terms = [it.strip() for it in sort.split(',') if it.strip()]

    def apply(self, queryset: QuerySet, scope: QueryScope | None = REQUEST_SCOPE):
        """
        Applies the sorting terms to the given queryset. With a scope (by default the scope
        of the route of the request) a term is a field of the route that can order, or a
        field of an object a to-one relation of the route leads to (null if the user cannot
        see the object); without one (None) any field path of the model. Invalid terms are
        400 ERR_FILTER.
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
        if scope is None:
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
