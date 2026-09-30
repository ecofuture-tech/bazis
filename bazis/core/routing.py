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

from collections.abc import Callable, Iterator, Sequence
from enum import Enum, IntEnum
from importlib import import_module
from typing import Any

from fastapi import APIRouter, params
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.types import DecoratedCallable, IncEx
from fastapi.utils import generate_unique_id, get_value_or_default

from starlette import routing as starlette_routing
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute


class BazisRoute(APIRoute):
    """
    Route class used by Bazis for fully initialized routes.

    Earlier FastAPI versions cloned the response model field for every route, which is
    very expensive for the large dynamically generated JSON:API schemas, so Bazis used to
    carry its own copy of ``APIRoute.__init__``. Current FastAPI no longer clones the
    response field, so the stock implementation is used and this class only remains
    as an extension point.
    """


class BazisDummyRoute(APIRoute):
    """
    A lightweight placeholder route that only stores the route declaration.

    Class-based routes are registered in many nested routers. Building dependencies and
    response fields for them is expensive, so the placeholder skips it: when a router is
    included into the application, FastAPI builds an effective route context from the
    stored declaration, and that context resolves dependencies, validates and handles
    requests. The placeholder itself is not meant to be mounted directly.
    """

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        response_model: Any = Default(None),
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = 'Successful Response',
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        name: str | None = None,
        methods: set[str] | list[str] | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] | DefaultPlaceholder = Default(JSONResponse),
        dependency_overrides_provider: Any | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[['APIRoute'], str] | DefaultPlaceholder = Default(
            generate_unique_id
        ),
        strict_content_type: bool | DefaultPlaceholder = Default(True),
        stream_item_type: Any | None = None,
        **kwargs,
    ) -> None:
        """
        Initializes a BazisDummyRoute instance, storing the route declaration without
        building dependencies and response fields.
        """
        self.path = path
        self.endpoint = endpoint
        self.response_model = response_model
        self.summary = summary
        self.response_description = response_description
        self.deprecated = deprecated
        self.operation_id = operation_id
        self.response_model_include = response_model_include
        self.response_model_exclude = response_model_exclude
        self.response_model_by_alias = response_model_by_alias
        self.response_model_exclude_unset = response_model_exclude_unset
        self.response_model_exclude_defaults = response_model_exclude_defaults
        self.response_model_exclude_none = response_model_exclude_none
        self.include_in_schema = include_in_schema
        self.response_class = response_class
        self.dependency_overrides_provider = dependency_overrides_provider
        self.callbacks = callbacks
        self.openapi_extra = openapi_extra
        self.generate_unique_id_function = generate_unique_id_function
        self.strict_content_type = strict_content_type
        self.stream_item_type = stream_item_type
        self.tags = tags or []
        self.responses = responses or {}
        self.name = name
        if methods is None:
            methods = ['GET']
        self.methods: set[str] = {method.upper() for method in methods}
        if isinstance(status_code, IntEnum):
            status_code = int(status_code)
        self.status_code = status_code
        self.dependencies = list(dependencies or [])
        self.description = description

        for k, v in kwargs.items():
            setattr(self, k, v)


def iter_api_routes(routes: Sequence[BaseRoute]) -> Iterator[APIRoute]:
    """
    Iterates over the declared API routes, including the routes of included routers.

    Since FastAPI 0.137 ``include_router`` does not copy the routes into the parent router:
    it adds a wrapper that references the included router (``original_router``) and builds
    the effective routes lazily. The wrappers are walked without building them.

    Tags: RAG, EXPORT
    """
    seen = set()

    def walk(routes_: Sequence[BaseRoute]) -> Iterator[APIRoute]:
        for route in routes_:
            if isinstance(route, APIRoute):
                if id(route) not in seen:
                    seen.add(id(route))
                    yield route
            elif isinstance(included := getattr(route, 'original_router', None), APIRouter):
                yield from walk(included.routes)

    yield from walk(routes)


class BazisRouter(APIRouter):
    """
    Custom router class inheriting from FastAPI's APIRouter, with additional methods
    for route management and registration.

    Tags: RAG, EXPORT
    """

    def __init__(self, **kwargs) -> None:
        """
        Initializes a BazisRouter instance, setting the default route class to
        BazisDummyRoute and passing any additional keyword arguments to the superclass
        constructor.
        """
        kwargs.setdefault('route_class', BazisDummyRoute)
        super().__init__(**kwargs)

    def routes_cast(self, new_class: type[APIRoute] = APIRoute) -> list[BaseRoute]:
        """
        Changes the class of the routes of this router and all included routers to the
        specified one. It is used to replace the lightweight BazisDummyRoute placeholders,
        so that the methods of the target class (e.g. ``get_route_handler``) are used
        when FastAPI builds the effective routes of the application.

        :param new_class: The class to which the route type should be changed.
        :return: The routes of the router.
        """
        for route in iter_api_routes(self.routes):
            route.__class__ = new_class
        return self.routes

    def register(self, prefix, arg=None, **kwargs):
        """
        Registers a new route or router with the given prefix and additional keyword
        arguments. Supports importing modules, including routers, and resetting routes.
        """
        if arg is None:
            arg = prefix
            prefix = ''

        if isinstance(arg, str):
            # example: router.register('entity.router')
            app_router = import_module(arg)
            self.include_router(app_router.router, prefix=prefix, **kwargs)
            if routers_with_prefix := getattr(app_router, 'routers_with_prefix', None):
                for router_prefix, router_value in routers_with_prefix.items():
                    self.include_router(router_value, prefix=f'/{router_prefix}', **kwargs)
        elif isinstance(arg, APIRouter):
            # example: router.register(routes.ChildEntityRouteSet.as_router())
            if hasattr(arg, 'get_url_prefix'):
                prefix = arg.get_url_prefix()
            self.include_router(arg, prefix=prefix, **kwargs)
        elif hasattr(arg, 'route'):
            self.reset_route(prefix, arg.route)

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs):
        """
        Adds a new API route to the router, saving information about the installed route
        for the given endpoint.
        """
        super().add_api_route(path, endpoint, **kwargs)
        # save info about the installed route for this endpoint
        endpoint.route = self.routes[-1]

    def reset_route(self, path: str, route):
        """
        Resets an existing route with the specified path and route configurations,
        supporting various route types including APIRoute, starlette.routing.Route,
        APIWebSocketRoute, and starlette.routing.WebSocketRoute.
        """
        if isinstance(route, APIRoute):
            combined_responses = {**route.responses}
            use_response_class = get_value_or_default(
                route.response_class,
                self.default_response_class,
            )
            current_generate_unique_id = get_value_or_default(
                route.generate_unique_id_function,
                self.generate_unique_id_function,
            )
            self.add_api_route(
                path or route.path,
                route.endpoint,
                response_model=route.response_model,
                status_code=route.status_code,
                tags=route.tags.copy(),
                dependencies=route.dependencies.copy(),
                summary=route.summary,
                description=route.description,
                response_description=route.response_description,
                responses=combined_responses,
                deprecated=route.deprecated or self.deprecated,
                methods=route.methods,
                operation_id=route.operation_id,
                response_model_include=route.response_model_include,
                response_model_exclude=route.response_model_exclude,
                response_model_by_alias=route.response_model_by_alias,
                response_model_exclude_unset=route.response_model_exclude_unset,
                response_model_exclude_defaults=route.response_model_exclude_defaults,
                response_model_exclude_none=route.response_model_exclude_none,
                include_in_schema=route.include_in_schema and self.include_in_schema,
                response_class=use_response_class,
                name=route.name,
                route_class_override=type(route),
                callbacks=route.callbacks.copy(),
                openapi_extra=route.openapi_extra,
                generate_unique_id_function=current_generate_unique_id,
                strict_content_type=route.strict_content_type,
            )
        elif isinstance(route, starlette_routing.Route):
            methods = list(route.methods or [])  # type: ignore # in Starlette
            self.add_route(
                path or route.path,
                route.endpoint,
                methods=methods,
                include_in_schema=route.include_in_schema,
                name=route.name,
            )
        elif isinstance(route, APIWebSocketRoute):
            self.add_api_websocket_route(path or route.path, route.endpoint, name=route.name)
        elif isinstance(route, starlette_routing.WebSocketRoute):
            self.add_websocket_route(path or route.path, route.endpoint, name=route.name)

    def internal(
        self,
        path: str,
        *,
        response_model: type[Any] | None = None,
        status_code: int | None = None,
        tags: list[str | Enum] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_description: str = 'Successful Response',
        responses: dict[int | str, dict[str, Any]] | None = None,
        deprecated: bool | None = None,
        operation_id: str | None = None,
        response_model_include: IncEx | None = None,
        response_model_exclude: IncEx | None = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        response_class: type[Response] = Default(JSONResponse),
        name: str | None = None,
        callbacks: list[BaseRoute] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        generate_unique_id_function: Callable[[APIRoute], str] = Default(generate_unique_id),
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """
        Decorator method for defining internal routes with the specified path and
        additional configurations, including response model, status code, tags,
        dependencies, and more.
        """
        return self.api_route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=['INTERNAL'],
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )
