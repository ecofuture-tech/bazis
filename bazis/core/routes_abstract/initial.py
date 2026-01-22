"""
Module Purpose:

- Implements the basic logic of class-based routes
- Provides class implementations for FastAPI
- Allows defining routes as class methods
- Decorators of the form `http\_...` serve as replacements for standard FastAPI decorators
- `http_internal` - a special decorator. Implements the possibility for programmatic route invocation.

An object of the `InitialRouteBase` class is created when FastAPI initializes the route object
and resolves dependencies.

Methods decorated as routes implement similar capabilities as FastAPI routes. In particular,
dependency implementation.
Additionally, dependencies can be defined in special data classes `Inject`. Dependencies
declared in this class will be available in all routes of the current and inherited classes,
in the attribute: `self.inject`. Dependencies defined in the signature of
a specific route will only be available in the object created in the context of that route.

Lifecycle of the `InitialRouteBase` route class and its objects:

- When defining a specific class, the meta-class `RouteSetMeta`:
  - Collects `Inject` classes from the class inheritance tree and creates a combined `InjectCommon` class,
  including dependencies from all parent classes.
  - Collects the class attribute `routes_ctx`, containing route wrapper objects for the current class.
  - Launches the class initialization method `cls_init`.

After defining the class, it can be set as a router. To do this, you need to call its method: `as_router`.
It will create a private router and initiate the creation of the endpoint function and its registration
for each route context. The creation of the endpoint function is performed by the `endpoint_make` method.
It creates the final `Inject` class for dependency initialization considering the dependencies defined
in the function signature. Then, an endpoint function is created, which receives the signature of the
original function.
Additionally, a dependency is added that creates the object and sets it as the `self` parameter in the
endpoint function signature.
The endpoint function runs the `route_run` function, which in turn runs the original function.
If necessary, in inherited classes, you can define logic common to all class routes in `route_run`.
Endpoint registration occurs in the `endpoint_register` method and is done
by setting the endpoint in the specified FastAPI router.
"""

import dataclasses
import inspect
from collections.abc import Callable, Sequence
from copy import deepcopy
from enum import Enum
from functools import partial
from typing import Any

from django.conf import settings
from django.utils.functional import cached_property
from django.utils.module_loading import import_string

from fastapi import Depends, Request
from fastapi.params import Depends as DependsCls
from fastapi.routing import APIRoute
from fastapi.types import IncEx
from fastapi.utils import generate_unique_id

from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute

from pydantic import BaseModel

from asgiref.sync import async_to_sync

from bazis.core.routes_abstract.context import RouteContext, RouteParams
from bazis.core.routing import BazisRoute, BazisRouter
from bazis.core.schemas.enums import ApiAction, HttpMethod
from bazis.core.utils.functools import func_sig_params_append, func_sig_transfer, get_class_name


def inject_make(*args: ApiAction):
    """
    This decorator is applied to classes inside a route class and creates a dataclass
    containing dependencies to be injected into the class routes.
    It can take API action tags as arguments; in that case, the dependencies will be injected
    only into routes with the corresponding tags.
    There can be several such classes in a route class.
    If class names coincide in the inheritance hierarchy, the last one will be used.
    If the names do not match, all classes will be combined into a single common Inject class
    based on ApiAction tags.

    Tags:  RAG, EXPORT
    """

    def decor(cls):
        cls._inject_tags = set(args)
        return dataclasses.dataclass(cls)

    return decor


ResponseModelType = (
    type[BaseModel]
    | type[str]
    | type[int]
    | type[float]
    | type[bool]
    | type[list]
    | type[dict]
    | None
)


def http_action_decor(
    http_method: HttpMethod,
    path: str,
    inject_tags: list[ApiAction] | None,
    response_model: ResponseModelType,
    response_model_route: RouteContext | Callable[..., Any] | None,
    endpoint_callbacks: list[Callable[..., Any] | partial] | None,
    *,
    status_code: int | None = None,
    tags: list[str | Enum] | None = None,
    dependencies: Sequence[DependsCls] | None = None,
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
    response_class: type[Response] = JSONResponse,
    callbacks: list[BaseRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    generate_unique_id_function: Callable[[APIRoute], str] = generate_unique_id,
) -> Callable[[Callable[..., Any]], RouteContext]:
    """
    Universal decorator for registering HTTP handlers of all types.
    Not used directly; it is called from specialized decorators.

    Tags: RAG
    """

    if http_method is HttpMethod.DELETE:
        # if the method is DELETE, the response will have no body, response_model is not needed
        response_model = None
    elif response_model_route:
        # if response_model_route is set, then response_model is taken from the endpoint specified there
        response_model = response_model_route.route_cls.endpoint_make(
            response_model_route
        ).route_params.response_model

    def decorator(func):
        nonlocal endpoint_callbacks, inject_tags

        return RouteContext(
            func=func,
            http_method=http_method.value,
            inject_tags=set(inject_tags) if inject_tags is not None else set(),
            endpoint_callbacks=endpoint_callbacks,
            route_params=RouteParams(
                path=path,
                response_model=response_model,
                status_code=status_code,
                tags=tags,
                dependencies=dependencies,
                summary=summary,
                description=description,
                responses=responses,
                response_description=response_description,
                deprecated=deprecated,
                operation_id=operation_id,
                response_model_include=response_model_include,
                response_model_exclude=response_model_exclude,
                response_model_by_alias=response_model_by_alias,
                response_model_exclude_unset=response_model_exclude_unset,
                response_model_exclude_defaults=response_model_exclude_defaults,
                response_model_exclude_none=response_model_exclude_none,
                include_in_schema=include_in_schema,
                response_class=response_class,
                callbacks=callbacks,
                openapi_extra=openapi_extra,
                generate_unique_id_function=generate_unique_id_function,
            ),
        )

    return decorator


def http_get(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a GET route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.GET,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_put(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a PUT route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.PUT,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_post(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a POST route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.POST,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_patch(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a PATCH route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.PATCH,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_delete(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a DELETE route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.DELETE,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_options(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating an OPTIONS route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.OPTIONS,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_head(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a HEAD route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.HEAD,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_trace(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating a TRACE route.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.TRACE,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


def http_internal(
    path: str,
    inject_tags: list[ApiAction] | None = None,
    response_model: ResponseModelType = None,
    response_model_route: RouteContext | Callable[..., Any] | None = None,
    endpoint_callbacks: list[Callable[..., None]] | None = None,
    **kwargs,
):
    """
    Decorator for creating an internal route, allowing programmatic invocation.

    Tags: RAG, EXPORT
    """
    return http_action_decor(
        HttpMethod.INTERNAL,
        path,
        inject_tags,
        response_model,
        response_model_route,
        endpoint_callbacks,
        **kwargs,
    )


class InitialRouteBaseMeta(type):
    """
    This meta-class performs (only for specific classes):

    - Collecting a unified Inject class across the entire inheritance tree.
    - Collecting a unified list of routes across the entire inheritance tree.
    - Launching custom initialization.

    Tags: RAG
    """

    def __new__(mcs, name: str, bases: tuple, attrs: dict, **kwargs):
        """
        Each class will have its own list of endpoints.
        """
        attrs['routes_ctx'] = {}
        # Class creation
        route_cls: type[InitialRouteBase] = super().__new__(mcs, name, bases, attrs, **kwargs)
        # Further logic - only for specific classes
        if attrs.get('abstract'):
            return route_cls

        route_cls.abstract = False

        # Collecting a unified list of route contexts from all base classes, replacing
        # the route class reference with the current one
        routes_ctx: dict[str, RouteContext] = {}
        for cl in route_cls.mro():
            if issubclass(cl, InitialRouteBase):
                for route_ctx in cl.routes_ctx.values():
                    if route_ctx.name not in routes_ctx:
                        route_ctx_for_cls = deepcopy(
                            dataclasses.replace(
                                route_ctx,
                                route_cls=route_cls,
                                route_params=deepcopy(route_ctx.route_params),
                                endpoint=None,
                            )
                        )
                        routes_ctx[route_ctx.name] = route_ctx_for_cls
                        # Overriding the route object attribute in the class
                        setattr(route_cls, route_ctx.name, route_ctx_for_cls)
        route_cls.routes_ctx = routes_ctx
        # Launching class custom initialization
        route_cls.cls_init()
        return route_cls


class ResponseRouteSet(Response):
    """
    Custom response class for route sets, overrides the render method to return the
    content directly.

    Tags: RAG
    """

    def render(self, content: Any):
        """
        Renders the response content directly.
        """
        return content

    def init_headers(self, headers: dict[str, str] = None) -> None:
        """
        Initializes the response headers.
        """
        self.raw_headers = []


class InitialRouteBase(metaclass=InitialRouteBaseMeta):
    """
    Base class for route definitions. Other class routes should inherit from it.

    Tags: RAG
    """

    abstract: bool = True
    inject: Any = None
    tags: list[str | Enum] | None = None
    actions: list[str | Enum] | None = None
    actions_exclude: list[str | Enum] | None = None
    routes_ctx: dict[str, RouteContext]
    route_ctx: RouteContext
    bazis_middlewares: list[str] = None

    @inject_make()
    class InjectRequest:
        """
        Data class for injecting the request object.
        """

        request: Request

    @classmethod
    def get_bazis_middlewares(cls):
        """
        Retrieves the list of Bazis middlewares for the current class.
        """
        bazis_middlewares = getattr(settings, 'BAZIS_MIDDLEWARES', [])

        return [import_string(path) for path in bazis_middlewares + (cls.bazis_middlewares or [])]

    @classmethod
    def get_name_route(cls, name: str):
        """
        Generates a route name based on the class name and the provided name.
        """
        return f'{cls.__name__}_{name}'

    @classmethod
    def get_url_prefix(cls) -> str:
        """
        Returns the URL prefix for the current class.
        """
        return ''

    def route_run(self, *args, **kwargs):
        """
        Method to run the endpoint function.
        Overriding this method allows implementing logic common to several routes of this class.
        """
        if func_before := getattr(self, f'{self.route_ctx.name}__before', None):
            func_before(*args, **kwargs)

        result = self.route_ctx.func(self, *args, **kwargs)

        if func_after := getattr(self, f'{self.route_ctx.name}__after', None):
            func_after(*args, **kwargs)

        return result

    @classmethod
    def endpoint_make(cls, route_ctx: RouteContext) -> RouteContext:  # noqa: C901
        """
        Creates a private (for the actual class route) parameterized endpoint from the function.
        This method ensures that the endpoint is properly configured with all necessary dependencies and parameters.
        :param route_ctx: The context of the route for which the endpoint is being created.

        """
        # If the endpoint is already created, exit
        if route_ctx.endpoint:
            return route_ctx

        # Collecting a tuple of all nested Inject classes in the route considering inheritance
        def inject_inherits() -> tuple:
            """
            Collects a tuple of all nested Inject classes in the route considering inheritance.
            This ensures that all dependencies from parent classes are included.
            :return: A tuple of Inject classes.
            """
            inherits = []
            for cl in cls.mro():
                for att in cl.__dict__.values():
                    if inspect.isclass(att) and hasattr(att, '_inject_tags'):
                        # if there are no condition tags in _inject_tags, add it
                        # if there are condition tags and the route tag belongs to one of them, also add it
                        if not att._inject_tags or att._inject_tags & route_ctx.inject_tags:
                            inherits.append(att)
            return tuple(inherits)

        # Collecting signature parameters of the route function and middlewares
        parameters = {
            p.name: (p.name, p.annotation, dataclasses.field(default=p.default))
            for f in (cls.get_bazis_middlewares() + [route_ctx.func])
            for p in inspect.signature(f).parameters.values()
            if isinstance(p.default, DependsCls)
        }

        # collect the final Inject for the route
        route_ctx.Inject = dataclasses.make_dataclass(
            'InjectRoute', parameters.values(), bases=inject_inherits()
        )

        # private endpoint for the current route context
        def endpoint(self, *args, **kwargs):
            """
            Private endpoint for the current route context.
                    This function acts as the actual endpoint that will be called for the route.
            """
            response_middlewares = []

            for middleware in self.get_bazis_middlewares():
                cor = middleware(self, *args, **kwargs)
                next(cor)
                response_middlewares.append(cor)

            result = None
            try:
                result = self.route_run(*args, **kwargs)
            finally:
                for cor in reversed(response_middlewares):
                    try:
                        if res := cor.send(result):
                            result = res
                    except StopIteration:
                        pass
                    else:
                        [_ for _ in cor]

            return result

        # transfer the signature of the real function to the endpoint
        func_sig_transfer(route_ctx.func, endpoint)
        # save the endpoint in the route context
        route_ctx.endpoint = endpoint
        # set the current route context for the endpoint
        route_ctx.endpoint.route_ctx = route_ctx

        # calculate the route name
        if not route_ctx.route_params.name:
            route_ctx.route_params.name = cls.get_name_route(route_ctx.func.__name__)

        # initialize the endpoint
        if route_ctx.endpoint_callbacks:
            for endpoint_callback in route_ctx.endpoint_callbacks:
                endpoint_callback(cls=cls, route_ctx=route_ctx)

        # collect all parameters from Inject
        injects_params = []
        for field in dataclasses.fields(route_ctx.Inject):
            injects_params.append(
                inspect.Parameter(
                    name=field.name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=(
                        field.default
                        if field.default is not dataclasses.MISSING
                        else inspect.Signature.empty
                    ),
                    annotation=field.type,
                )
            )

        # Depends function that creates an instance of the current route.
        # Contains the inject attribute, which includes all dependencies from Inject classes.
        # This Depends will be automatically included in the route function when creating routes
        def route_obj_factory(**kwargs_):
            """
            Depends function that creates an instance of the current route.
            This function includes the inject attribute, which includes all dependencies from Inject classes.
            :return: An instance of the route class with dependencies injected.
            """
            return cls(inject=route_ctx.Inject(**kwargs_), route_ctx=route_ctx)

        func_sig_params_append(route_obj_factory, *injects_params)

        # collect Inject dependencies and add a dependency that creates a route instance.
        # In other dependencies, the route will not be available!
        injects_params_route = list(injects_params) + [
            inspect.Parameter(
                name='self',
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(route_obj_factory),
                annotation=InitialRouteBase,
            )
        ]

        func_sig_params_append(route_ctx.endpoint, *injects_params_route)

        return route_ctx

    @classmethod
    def endpoint_register(cls, router: BazisRouter, route_ctx: RouteContext):
        """
        Register the route in the router defined in the class.
        """
        getattr(router, route_ctx.http_method)(**dataclasses.asdict(route_ctx.route_params))(
            route_ctx.endpoint
        )

        # save the reference to the low-level route in the context
        route_ctx.route = router.routes[-1]

    @classmethod
    def as_router(cls, actions: list | None = None, actions_exclude: list | None = None):
        """
        Determine the list of allowed actions: either explicitly specified or from the
        class.
        """
        actions = actions or cls.actions
        actions_exclude = actions_exclude or cls.actions_exclude

        # set-level router
        router = BazisRouter(tags=cls.tags)
        # pass the prefix from the target class
        if cls.get_url_prefix:
            router.get_url_prefix = cls.get_url_prefix

        routes_install = set()
        # collect registered route contexts
        for route_ctx in cls.routes_ctx.values():
            # if a limited list of actions is passed - check
            if actions and route_ctx.name not in actions:
                continue
            if actions_exclude and route_ctx.name in actions_exclude:
                continue
            # do not register the internal handler
            if route_ctx.name == 'action_internal':
                continue
            # avoid re-registration
            if route_ctx.name in routes_install:
                continue

            routes_install.add(route_ctx.name)

            # create a route from the function
            cls.endpoint_make(route_ctx)

            # register the route in the router defined in the class
            cls.endpoint_register(router, route_ctx)

        return router

    @classmethod
    def url_path_for(cls, name: str, **path_params: Any):
        """
        Generates the URL path for a given route name with specified path parameters.
        :param name: The name of the route.
        :param path_params: The parameters to include in the path.
        :return: The URL path for the route.

        """
        from bazis.core.app import app

        return app.router.url_path_for(cls.get_name_route(name), **path_params)

    @classmethod
    def cls_init(cls):
        """
        Custom initialization logic for the class.
                This method is intended to be overridden by subclasses to provide specific initialization steps.
        """
        ...

    @classmethod
    def raw_call(
        cls, request, path='/', endpoint_callbacks: list[Callable, partial] = None, **kwargs
    ):
        """
        Collect custom action.
        """
        action_internal = dataclasses.replace(
            cls.routes_ctx['action_internal'], endpoint_callbacks=endpoint_callbacks
        )

        # set all passed additional parameters as storage
        if kwargs:
            action_internal.store = kwargs

        # create a route from the function
        cls.endpoint_make(action_internal)

        # fake route registration
        cls.endpoint_register(BazisRouter(route_class=BazisRoute), action_internal)

        # collect scope
        scope = {
            'type': request.scope.get('type'),
            'asgi': request.scope.get('asgi'),
            'http_version': request.scope.get('http_version'),
            'server': request.scope.get('server'),
            'client': request.scope.get('client'),
            'scheme': request.scope.get('scheme'),
            'headers': request.scope.get('headers'),
            'endpoint': action_internal,
            'method': 'INTERNAL',
            'query_string': None,
            'path': path,
            'raw_path': path,
        }

        # collect response
        result = {
            'route': None,
        }

        async def receive():
            """
            Asynchronous function to receive HTTP request data.
                    This function simulates receiving data for the internal route call.
            """
            return {
                'type': 'http.request',
            }

        async def sender(_data):
            """
            Asynchronous function to send HTTP response data.
                    This function simulates sending data for the internal route call.
                    :param _data: The data to send.
            """
            if _data['type'] == 'http.response.body':
                result['route'] = _data['body']

        async_to_sync(action_internal.route.handle)(scope, receive, sender)

        return result['route']

    @classmethod
    def get_context_classes(cls, route_ctx: RouteContext) -> dict[str, type]:
        """
        The method collects a dictionary of classes that can be sources for building jsonapi response data.

            :return: Dictionary of classes.
        """
        response = {}
        for ctx_cls in [cls] + [f.type for f in dataclasses.fields(route_ctx.Inject)]:
            if hasattr(ctx_cls, 'mro'):
                for _cls in reversed(ctx_cls.mro()):
                    response[get_class_name(_cls)] = _cls
        return response

    @cached_property
    def context_sources(self) -> dict[str, Any]:
        """
        The method collects a dictionary of runtime objects created in the context of the current request,
                which contain data for the jsonapi response.

                :return: Dictionary of runtime objects.
        """
        response = {}
        for inst in [self] + [
            getattr(self.inject, f.name) for f in dataclasses.fields(self.inject)
        ]:
            cls = inst.__class__
            if hasattr(cls, 'mro'):
                for _cls in cls.mro():
                    response[get_class_name(_cls)] = inst
        return response

    def __init__(self, *, inject, route_ctx):
        """
        Initializes the route instance with the given inject dependencies and route context.
                :param inject: The injected dependencies for the route.
                :param route_ctx: The context of the route.
        """
        self.inject = inject
        self.route_ctx = route_ctx

    @http_internal('/')
    def action_internal(self, **kwargs):
        """
        Internal action handler for processing custom actions.
        This method allows setting custom attributes and returning a response.
        :param kwargs: Additional parameters to set as attributes.
        :return: A ResponseRouteSet instance.

        """
        for k, v in self.route_ctx.store.items():
            setattr(self, k, v)
        return ResponseRouteSet(self)
