from fastapi import Request

from bazis.core.routes_abstract.initial import RouteContext


def get_route_ctx(request: Request) -> RouteContext:
    """
    Retrieve the RouteContext instance from the FastAPI request object. This
    function extracts the 'route_ctx' attribute from the 'endpoint' in the request's
    scope.
    """
    return request.scope['endpoint'].route_ctx
