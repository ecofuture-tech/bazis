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

import traceback
from itertools import chain
from typing import Any, List, TypeVar, get_type_hints  # noqa: UP035

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.db.models.deletion import PROTECT, ProtectedError
from django.db.utils import IntegrityError
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from fastapi import Body, Depends, HTTPException, Request
from fastapi.datastructures import DefaultPlaceholder
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from pydantic import BaseModel, ValidationError

from bazis.core.errors import (
    JsonApi403Exception,
    JsonApiBazisError,
    JsonApiBazisException,
    JsonApiHttpException,
    JsonApiItemInvalidException,
    JsonApiRequestValidationError,
    SchemaErrors,
)
from bazis.core.item_validation import defer_validate_item
from bazis.core.models_abstract import JsonApiMixin
from bazis.core.routes_abstract.context import RouteContext
from bazis.core.routes_abstract.initial import (
    InitialRouteBase,
    http_delete,
    http_get,
    http_patch,
    http_post,
    inject_make,
)
from bazis.core.schemas.enums import ApiAction, CrudAccessAction, CrudApiAction, RouteKind
from bazis.core.schemas.factory import SchemaFactory
from bazis.core.schemas.fields import (
    CallableContext,
    SchemaField,
    SchemaFields,
    SchemaInclusions,
    SchemaMetaFields,
)
from bazis.core.schemas.schemas import JsonApiDataSchema
from bazis.core.services.filtering import ServiceFiltering
from bazis.core.services.includes import include_to_list
from bazis.core.services.meta_fields import meta_to_list
from bazis.core.services.pagination import ServicePagination
from bazis.core.services.searching import ServiceSearching
from bazis.core.services.sorting import SortingSearching
from bazis.core.services.sparse_fieldsets import ServiceSparseFieldsets
from bazis.core.utils.functools import get_attr
from bazis.core.utils.orm import calc_cached_property
from bazis.core.utils.query_complex import QueryScope

from ...services.relationships import RelationshipsService
from .cache import with_cache_openapi_schema
from .callbacks import crud_jsonapi_callbacks
from .schemas import FieldListModel, RelationshipData, openapi_relationship_examples
from .schemas_dict import SchemasDict, SchemasResponseDict
from .services import RouteFilterFieldsService


SchemaStructT = TypeVar('SchemaStructT')
SchemaCreateT = TypeVar('SchemaCreateT')
SchemaUpdateT = TypeVar('SchemaUpdateT')


class JsonapiRouteBase(InitialRouteBase):
    """
    Base class for JSON:API routes, implementing main CRUD operations and adhering
    to the JSON:API specification.
    Used in every JSON:API route to provide standard CRUD operations, as well as
    to implement the core Bazis functionality.

    Tags: RAG, EXPORT
    """

    abstract: bool = True
    model: type[JsonApiMixin] = None
    fields: dict[ApiAction, SchemaFields] = None
    inclusions: dict[ApiAction, SchemaInclusions] = None
    meta_fields: dict[ApiAction, SchemaMetaFields] = None
    search_fields: list[str] = None
    filters_aliases: dict[str, str] = {}

    item: JsonApiMixin | None = None
    schema_defaults: dict[ApiAction, type[BaseModel]] = None
    schema_responses_defaults: dict[ApiAction, type[BaseModel]] = None
    schema_factories: dict[ApiAction, SchemaFactory] = None
    schemas: dict[ApiAction, type[BaseModel]] = None
    schemas_responses: dict[ApiAction, type[BaseModel]] = None
    relationships_service: RelationshipsService = RelationshipsService

    #: the route is the default route of its model (`JsonApiMixin.get_default_route`), whose
    #: `restrict_queryset` restricts the objects of the model in the relationships and
    #: `included` of the other routes. Declared in the class body, it is not inherited.
    #: Without it the last defined route class of the model is the default one.
    default_route: bool = False

    #: the relationships of a created or changed item link only the objects the default
    #: route of the related model shows (`relations_access_check`); False turns it off
    relation_targets_check: bool = True

    @inject_make()
    class InjectJsonApi:
        """
        Dependency injection class for injecting meta information into JSON:API routes.
        """

        meta: str | None = Depends(meta_to_list)

    @inject_make(CrudApiAction.LIST)
    class InjectForList:
        """
        Dependency injection class for injecting filtering, searching, pagination, and
        sorting services into LIST CRUD API actions.
        """

        filtering: ServiceFiltering = Depends()
        searching: ServiceSearching = Depends()
        pagination: ServicePagination = Depends()
        sorting: SortingSearching = Depends()

    @inject_make(CrudApiAction.RETRIEVE, CrudApiAction.LIST)
    class InjectOnlyFields:
        """
        Dependency injection class for injecting sparse_fieldsets service.
        """

        sparse_fieldsets: ServiceSparseFieldsets = Depends()

    def __init_subclass__(cls, **kwargs):
        """
        Dynamically create InjectOnlyFieldsList and InjectOnlyFieldsRetrieve.
        """
        super().__init_subclass__(**kwargs)

        if cls.model:
            cls.InjectOnlyFieldsList, cls.InjectOnlyFieldsRetrieve = (
                ServiceSparseFieldsets.create_inject_class(cls)
            )

    @inject_make(CrudApiAction.RETRIEVE, CrudApiAction.UPDATE, CrudApiAction.CREATE)
    class InjectInclude:
        """
        Dependency injection class for injecting include parameters into RETRIEVE,
        UPDATE, and CREATE CRUD API actions.
        """

        include: str | None = Depends(include_to_list)

    @classmethod
    def cls_init(cls):
        """
        Class-level initialization method for setting up schema factories, defaults, and
        other configurations.

        Tags: RAG, INTERNAL
        """
        super().cls_init()

        cls.fields = cls.fields or {}
        cls.inclusions = cls.inclusions or {}
        cls.meta_fields = cls.meta_fields or {}
        # calculated data sets
        cls.schema_factories = {}
        cls.schema_defaults = {}
        cls.schema_responses_defaults = {}
        cls.schemas = {}
        cls.schemas_responses = {}
        cls.search_fields = cls.search_fields or []

        for rc in cls.routes_ctx.values():
            # Get the original function and extract type hints
            original_func = rc.func
            return_type = get_type_hints(original_func).get('return', None)

            if return_type:
                rc.route_params.response_model = return_type
            else:
                # If endpoint_callbacks are not passed, but the CrudApiAction tag is passed — generate callbacks automatically
                if (
                    rc.endpoint_callbacks is None
                    and rc.inject_tags is not None
                    and len(rc.inject_tags) == 1
                ):
                    tag = next(iter(rc.inject_tags))
                    if isinstance(tag, CrudApiAction):
                        rc.endpoint_callbacks = list(crud_jsonapi_callbacks(tag))

        if not issubclass(cls.model, JsonApiMixin):
            raise Exception(
                _(
                    f'The model used in routing ({cls.model.__name__}) must be a subclass of JsonApiMixin'
                )
            )

        # save the default route: an explicit one (`default_route` in the class body) is
        # replaced only by another explicit one
        current = cls.model.__dict__.get('_default_route')
        if vars(cls).get('default_route') or not (
            current and vars(current).get('default_route')
        ):
            cls.model._default_route = cls

        # for proxy models, create/update actions are not available, as they can change the state
        # of the visibility of proxy model objects
        if cls.model._meta.proxy:
            cls.actions_exclude = cls.actions_exclude or []
            cls.actions_exclude.extend(['action_create', 'action_update'])

    @classmethod
    def route_responses(cls, route_ctx: RouteContext) -> dict[int | str, dict[str, Any]]:
        """
        Adds the errors the core routes fail with: 404 for a route of an item (`item_id` in
        the path, the item is not found) and 403 for a route of a relationship (the
        relationship is read-only or the objects violate its restrictions).
        """
        responses = super().route_responses(route_ctx)
        if '{item_id}' in route_ctx.route_params.path:
            responses[HTTP_404_NOT_FOUND] = {'model': SchemaErrors}
        if route_ctx.kind is RouteKind.RELATIONSHIP:
            responses[HTTP_403_FORBIDDEN] = {'model': SchemaErrors}
        return responses

    @classmethod
    def get_url_prefix(cls) -> str:
        """
        Returns the URL prefix for the route based on the model's resource path.
        """
        return f'/{cls.model.get_resource_path()}'

    @classmethod
    def build_schema_attrs(
        cls, api_action: ApiAction, attr_name: str, schema_type: type[SchemaStructT]
    ) -> SchemaStructT:
        """
        Builds schema attributes for the given API action and attribute name,
        aggregating attributes from the class hierarchy.

        Tags: RAG, INTERNAL
        """
        assert isinstance(getattr(cls, attr_name), dict)

        attrs_list = []
        for _cls in cls.mro():
            # look for a specific action, and a general one (with the key None)
            for _action in (api_action, None):
                attrs = (getattr(_cls, attr_name, None) or {}).get(_action, None)
                if attrs:
                    # assert isinstance(attrs, schema_type)
                    attrs_list.append(attrs)
                    if not attrs.is_inherit:
                        break

        # create a new list of schema fields
        schema_attrs = schema_type()
        for attrs in reversed(attrs_list):
            if attrs.origin:
                schema_attrs.origin = dict(attrs.origin)
            schema_attrs.include.update(attrs.include)
            schema_attrs.exclude.update(attrs.exclude)

        return schema_attrs

    @classmethod
    def build_schema_factory(cls, api_action: ApiAction):
        """
        Creates and returns a SchemaFactory for the given API action.

        Tags: RAG, INTERNAL
        """
        return SchemaFactory(
            route_cls=cls,
            model=cls.model,
            api_action=api_action,
            fields_struct=cls.build_schema_attrs(api_action, 'fields', SchemaFields),
            inclusions_struct=cls.build_schema_attrs(api_action, 'inclusions', SchemaInclusions),
            meta_fields_struct=cls.build_schema_attrs(api_action, 'meta_fields', SchemaMetaFields),
        )

    def set_route(self, route: 'JsonapiRouteBase'):
        """
        Sets the current route instance in the JsonApiMixin context.

        Tags: RAG, INTERNAL
        """
        JsonApiMixin.CTX_ROUTE.set(route)

    def set_api_action(self, api_action: ApiAction | None):
        """
        Sets the current API action in the JsonApiMixin context.
        """
        if api_action:
            JsonApiMixin.CTX_API_ACTION.set(api_action)

    def __init__(self, *args, **kwargs):
        """
        Initializes the JsonapiRouteBase instance, setting the route and API action
        contexts.
        """
        super().__init__(*args, **kwargs)
        self.set_route(self)
        self.set_api_action(self.route_ctx.store.get('api_action'))
        self.schemas = SchemasDict(type(self), getattr(self.inject, 'include', []))
        self.schemas_responses = SchemasResponseDict(
            type(self), getattr(self.inject, 'include', []), True
        )

    @classmethod
    def get_fiter_context(cls, route: 'JsonapiRouteBase' = None, **kwargs):
        """
        Returns a context dictionary for filtering, including the current route
        instance.
        """
        return {
            'route': route,
        }

    @classmethod
    def query_fields(cls, user=None, **kwargs) -> list[SchemaField]:
        """
        The fields of the LIST schema of the route for the user: the keys of `filter`
        (the fields that can filter) and `sort` (that can order) of a request start with
        one of them (their source), and the search fields of the route must be among them.
        A relation of them leads into the fields of the default route of the related model.
        A package that changes the LIST schema per user overrides it (accept `**kwargs`).
        """
        factory = cls.schema_factories.get(CrudApiAction.LIST)
        if factory is None:
            # a route without the list action, e.g. the default route of a related model
            if (factory := vars(cls).get('_query_schema_factory')) is None:
                factory = cls._query_schema_factory = cls.build_schema_factory(
                    CrudApiAction.LIST
                )
        return factory.fields_list

    def query_scope(self) -> QueryScope | None:
        """
        What the filter, the sorting and the search of the request may reach
        (`QueryScope.for_route` with the user of the route), or None when
        `BAZIS_FILTERS_STRICT` is off (transitional: not restricted, as before 2.9).
        """
        if not settings.BAZIS_FILTERS_STRICT:
            return None
        if (scope := vars(self).get('_query_scope')) is None:
            scope = self._query_scope = QueryScope.for_route(
                type(self), user=getattr(self.inject, 'user', None)
            )
        return scope

    def route_run(self, *args, **kwargs):
        """
        Executes the route, wrapping the endpoint execution in a transaction and
        handling validation and HTTP exceptions.

        Tags: RAG, INTERNAL
        """
        response_class = self.route_ctx.route_params.response_class
        if isinstance(response_class, DefaultPlaceholder):
            response_class = response_class.value
        else:
            response_class = response_class

        self.set_route(self)
        self.set_api_action(self.route_ctx.store.get('api_action'))

        # execute the entire endpoint in a single transaction
        with transaction.atomic(savepoint=False):
            try:
                data = super().route_run(*args, **kwargs)

                # for the standard case when the endpoint defines the schema by the api_action type
                if not isinstance(data, Response) and 'api_action_response' in self.route_ctx.store:
                    schema_response = self.schemas_responses.get(
                        self.route_ctx.store['api_action_response']
                    )

                    if schema_response:
                        validate_data = schema_response.model_validate(data)
                        content = jsonable_encoder(validate_data, exclude_unset=True)

                        return response_class(
                            content,
                            status_code=get_attr(self.route_ctx.route, 'status_code') or 200,
                        )
            except ValidationError as e:
                traceback.print_exc()
                # intercepts validation exception and generates its own exception
                raise JsonApiRequestValidationError(e.errors()) from e
            except JsonApiHttpException:
                # already a JSON:API error: keep its code (JsonApi403Exception: ERR_FORBIDDEN)
                raise
            except HTTPException as e:
                # intercepts the general exception and generates its own exception
                raise JsonApiHttpException(
                    status_code=e.status_code, detail=e.detail, headers=e.headers
                ) from e
            return data

    @http_get('/schema_list/', response_model=dict[str, Any], kind=RouteKind.SCHEMA)
    def action_schema_list(self, **kwargs):
        return with_cache_openapi_schema(self.schemas[CrudApiAction.LIST])

    @http_get('/schema_create/', response_model=dict[str, Any], kind=RouteKind.SCHEMA)
    def action_schema_create(
        self,
        include: str | None = Depends(include_to_list),
        **kwargs,
    ):
        return with_cache_openapi_schema(self.schemas[CrudApiAction.CREATE])

    @http_get('/{item_id}/schema_retrieve/', response_model=dict[str, Any], kind=RouteKind.SCHEMA)
    def action_schema_retrieve(
        self,
        item_id: str,
        include: str | None = Depends(include_to_list),
        **kwargs,
    ):
        self.set_api_action(CrudApiAction.RETRIEVE)
        self.set_item(item_id)
        return with_cache_openapi_schema(self.schemas[CrudApiAction.RETRIEVE])

    @http_get('/{item_id}/schema_update/', response_model=dict[str, Any], kind=RouteKind.SCHEMA)
    def action_schema_update(
        self,
        item_id: str,
        include: str | None = Depends(include_to_list),
        **kwargs,
    ):
        self.set_api_action(CrudApiAction.UPDATE)
        self.set_item(item_id)
        return with_cache_openapi_schema(self.schemas[CrudApiAction.UPDATE])

    @http_get('/route_filter_fields/', response_model=FieldListModel, kind=RouteKind.SCHEMA)
    def get_route_filter_fields(self, **kwargs):
        """
        Return a list of filterable fields for the current route.

        This endpoint is used to inform frontend filtering interfaces about which fields
        can be used in filters and what types they are (OpenAPI-style).
        """
        fields = RouteFilterFieldsService.get_fields(self)
        return FieldListModel(fields=fields)

    @http_get(
        '/_id/',
        endpoint_callbacks=[],
        inject_tags=[CrudApiAction.LIST],
    )
    def action_list_id(self, **kwargs) -> List[str]:  # noqa: UP006
        """
        Handles the HTTP GET request to list items.
        """
        return self.list_id()

    @http_get(
        '/',
        inject_tags=[CrudApiAction.LIST],
        kind=RouteKind.COLLECTION,
    )
    def action_list(self, **kwargs):
        """
        Handles the HTTP GET request to list items.
        """
        return {
            'data': self.list(),
            'meta': self.get_meta_fields(CrudApiAction.LIST),
            'links': self.get_links(CrudApiAction.LIST),
        }

    @http_get(
        '/{item_id}/',
        inject_tags=[CrudApiAction.RETRIEVE],
        kind=RouteKind.ITEM,
    )
    def action_retrieve(self, item_id: str, **kwargs):
        """
        Handles the HTTP GET request to retrieve a single item by its ID.
        """
        data = self.retrieve(str(item_id).strip())
        data.only_fields = getattr(
            self.inject, f'fields_{self.model.get_resource_label().replace(".", "_")}'
        )
        meta = self.get_meta_fields(CrudApiAction.RETRIEVE)
        included = []
        for queryset in self.item.fields_for_included.values():
            for item in queryset:
                item.only_fields = getattr(
                    self.inject, f'fields_{queryset.model.get_resource_label().replace(".", "_")}'
                )
                included.append(item)
        return {
            'data': data,
            'meta': meta,
            'included': included,
        }

    @http_post(
        '/',
        status_code=201,
        inject_tags=[CrudApiAction.CREATE],
        kind=RouteKind.CREATE,
    )
    def action_create(
        self,
        request: Request,
        item_data: SchemaCreateT = Body(..., media_type='application/vnd.api+json'),
        **kwargs,
    ):
        """
        Handles the HTTP POST request to create a new item.
        """
        item = self.create(request._json, item_data)
        result = {
            'data': self.retrieve(str(item.id).strip(), is_force=True),
            'meta': self.get_meta_fields(CrudApiAction.RETRIEVE),
            'included': chain(*self.item.fields_for_included.values()),
        }
        return result

    @http_patch(
        '/{item_id}/',
        inject_tags=[CrudApiAction.UPDATE],
        kind=RouteKind.UPDATE,
    )
    def action_update(
        self,
        item_id: str,
        request: Request,
        item_data: SchemaUpdateT = Body(..., media_type='application/vnd.api+json'),
        **kwargs,
    ):
        """
        Handles the HTTP PATCH request to update an existing item by its ID.
        """
        item = self.update(str(item_id).strip(), request._json, item_data)
        return {
            'data': self.retrieve(str(item.id).strip(), is_force=True),
            'meta': self.get_meta_fields(CrudApiAction.RETRIEVE),
            'included': chain(*self.item.fields_for_included.values()),
        }

    @http_post(
        '/{item_id}/relationships/{related_field_name}',
        status_code=204,
        kind=RouteKind.RELATIONSHIP,
    )
    def action_post_relationships(
        self,
        item_id: str,
        related_field_name: str,
        relationships_data: RelationshipData = Body(
            ..., openapi_examples=openapi_relationship_examples
        ),
        **kwargs,
    ):
        """
        Handles the HTTP POST request to add relationships.
        """
        if relationships_data.data:
            self.relationships_change('add', item_id, related_field_name, relationships_data)
        return Response(status_code=204)

    @http_patch(
        '/{item_id}/relationships/{related_field_name}',
        status_code=204,
        kind=RouteKind.RELATIONSHIP,
    )
    def action_update_relationships(
        self,
        item_id: str,
        related_field_name: str,
        relationships_data: RelationshipData = Body(
            ..., openapi_examples=openapi_relationship_examples
        ),
        **kwargs,
    ):
        """
        Handles the HTTP PATCH request to update relationships.
        """
        self.relationships_change('set', item_id, related_field_name, relationships_data)
        return Response(status_code=204)

    @http_delete(
        '/{item_id}/relationships/{related_field_name}',
        status_code=204,
        kind=RouteKind.RELATIONSHIP,
    )
    def action_delete_relationships(
        self,
        item_id: str,
        related_field_name: str,
        relationships_data: RelationshipData = Body(
            ..., openapi_examples=openapi_relationship_examples
        ),
        **kwargs,
    ):
        """
        Handles the HTTP DELETE request to remove relationships.
        """
        if relationships_data.data:
            self.relationships_change('remove', item_id, related_field_name, relationships_data)
        return Response(status_code=204)

    @http_delete(
        '/{item_id}/', inject_tags=[CrudApiAction.DESTROY], status_code=204, kind=RouteKind.DELETE
    )
    def action_destroy(self, item_id: str, **kwargs):
        """
        Handles the HTTP DELETE request to delete an item by its ID.
        """
        self.destroy(str(item_id).strip())

    @http_get(
        '/{item_id}/dict_data/',
    )
    def action_dict_data(self, item_id: str, **kwargs):
        """
        Handles the HTTP GET request to retrieve the dictionary representation of an item.
        """
        return self.set_item(item_id).dict_data

    def get_links(self, api_action: ApiAction):
        """
        Generates and returns pagination links for the list action.
        """
        if api_action == CrudApiAction.LIST:
            if self.inject.pagination:
                return self.inject.pagination.links
        return {}

    def get_meta_fields(self, api_action: ApiAction) -> dict:
        """
        Generates and returns meta fields for the specified API action.
        """
        meta_fields = {}
        for f_name, field in self.schema_factories[api_action].meta_fields.items():
            if f_name not in self.inject.meta:
                continue

            meta_value = None

            if isinstance(field.source, CallableContext):
                source = self.context_sources[field.source.class_path]
                # get the value of the data source
                source_attr = getattr(source, field.source.attr)

                if callable(source_attr):
                    meta_value = source_attr()
                else:
                    meta_value = source_attr
            elif callable(field.source):
                meta_value = field.source(self)
            elif isinstance(field.source, str) and hasattr(self, field.source):
                meta_value = getattr(self, field.source)

            # try to get the value of the meta-field from the route instance
            meta_fields[f_name] = meta_value

        return meta_fields

    def get_queryset(self) -> QuerySet:
        """
        Assembles the most basic QuerySet for the current model.
                Override this method to add any basic restrictions or optimizations.
        """
        return self.model.objects.all()

    def get_queryset_for_response(self) -> QuerySet:
        """
        Passes all dependencies declared as calc_property to the base queryset.
        """

        queryset = self.get_queryset()

        # Check if an API action is defined
        if (api_action := self.route_ctx.store.get('api_action_response')) is None:
            return queryset

        if not hasattr(queryset, 'relation_field'):
            return queryset

        schema_factory = self.schema_factories[api_action]
        context = self.get_fiter_context(route=self)

        simple_fields_names, calc_fields_names, relation_fields_names = (
            (self.inject.sparse_fieldsets.get_fields_for_queryset(queryset, inject=self.inject))
            if hasattr(self.inject, 'sparse_fieldsets')
            else (None, None, None)
        )
        if simple_fields_names is not None:
            queryset = queryset.only(*simple_fields_names)
        if calc_fields_names is None:
            calc_fields_names = []
            for k, _v in schema_factory.fields.items():
                if type(getattr(queryset.model, k, None)) is calc_cached_property:
                    calc_fields_names.append(k)
        queryset = queryset.relation_field(
            context,
            fields_allowed=schema_factory.fields.keys()
            if relation_fields_names is None
            else relation_fields_names,
        ).calc_fields(calc_fields_names, context)
        return queryset

    def get_queryset_for_list(self):
        """
        Assembles the QuerySet taking into account search and filtering.
                Override this method if the route adds additional restrictions.
                Note: Pagination is not applied in this method.
        """
        qs = self.inject.searching.apply(
            self.inject.filtering.apply(
                self.get_queryset_for_response(),
                filters_aliases=self.filters_aliases,
                fiter_context=self.get_fiter_context(route=self),
            )
        )
        return qs

    def get_queryset_for_item(self, item_id: str, with_lock: bool = False):
        """
        Assembles the QuerySet for a single item by its ID, optionally with a database
        lock. An ID that cannot be a primary key of the model (a malformed UUID) is an item
        that does not exist: 404, on every route of an item.
        """
        try:
            item_id = self.model._meta.pk.to_python(item_id)
        except DjangoValidationError:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=_('Item not found')) from None
        if with_lock:
            qs = self.get_queryset().select_for_update(no_key=True)
        else:
            qs = self.get_queryset_for_response()
        return qs.filter(id=item_id)

    def get_item(self, item_id: str):
        """
        Fetches and returns a single item by its ID. Raises an HTTP 404 exception if the
        item is not found.
        """
        item = self.get_queryset_for_item(item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail=_('Item not found'))
        return item

    def set_item(
        self, item_id: str, with_lock: bool = False, is_force: bool = False
    ) -> JsonApiMixin:
        """
        If the instance is already set, do not override anything. sets the item for the
        current route context.
        """
        qs = self.get_queryset_for_item(item_id, with_lock)
        only_fields = getattr(
            self.inject, f'fields_{qs.model.get_resource_label().replace(".", "_")}', None
        )
        if self.item and not is_force and only_fields is None:
            return self.item
        self.item = qs.first()
        if not self.item:
            raise HTTPException(status_code=404, detail=_('Item not found'))
        self.item.only_fields = only_fields
        return self.item

    def relationships_change(
        self,
        action: str,
        item_id: str,
        related_field_name: str,
        relationships_data: RelationshipData,
    ):
        """
        Changes a relationship of an item (the relationships endpoints) with the same
        checks as an update of the item: the item is taken through the route, the
        relationship must be writable in the update schema of the route (for this user),
        the `filter:` restrictions of the field apply, and the hooks
        `hook_before_relationships_change` / `hook_after_relationships_change` run inside
        the transaction. The item is validated (`validate_item`, source `relationships`)
        at the end; the errors of the validation of the items the change writes point to
        the path parameter `/related_field_name`.
        """
        try:
            with defer_validate_item(user=self._write_user(), savepoint=False) as scope:
                self.set_api_action(CrudApiAction.UPDATE)
                item = self.set_item(str(item_id).strip())

                data = self.relationships_validate(item, related_field_name, relationships_data)
                self.relations_access_check(data, item, action)
                self.relationships_restricts_check(item, data, related_field_name, action)

                self.hook_before_relationships_change(item, data, related_field_name, action)
                self.relationships_service.apply_relationship_action(
                    action=action,
                    model=self.model,
                    item_id=str(item.pk),
                    related_field_name=related_field_name,
                    relationships_data=relationships_data,
                )
                item.refresh_from_db()
                info = item.get_fields_info().relations[related_field_name]
                scope.mark(
                    item,
                    'relationships',
                    relations=[related_field_name] if info.to_many or info.reverse else [],
                    user=self._write_user(),
                )
                self.hook_after_relationships_change(item, data, related_field_name, action)
        except JsonApiItemInvalidException as e:
            # the request names only the relation of the path: the errors point to it
            raise JsonApiItemInvalidException(e.error, item=e.item, source='relationships') from e

    def relationships_validate(
        self, item: JsonApiMixin, related_field_name: str, relationships_data: RelationshipData
    ) -> JsonApiDataSchema:
        """
        Validates the relationship data with the update schema of the route and returns
        the validated item data. Fails with 403 `ERR_RELATIONSHIP_READONLY` if the
        relationship is not writable: absent from the update schema or read-only in it.
        """
        schema = self.schemas.get(CrudApiAction.UPDATE)
        if schema is None:
            raise JsonApi403Exception()

        item_raw = {
            'data': {
                'id': str(item.pk),
                'type': self.model.get_resource_label(),
                'bs:action': CrudAccessAction.CHANGE.value,
                'relationships': {
                    related_field_name: relationships_data.model_dump(mode='json'),
                },
            }
        }
        try:
            item_data = schema.model_validate(item_raw)
        except ValidationError as e:
            raise RequestValidationError(e.errors(), body=item_raw) from e

        # a relationship missing from the schema, or read-only in it (the schema keeps a
        # read-only field and `readonly_validator` drops its value), is not set
        relationships = item_data.data.relationships
        if relationships is None or related_field_name not in relationships.model_fields_set:
            raise JsonApiBazisException(
                JsonApiBazisError(
                    detail=format_lazy(
                        _('The relationship {name} cannot be changed'), name=related_field_name
                    ),
                    loc=('path', 'related_field_name'),
                    code='ERR_RELATIONSHIP_READONLY',
                    title=_('Relationship is read-only'),
                    status=403,
                ),
                status=403,
            )
        return item_data.data

    def relations_access_check(
        self, data: JsonApiDataSchema, item: JsonApiMixin | None = None, action: str = 'set'
    ):
        """
        Checks that the relationships of the item data link only the objects the default
        route of the related model shows (its `restrict_queryset` with this user): a
        relationship links the objects the user can view, a reverse relationship changes
        the foreign key of the objects it links and unlinks, so they must be changeable.
        For a changed item only the objects whose link changes are checked; `action` is the
        action of the relationships endpoints (`add`, `remove`, `set`; an update sets the
        value). The models whose route does not restrict them are not queried. Fails with
        403 `ERR_RELATION_ACCESS`; `relation_targets_check = False` turns the check off.
        """
        if self.relation_targets_check is False or not getattr(data, 'relationships', None):
            return

        # the mixin module imports this one
        from .mixins import route_restrict_queryset

        model = type(item) if item is not None else JsonApiMixin.get_model_by_label(data.type)
        relations = model.get_fields_info().relations
        user = getattr(self.inject, 'user', None)

        for f_name, value in data.relationships.model_dump(exclude_unset=True).items():
            if not (field_info := relations.get(f_name)):
                continue
            rel_model = field_info.related_model
            if not (restrict := route_restrict_queryset(rel_model)):
                continue

            rel_data = (value or {}).get('data')
            if not isinstance(rel_data, list):
                rel_data = [rel_data] if rel_data else []
            # normalized as the primary keys of the database (e.g. a UUID in upper case)
            ids = {
                str(self.relationships_service._parse_id(it['id'], rel_model))
                for it in rel_data
                if it and it.get('id') is not None
            }
            unlinked = set()
            if item is not None:
                if field_info.to_many:
                    current = {str(pk) for pk in getattr(item, f_name).values_list('pk', flat=True)}
                elif not field_info.reverse:
                    pk = getattr(item, field_info.model_field.attname, None)
                    current = {str(pk)} if pk is not None else set()
                elif current_obj := getattr(item, f_name, None):
                    current = {str(current_obj.pk)}
                else:
                    current = set()

                if action == 'remove':
                    # removing a to-one relation clears it whatever the request refers to
                    ids, unlinked = set(), (ids & current if field_info.to_many else current)
                elif action == 'add':
                    ids -= current
                else:
                    ids, unlinked = ids - current, current - ids

            if field_info.reverse:
                ids, access_action = ids | unlinked, CrudAccessAction.CHANGE
            else:
                access_action = CrudAccessAction.VIEW
            if not ids:
                continue

            allowed = restrict(rel_model.objects.filter(pk__in=ids), access_action, user=user)
            if ids - {str(pk) for pk in allowed.values_list('pk', flat=True)}:
                raise JsonApiBazisException(
                    JsonApiBazisError(
                        detail=format_lazy(
                            _('No access to the related object of {name}'), name=f_name
                        ),
                        loc=('body', 'data', 'relationships', f_name),
                        code='ERR_RELATION_ACCESS',
                        title=_('Access denied'),
                        status=403,
                    ),
                    status=403,
                )

    def relationships_restricts_check(
        self, item: JsonApiMixin, data: JsonApiDataSchema, related_field_name: str, action: str
    ):
        """
        Applies the `filter:` restrictions of the field: the objects the action links and
        unlinks must match them (an update keeps the linked objects that do not match).
        """
        field_info = item.get_fields_info().relations[related_field_name]
        value = data.relationships.model_dump(exclude_unset=True)[related_field_name]
        rel_model = field_info.related_model

        if field_info.to_many:
            # normalized as the primary keys of the database (e.g. a UUID in upper case)
            ids = {
                str(self.relationships_service._parse_id(it['id'], rel_model))
                for it in (value.get('data') or [])
            }
            if action == 'set':
                current = getattr(item, related_field_name).values_list('pk', flat=True)
                ids ^= {str(pk) for pk in current}
            if not ids:
                return
            touched = {'data': [{'id': pk} for pk in ids]}
            allowed = data.check_restrict_m2m(related_field_name, touched, rel_model)
            allowed_ids = {str(pk) for pk in allowed.values_list('pk', flat=True)}
            if ids - allowed_ids:
                raise JsonApi403Exception()
        else:
            f_pk = None if action == 'remove' else (value.get('data') or {}).get('id')
            if not data.check_restrict_rel(related_field_name, f_pk, rel_model, instance=item):
                raise JsonApi403Exception()

    def hook_before_relationships_change(
        self, item: JsonApiMixin, data: JsonApiDataSchema, related_field_name: str, action: str
    ):
        """
        Hook method called before a relationship of the item is changed through the
        relationships endpoints. Can be overridden to add custom checks.
        """
        pass

    def hook_after_relationships_change(
        self, item: JsonApiMixin, data: JsonApiDataSchema, related_field_name: str, action: str
    ):
        """
        Hook method called after a relationship of the item is changed through the
        relationships endpoints (inside the transaction).
        """
        pass

    def hook_before_create(self, item: JsonApiMixin):
        """
        Hook method called before creating an item. Can be overridden to add custom
        logic.
        """
        pass

    def hook_after_create(self, item: JsonApiMixin):
        """
        Hook method called after creating an item. Can be overridden to add custom
        logic.
        """
        pass

    def hook_before_update(self, item: JsonApiMixin):
        """
        Hook method called before updating an item. Can be overridden to add custom
        logic.
        """
        pass

    def hook_after_update(self, item: JsonApiMixin):
        """
        Hook method called after updating an item. Can be overridden to add custom
        logic.
        """
        pass

    def _write_user(self):
        """
        The user the writes of the route are validated with (`ItemChanges.user`).
        """
        return getattr(self.inject, 'user', None)

    @staticmethod
    def _write_relations(model: type[JsonApiMixin], data: JsonApiDataSchema) -> list[str]:
        """
        The to-many and reverse relations the item data sets (`ItemChanges.relations`).
        """
        if not getattr(data, 'relationships', None):
            return []
        relations = model.get_fields_info().relations
        return [
            name
            for name in data.relationships.model_dump(exclude_unset=True)
            if (info := relations.get(name)) and (info.to_many or info.reverse)
        ]

    def item_update(self, item: JsonApiMixin, data: JsonApiDataSchema):
        """
        Simple attributes are assigned immediately. updates the attributes and
        relationships of an item. The item is validated (`validate_item`, source
        `update`) at the end of the write.
        """
        with defer_validate_item(
            item,
            source='update',
            user=self._write_user(),
            relations=self._write_relations(type(item), data),
            savepoint=False,
        ):
            self.relations_access_check(data, item)
            self.hook_before_update(item)
            data.update_for(item)
            self.hook_after_update(item)
        return item

    def item_create(self, data: JsonApiDataSchema) -> JsonApiMixin:
        """
        Get model by type. creates a new item based on the provided data. The item is
        validated (`validate_item`, source `create`) at the end of the write.
        """
        self.relations_access_check(data)
        try:
            item = data.build_for()
        except ValueError:
            raise HTTPException(status_code=400, detail=_('Data type is invalid')) from None

        with defer_validate_item(user=self._write_user(), savepoint=False) as scope:
            self.hook_before_create(item)
            try:
                data.create_for(item)
            except IntegrityError:
                raise HTTPException(status_code=409, detail=_('Data conflict')) from None
            scope.mark(
                item,
                'create',
                relations=self._write_relations(type(item), data),
                user=self._write_user(),
            )
            self.hook_after_create(item)
        return item

    def list(self):
        """
        Fetches and returns a list of items, applying pagination and sorting.
        """
        qs = self.inject.pagination.apply(self.inject.sorting.apply(self.get_queryset_for_list()))
        for item in qs:
            item.only_fields = getattr(
                self.inject, f'fields_{qs.model.get_resource_label().replace(".", "_")}'
            )
        return qs

    def list_id(self) -> List[str]:  # noqa: UP006
        """
        Fetches and returns a list of items, applying pagination and sorting.
        """
        qs = self.get_queryset_for_list()
        # if qs.count() > settings.BAZIS_LIST_ID_LIMIT:
        #     raise HTTPException(
        #         status_code=400,
        #         detail=f'Number of items exceeds the limit of {settings.BAZIS_LIST_ID_LIMIT}',
        #     )
        return [str(it) for it in qs[: settings.BAZIS_LIST_ID_LIMIT].values_list('pk', flat=True)]

    def retrieve(
        self, item_id: str, with_lock: bool = False, is_force: bool = False
    ) -> JsonApiMixin:
        """
        Fetches and returns a single item by its ID, optionally with a database lock.
        """
        self.set_api_action(CrudApiAction.RETRIEVE)
        return self.set_item(item_id, with_lock=with_lock, is_force=is_force)

    def update(self, item_id: str, item_raw: dict, item_data: BaseModel) -> JsonApiMixin:
        """
        Updates an existing item by its ID based on the provided data. The item and the
        included items are validated at the end, once each.
        """
        with defer_validate_item(user=self._write_user(), savepoint=False) as scope:
            self.set_api_action(CrudApiAction.UPDATE)
            self.set_item(item_id)

            if schema_data := self.schemas.get(CrudApiAction.UPDATE):
                try:
                    item_data = schema_data.model_validate(item_raw)
                except ValidationError as e:
                    raise RequestValidationError(e.errors()) from e

            # update main instance
            self.item_update(self.item, item_data.data)

            # try to get input data for included
            if item_data_included := getattr(item_data, 'included', None):
                # collect a dictionary of existing related objects
                includes_cached = {}
                for includes in self.item.fields_for_included.values():
                    for include in includes:
                        includes_cached[(include.get_resource_label(), str(include.id))] = include

                # from the input included, take those that came for updating
                for index, include_data in enumerate(item_data_included):
                    if include_data.action != CrudAccessAction.CHANGE.value:
                        continue
                    try:
                        include = includes_cached[(include_data.type, str(include_data.id))]
                    except KeyError:
                        raise HTTPException(
                            status_code=400,
                            detail=format_lazy(
                                _('The object does not exist. Type: {type}. ID: {id}'),
                                type=include_data.type,
                                id=include_data.id,
                            ),
                        ) from None
                    self.item_update(include, include_data)
                    # the errors of its validation point to it
                    scope.mark(include, 'update', loc=('body', 'included', index))

                # from the input included, take those that came for creation
                for index, include_data in enumerate(item_data_included):
                    if include_data.action == CrudAccessAction.ADD.value:
                        include = self.item_create(include_data)
                        scope.mark(include, 'create', loc=('body', 'included', index))

            return self.item

    def create(self, item_raw: dict, item_data: BaseModel) -> JsonApiMixin:
        """
        Creates a new item based on the provided data. The item and the included items are
        validated at the end, once each.
        """
        with defer_validate_item(user=self._write_user(), savepoint=False) as scope:
            if schema_data := self.schemas.get(CrudApiAction.CREATE):
                try:
                    item_data = schema_data.model_validate(item_raw)
                except ValidationError as e:
                    raise RequestValidationError(e.errors(), body=item_raw) from e

            # create main instance
            self.item = self.item_create(item_data.data)

            # try to get input data for included
            if item_data_included := getattr(item_data, 'included', None):
                for index, include_data in enumerate(item_data_included):
                    include = self.item_create(include_data)
                    # the errors of its validation point to it
                    scope.mark(include, 'create', loc=('body', 'included', index))
            return self.item

    def destroy(self, item_id: str):
        """
        Deletes an item by its ID.
        """
        self.set_item(item_id)

        try:
            self.item.delete()
        except ProtectedError as err:
            protected_models = {}
            not_jsonapi_related_models = {}
            for rel in self.item.get_fields_info().reverse_relations.values():
                related_model = rel.related_model

                if not rel.is_m2m and rel.model_field.on_delete == PROTECT:
                    children_count = rel.get_child_queryset(self.item.pk).count()
                    if children_count > 0:
                        if issubclass(related_model, JsonApiMixin):
                            protected_models[related_model.get_resource_label()] = children_count
                        else:
                            not_jsonapi_related_models[
                                f'{related_model._meta.app_label}.{related_model.__name__}'
                            ] = children_count

            if not_jsonapi_related_models:
                raise JsonApiBazisException(
                    errors=[
                        JsonApiBazisError(
                            code='MODEL_NOT_JSONAPI',
                            title=format_lazy(
                                _('{model} is not JSON:API compliant'), model=model_name
                            ),
                            detail=format_lazy(
                                _(
                                    'Cannot delete object because it has related objects in '
                                    'non-JSON:API models. (count: {count})'
                                ),
                                count=count,
                            ),
                            meta_data={
                                'type': model_name,
                                'count': count,
                            },
                        )
                        for model_name, count in not_jsonapi_related_models.items()
                    ]
                ) from err

            if protected_models:
                raise JsonApiBazisException(
                    errors=[
                        JsonApiBazisError(
                            code='MODEL_PROTECTED_RELATION',
                            title=_('Error deleting protected model'),
                            detail=format_lazy(
                                _(
                                    'Cannot delete object because it has protected related '
                                    'objects of type {model} (count: {count})'
                                ),
                                model=model_name,
                                count=count,
                            ),
                            meta_data={
                                'type': model_name,
                                'count': count,
                            },
                        )
                        for model_name, count in protected_models.items()
                    ]
                ) from err

    @classmethod
    def route_instance(cls, request, **kwargs):
        """
        Returns an instance of the route class for the given request.
        """
        return cls.raw_call(request, path='/', **kwargs)
