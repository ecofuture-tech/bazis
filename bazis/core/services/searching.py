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

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from fastapi import Depends

from bazis.core.errors import JsonApiBazisError, JsonApiBazisException
from bazis.core.routes_abstract.initial import InitialRouteBase, RouteContext
from bazis.core.services.route_ctx import REQUEST_SCOPE, get_route_ctx, request_query_scope
from bazis.core.utils.query_complex import QueryScope, SearchToOrm


class ServiceSearching:
    """
    ServiceSearching handles the search functionality for a given queryset: with a query
    scope, the search fields of the scope (`QueryScope.search_fields`: the `search_fields`
    of its route, else the text fields of the LIST schema for the user); without one, the
    `search_fields` of the route class, else every text and integer field of the model.

    Tags: RAG, EXPORT
    """

    search: str
    route_cls: type[InitialRouteBase]

    def __init__(self, search: str = None, route_ctx: RouteContext = Depends(get_route_ctx)):
        """
        Initializes the ServiceSearching class with an optional search string and a
        route context. The route context provides the route class, whose `search_fields`
        are searched when `apply` gets no scope; with a scope the fields are those of the
        scope.
        """
        self.search = search
        self.route_cls = route_ctx.route_cls

    def apply(self, queryset: QuerySet, scope: QueryScope | None = REQUEST_SCOPE):
        """
        Applies the search query to the provided queryset by constructing a Q object and
        filtering the queryset based on the search terms. With a scope (by default the
        scope of the route of the request) its search fields are searched where it reaches
        them (`search_fields` of the route, else the text fields of its LIST schema for the
        user), and a search without one of them is 400 ERR_FILTER; without a scope (None)
        the `search_fields` of the route, else every text and integer field of the model.
        """
        scope = request_query_scope(scope)
        try:
            search = SearchToOrm(
                queryset.model,
                self.search,
                search_fields=self.route_cls.search_fields if scope is None else None,
                scope=scope,
            )
        except ValueError as e:
            raise JsonApiBazisException(
                JsonApiBazisError(
                    detail=str(e),
                    loc=('query', 'search'),
                    code='ERR_FILTER',
                    title=_('Invalid filter'),
                    status=400,
                ),
                status=400,
            ) from e
        return queryset.filter(search.q)
