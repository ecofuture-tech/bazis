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

from fastapi import Request

from bazis.core.routes_abstract.initial import RouteContext


def get_route_ctx(request: Request) -> RouteContext:
    """
    Retrieve the RouteContext instance from the FastAPI request object. This
    function extracts the 'route_ctx' attribute from the 'endpoint' in the request's
    scope.
    """
    return request.scope['endpoint'].route_ctx


#: the default `scope` of the services of the filter, the sorting and the search
REQUEST_SCOPE = object()


def request_query_scope(scope=REQUEST_SCOPE):
    """
    The `scope` of a service of the filter, the sorting or the search: as given (None is not
    restricted), by default the `query_scope()` of the route of the request
    (`JsonApiMixin.CTX_ROUTE`), so that a route calling the service itself is restricted too.
    """
    if scope is not REQUEST_SCOPE:
        return scope
    from bazis.core.models_abstract import JsonApiMixin

    route = JsonApiMixin.CTX_ROUTE.get()
    return route.query_scope() if route is not None else None
