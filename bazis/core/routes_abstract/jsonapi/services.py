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

"""
Module for extracting filterable fields from route schemas.

This module defines the `RouteFilterFieldsService` class, which inspects FastAPI routes
based on `JsonapiRouteBase` to gather metadata about fields that can be used for filtering.

It supports:
- Native database fields (with type conversion to OpenAPI types).
- Related fields (resolved to list endpoints of related resources).
- Calculated fields (using annotated response types via `@calc_property`).

The main entry point is `RouteFilterFieldsService.get_fields(route_cls)`, which returns a list of `InputField` objects
representing filterable fields for the given route.
"""

from functools import cache
from typing import TYPE_CHECKING

from fastapi.routing import APIRoute

from pydantic import TypeAdapter

from bazis.core.routes_abstract.initial import InitialRouteBase
from bazis.core.schemas import CrudApiAction

from .schemas import InputField, RouteFilterFieldsSchemas


if TYPE_CHECKING:
    from .route_base import JsonapiRouteBase


class RouteFilterFieldsService:
    """
    Service that extracts filterable fields from route schema.

    Tags: RAG
    """

    @classmethod
    def get_fields(cls, route_cls: type['JsonapiRouteBase']) -> list[InputField]:
        """Return list of filterable fields for a given route class."""
        schema_factory = route_cls.schemas[CrudApiAction.LIST].schema_factory
        return [
            cls._serialize_field(route_schema_field, route_cls)
            for route_schema_field in schema_factory.fields_list
            if route_schema_field.can_filter is True
        ]

    @classmethod
    def _serialize_field(
        cls, route_schema_field: object, route_cls: type['JsonapiRouteBase']
    ) -> InputField:
        """
        Serialize a field to InputField format, determining the type (py_type)
        depending on whether it's a related field, a database field, or a calculated field.
        """
        field_info: dict[str, str] = {'name': route_schema_field.name}

        if route_schema_field.field_db_rel:
            # Related field — map to endpoint URL of related route.
            field_route_cls = cls._find_route_cls_for_model(
                route_schema_field.field_db_rel.related_model
            )
            field_info['py_type'] = (
                field_route_cls.url_path_for('action_list') if field_route_cls else 'unknown'
            )

        elif route_schema_field.field_db_attr:
            # Database attribute — resolve OpenAPI type via Python type.
            field_info['py_type'] = cls.get_openapi_type_name(route_schema_field.py_type)

        else:
            # Calculated field — get method's response_type and resolve its OpenAPI type.
            method = getattr(route_cls.model, route_schema_field.source, None)
            response_type = getattr(method, 'response_type', None)
            field_info['py_type'] = (
                cls.get_openapi_type_name(response_type) if response_type else 'unknown'
            )

        return InputField(**field_info)

    @staticmethod
    @cache
    def get_openapi_type_name(py_type: type) -> str:
        """
        Convert a Python type into a corresponding OpenAPI type name.
        If the type is a union (anyOf), returns the first non-null type.
        """
        schema = TypeAdapter(py_type).json_schema(schema_generator=RouteFilterFieldsSchemas)
        if 'type' in schema:
            return schema['type']
        if 'anyOf' in schema:
            return next(
                (
                    response_type['type']
                    for response_type in schema['anyOf']
                    if response_type['type'] != 'null'
                ),
                'unknown',
            )
        return 'unknown'

    @staticmethod
    @cache
    def _find_route_cls_for_model(model: type) -> type['JsonapiRouteBase'] | None:
        """
        Search registered FastAPI routes and return route class that corresponds to the given Django model.
        Only non-abstract InitialRouteBase subclasses are considered.
        """
        from bazis.core.app import app

        for route in app.router.routes:
            if (
                isinstance(route, APIRoute)
                and hasattr(route.endpoint, 'route_ctx')
                and issubclass(route.endpoint.route_ctx.route_cls, InitialRouteBase)
                and not getattr(route.endpoint.route_ctx.route_cls, 'abstract', False)
                and getattr(route.endpoint.route_ctx.route_cls, 'model', None) == model
            ):
                return route.endpoint.route_ctx.route_cls
        return None
