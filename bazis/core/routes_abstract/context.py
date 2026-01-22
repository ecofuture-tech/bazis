import dataclasses
from collections.abc import Callable, Sequence
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi.datastructures import Default
from fastapi.params import Depends as DependsCls
from fastapi.routing import APIRoute
from fastapi.types import IncEx
from fastapi.utils import generate_unique_id

from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute

from pydantic import BaseModel

from bazis.core.schemas.enums import ApiAction


if TYPE_CHECKING:
    from .initial import InitialRouteBase


class EndpointType(Callable):
    """
    Callable type that represents an endpoint function. It includes a reference to
    the RouteContext.

    Tags: RAG
    """

    route_ctx: 'RouteContext'


@dataclasses.dataclass
class RouteParams:
    """
    Data class that contains parameters for a FastAPI route.

    Tags: RAG
    """

    path: str
    response_model: BaseModel | dict | None = None
    status_code: int | None = None
    tags: list[str | Enum] | None = (None,)
    dependencies: Sequence[DependsCls] | None = None
    summary: str | None = None
    description: str | None = (None,)
    response_description: str = 'Successful Response'
    responses: dict[int | str, dict[str, Any]] | None = None
    deprecated: bool | None = None
    operation_id: tuple = (None,)
    response_model_include: IncEx | None = None
    response_model_exclude: IncEx | None = None
    response_model_by_alias: bool = True
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
    response_model_exclude_none: bool = False
    include_in_schema: bool = True
    response_class: type[Response] = dataclasses.field(
        default_factory=lambda: Default(JSONResponse)
    )
    name: str | None = None
    callbacks: list[BaseRoute] | None = None
    openapi_extra: dict[str, Any] | None = None
    generate_unique_id_function: Callable[[APIRoute], str] = dataclasses.field(
        default_factory=lambda: Default(generate_unique_id)
    )


@dataclasses.dataclass
class RouteContext:
    """
    An object of this class is a proxy wrapper for the route function.
    After a method becomes a route through one of the http\_... decorators,
    accessing it returns a RouteContext object.
    This object stores references to the original method, routing parameters,
    the endpoint function, and the route's local storage.
    Each inherited class will have its own RouteContext object.

    Tags: RAG
    """

    #: HTTP method associated with the route
    http_method: str
    #: Reference to the route parameters
    route_params: RouteParams
    #: Set of callbacks invoked during endpoint initialization
    endpoint_callbacks: list[Callable[..., Any] | partial] | None
    #: Tag to be injected into the route
    inject_tags: set[ApiAction] | None
    #: Function with the route logic
    func: Callable[..., Any] | None
    #: Route name
    name: str | None = None
    #: Reference to the router class
    route_cls: type['InitialRouteBase'] | None = None
    #: Final Inject class obtained by merging all Injects from parent classes
    Inject: type[dataclasses.dataclass] | None = None
    #: Function that will be passed as the route function
    endpoint: EndpointType | None = None
    #: Arbitrary route data storage
    store: dict = dataclasses.field(default_factory=dict)
    #: Reference to the fastapi route
    route: BaseRoute | None = None

    def __set_name__(self, owner: type['InitialRouteBase'], name: str):
        """
        If the magic method was called, the route function is a method, initialize the route in it.
        """
        self.route_cls = owner
        self.name = name
        self.route_cls.routes_ctx[self.name] = self
