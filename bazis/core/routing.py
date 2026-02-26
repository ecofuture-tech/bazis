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

import inspect
from collections.abc import Callable, Sequence
from enum import Enum, IntEnum
from importlib import import_module
from typing import Any

from fastapi import APIRouter, params
from fastapi._compat import (
    ModelField,
    annotation_is_pydantic_v1,
    lenient_issubclass,
)
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.dependencies.utils import (
    _should_embed_body_fields,
    get_body_field,
    get_dependant,
    get_flat_dependant,
    get_parameterless_sub_dependant,
    get_typed_return_annotation,
)
from fastapi.exceptions import (
    PydanticV1NotSupportedError,
)
from fastapi.routing import APIRoute, APIWebSocketRoute, request_response
from fastapi.types import DecoratedCallable, IncEx
from fastapi.utils import (
    create_model_field,
    generate_unique_id,
    get_value_or_default,
    is_body_allowed_for_status_code,
)

from starlette import routing as starlette_routing
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, compile_path, get_name


class BazisRoute(APIRoute):
    """
    Custom route class inheriting from FastAPI's APIRoute, with additional handling
    for response models, dependencies, and other route-specific configurations.
    """

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        response_model: Any = None,
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
    ) -> None:
        """
        Initializes a BazisRoute instance with the given parameters, setting up the
        path, endpoint, response model, dependencies, and other route-specific
        configurations.
        """
        self.path = path
        self.endpoint = endpoint
        if isinstance(response_model, DefaultPlaceholder):
            return_annotation = get_typed_return_annotation(endpoint)
            if lenient_issubclass(return_annotation, Response):
                response_model = None
            else:
                response_model = return_annotation
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
        self.tags = tags or []
        self.responses = responses or {}
        self.name = get_name(endpoint) if name is None else name
        self.path_regex, self.path_format, self.param_convertors = compile_path(path)
        self.strict_content_type = strict_content_type
        if methods is None:
            methods = ['GET']
        self.methods: set[str] = {method.upper() for method in methods}
        if isinstance(generate_unique_id_function, DefaultPlaceholder):
            current_generate_unique_id: Callable[[APIRoute], str] = (
                generate_unique_id_function.value
            )
        else:
            current_generate_unique_id = generate_unique_id_function
        self.unique_id = self.operation_id or current_generate_unique_id(self)
        # normalize enums e.g. http.HTTPStatus
        if isinstance(status_code, IntEnum):
            status_code = int(status_code)
        self.status_code = status_code
        if self.response_model:
            assert is_body_allowed_for_status_code(status_code), (
                f'Status code {status_code} must not have a response body'
            )
            response_name = 'Response_' + self.unique_id
            if annotation_is_pydantic_v1(self.response_model):
                raise PydanticV1NotSupportedError(
                    'pydantic.v1 models are no longer supported by FastAPI.'
                    f' Please update the response model {self.response_model!r}.'
                )
            self.response_field = create_model_field(
                name=response_name,
                type_=self.response_model,
                mode='serialization',
            )
            # Create a clone of the field, so that a Pydantic submodel is not returned
            # as is just because it's an instance of a subclass of a more limited class
            # e.g. UserInDB (containing hashed_password) could be a subclass of User
            # that doesn't have the hashed_password. But because it's a subclass, it
            # would pass the validation and be returned as is.
            # By being a new field, no inheritance will be passed as is. A new model
            # will be always created.
            # self.secure_cloned_response_field: Optional[
            #     ModelField
            # ] = create_cloned_field(self.response_field)
            self.secure_cloned_response_field: ModelField | None = self.response_field
        else:
            self.response_field = None  # type: ignore
            self.secure_cloned_response_field = None
        self.dependencies = list(dependencies or [])
        self.description = description or inspect.cleandoc(self.endpoint.__doc__ or '')
        # if a "form feed" character (page break) is found in the description text,
        # truncate description text to the content preceding the first "form feed"
        self.description = self.description.split('\f')[0].strip()
        response_fields = {}
        for additional_status_code, response in self.responses.items():
            assert isinstance(response, dict), 'An additional response must be a dict'
            model = response.get('model')
            if model:
                assert is_body_allowed_for_status_code(additional_status_code), (
                    f'Status code {additional_status_code} must not have a response body'
                )
                response_name = f'Response_{additional_status_code}_{self.unique_id}'
                if annotation_is_pydantic_v1(model):
                    raise PydanticV1NotSupportedError(
                        'pydantic.v1 models are no longer supported by FastAPI.'
                        f' In responses={{}}, please update {model}.'
                    )
                response_field = create_model_field(
                    name=response_name, type_=model, mode='serialization'
                )
                response_fields[additional_status_code] = response_field
        if response_fields:
            self.response_fields: dict[int | str, ModelField] = response_fields
        else:
            self.response_fields = {}

        assert callable(endpoint), 'An endpoint must be a callable'
        self.dependant = get_dependant(path=self.path_format, call=self.endpoint, scope='function')
        for depends in self.dependencies[::-1]:
            self.dependant.dependencies.insert(
                0,
                get_parameterless_sub_dependant(depends=depends, path=self.path_format),
            )
        self._flat_dependant = get_flat_dependant(self.dependant)
        self._embed_body_fields = _should_embed_body_fields(self._flat_dependant.body_params)
        self.body_field = get_body_field(
            flat_dependant=self._flat_dependant,
            name=self.unique_id,
            embed_body_fields=self._embed_body_fields,
        )
        self.app = request_response(self.get_route_handler())


class BazisDummyRoute(APIRoute):
    """
    A simplified version of BazisRoute, intended for use as a placeholder or default
    route class with basic configurations.
    """

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        response_model: Any = None,
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
        **kwargs,
    ) -> None:
        """
        Initializes a BazisDummyRoute instance with the given parameters, setting up the
        path, endpoint, response model, dependencies, and other basic configurations.
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

    def routes_cast(self, new_class: type[APIRoute] = APIRoute) -> list[APIRoute]:
        """
        Changes the route type to the specified one. This method is intended to work around
        the issue of the default route type setting in FastAPI, where the route type
        is determined through fastapi.routing.APIRouter.include_router:

        route_class_override=type(route)

        :param new_class: The class to which the route type should be changed.
        :return: A list of routes with the changed type.
        """
        for route in self.routes:
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
