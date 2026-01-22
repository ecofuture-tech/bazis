from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from starlette.status import HTTP_400_BAD_REQUEST, HTTP_422_UNPROCESSABLE_ENTITY

from bazis.core.errors import SchemaErrors
from bazis.core.routes_abstract.context import RouteContext
from bazis.core.schemas.enums import ApiAction, CrudApiAction
from bazis.core.schemas.fields import SchemaMetaFields
from bazis.core.schemas.meta import get_meta_schemas
from bazis.core.utils.django_types import TYPES_DJANGO_TO_SCHEMA_LOOKUP
from bazis.core.utils.functools import func_sig_param_replace


if TYPE_CHECKING:
    from .route_base import JsonapiRouteBase


def meta_fields_addition(
    cls: type['JsonapiRouteBase'], route_ctx: RouteContext, api_action: ApiAction
):
    """
    Function for adding meta-fields to a JSON:API route based on context classes.
        Extracts meta-fields from the route's context classes and adds them to
        the route class's meta_fields for the specified API action.
        Called as a callback when initializing the route for an API action.

        Example of usage in a route method:
            ```python
            @http_get('/{item_id}/', inject_tags=[CrudApiAction.RETRIEVE], endpoint_callbacks=[
                partial(meta_fields_addition, api_action=CrudApiAction.RETRIEVE),
                partial(api_action_init, api_action=CrudApiAction.RETRIEVE),
                partial(api_action_response_init, api_action=CrudApiAction.RETRIEVE),
                api_action_jsonapi_init,
                item_id_typing,
            ])
            def action_retrieve(self, item_id: str, **kwargs):
                return {
                    'data': self.retrieve(str(item_id).strip()),
                    'meta': self.get_meta_fields(CrudApiAction.RETRIEVE),
                    'included': chain(*self.item.fields_for_included.values()),
                }
            ```

        :param cls: JsonapiRouteBase class
        :param route_ctx: Route context object
        :param api_action: HTTP action within which we extract meta-fields

    Tags: RAG, EXPORT
    """
    # collect information about meta-fields from context classes
    for ctx_cls in cls.get_context_classes(route_ctx).values():
        for name, meta_schema in get_meta_schemas(ctx_cls).items():
            if api_action in meta_schema.api_actions:
                if api_action not in cls.meta_fields:
                    cls.meta_fields[api_action] = SchemaMetaFields()
                cls.meta_fields[api_action].include[name] = meta_schema.field_schema


def build_schema_defaults(cls, api_action: ApiAction):
    """
    Creates and stores default schemas for the specified API action.
        If a schema for the API action already exists, it is not recreated.
        For the UPDATE action, the schema is created by combining the inclusions
        of the schemas for the UPDATE and CREATE actions.
    Schemas are created using the schema factory associated with the route class.
    Used similarly to meta_fields_addition.

    Tags: RAG
    """
    if api_action == CrudApiAction.UPDATE:
        if CrudApiAction.UPDATE not in cls.schema_factories:
            cls.schema_factories[CrudApiAction.UPDATE] = cls.build_schema_factory(
                CrudApiAction.UPDATE
            )
        if CrudApiAction.CREATE not in cls.schema_factories:
            cls.schema_factories[CrudApiAction.CREATE] = cls.build_schema_factory(
                CrudApiAction.CREATE
            )

        if CrudApiAction.UPDATE not in cls.schema_defaults:
            cls.schema_defaults[CrudApiAction.UPDATE] = cls.schema_factories[
                CrudApiAction.UPDATE
            ].build_schema(
                inclusions=(
                    cls.schema_factories[CrudApiAction.UPDATE].inclusions_list
                    + cls.schema_factories[CrudApiAction.CREATE].inclusions_list
                )
            )
    else:
        if api_action not in cls.schema_factories:
            cls.schema_factories[api_action] = cls.build_schema_factory(api_action)
        if api_action not in cls.schema_defaults:
            cls.schema_defaults[api_action] = cls.schema_factories[api_action].build_schema()
            cls.schema_responses_defaults[api_action] = cls.schema_factories[
                api_action
            ].build_schema(is_response_schema=True)


def api_action_init(cls, route_ctx: RouteContext, api_action: ApiAction):
    """
    Triggers building of the default schema for the specified API action.
    Stores the API action in the route context.
    Used similarly to meta_fields_addition.

    Tags: RAG, EXPORT
    """
    build_schema_defaults(cls, api_action)
    route_ctx.store['api_action'] = api_action


def api_action_response_init(cls, route_ctx: RouteContext, api_action: ApiAction):
    """
    Sets the response model for the route based on the default schema.
    Used similarly to meta_fields_addition.

    Tags: RAG, EXPORT
    """
    build_schema_defaults(cls, api_action)
    route_ctx.route_params.response_model = cls.schema_defaults[api_action]
    route_ctx.store['api_action_response'] = api_action


class JsonApiResponse(JSONResponse):
    """
    JSON:API response type with media_type 'application/vnd.api+json'.

    Tags: RAG, EXPORT
    """

    media_type = 'application/vnd.api+json'


def api_action_jsonapi_init(cls, route_ctx: RouteContext):
    """
    Converts the route into a JSON:API route by setting the appropriate response class
    and exception parameters for the response model.
    Used similarly to meta_fields_addition.

    Tags: RAG, EXPORT
    """
    # without this setting, fields removed from the private schema with a value of null
    # are included in the output attributes
    route_ctx.route_params.response_model_exclude_unset = True
    route_ctx.route_params.response_class = JsonApiResponse
    route_ctx.route_params.responses = {
        HTTP_400_BAD_REQUEST: {'model': SchemaErrors},
        HTTP_422_UNPROCESSABLE_ENTITY: {'model': SchemaErrors},
    }


def item_data_typing(cls, route_ctx: RouteContext, api_action: ApiAction):
    """
    Replaces the item_data parameter annotation with the default schema for the API action.
    Used similarly to meta_fields_addition.

    Tags: RAG, EXPORT
    """
    func_sig_param_replace(
        route_ctx.endpoint, 'item_data', annotation=cls.schema_defaults[api_action]
    )


def item_id_typing(cls, route_ctx: RouteContext):
    """
    Replaces the item_id parameter annotation with the primary key type from the read schema.
    Used similarly to meta_fields_addition.

    Tags: RAG, EXPORT
    """
    func_sig_param_replace(
        route_ctx.endpoint,
        'item_id',
        annotation=TYPES_DJANGO_TO_SCHEMA_LOOKUP[cls.model._meta.pk],
    )


def crud_jsonapi_callbacks(api_action: CrudApiAction) -> list[Callable]:
    """
    Returns a list of endpoint callbacks for the given CrudApiAction.

    Replaces the standard JSONResponse with JsonApiResponse, which has media_type = 'application/vnd.api+json'.
    Adds descriptions of 400 and 422 errors to the OpenAPI documentation (SchemaErrors).
    Removes fields with the value None from the response — in JSON:API they must not be present.

    Tags: RAG
    """
    callbacks = [api_action_jsonapi_init]

    if api_action != CrudApiAction.DESTROY:
        callbacks.extend(
            [
                # adding meta, in most cases pagination for a list, but it can be an addition to any schema
                partial(meta_fields_addition, api_action=api_action),
                # building a schema for api_action
                partial(api_action_init, api_action=api_action),
                # setting the response model
                partial(
                    api_action_response_init,
                    api_action=(
                        api_action if api_action is CrudApiAction.LIST else CrudApiAction.RETRIEVE
                    ),
                ),
            ]
        )

    if api_action in {CrudApiAction.CREATE, CrudApiAction.UPDATE}:
        # create and update have a request body
        # therefore it is necessary to substitute a specific Pydantic schema of the request body into the route signature,
        # so that everything is validated correctly and displayed in Swagger
        callbacks.append(partial(item_data_typing, api_action=api_action))

    if api_action in {CrudApiAction.RETRIEVE, CrudApiAction.UPDATE, CrudApiAction.DESTROY}:
        #  clarification of the item_id parameter type in the route signature based on the RETRIEVE schema
        #  substitutes the type of the primary key field (usually str, int, UUID, etc.),
        #  so that FastAPI correctly validates item_id when it is passed in the path
        callbacks.append(item_id_typing)

    return callbacks
