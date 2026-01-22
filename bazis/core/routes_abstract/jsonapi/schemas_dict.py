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

from collections import UserDict
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel

from bazis.core.schemas.enums import ApiAction, CrudApiAction


if TYPE_CHECKING:
    from .route_base import JsonapiRouteBase


class SchemasDict(UserDict, dict[ApiAction, type[BaseModel]]):
    """
    A dictionary-like class that manages schema generation for different CRUD API
    actions.

    Tags: RAG
    """

    def __init__(
        self,
        route_cls: type['JsonapiRouteBase'],
        includes: list[str] = None,
        is_schema_response=False,
        dict=None,
        /,
        **kwargs,
    ):
        """
        Initializes the SchemasDict with the route class and optional includes.
        """
        self.route_cls = route_cls
        self.schema_defaults = (
            route_cls.schema_defaults
            if not is_schema_response
            else route_cls.schema_responses_defaults
        )
        self.is_response_schema = is_schema_response
        self.includes = includes
        super().__init__(dict=dict, **kwargs)

    def build_schema_list(self):
        """
        Builds the schema for the LIST CRUD API action.
        """
        return self.schema_defaults[CrudApiAction.LIST]

    def build_schema_retrieve(self):
        """
        Builds the schema for the RETRIEVE CRUD API action, including specified includes
        if any.
        """
        if not self.includes:
            return self.schema_defaults[CrudApiAction.RETRIEVE]

        schema_factory = self.route_cls.schema_factories[CrudApiAction.RETRIEVE]
        inclusions_factory = [
            v
            for k, v in schema_factory.inclusions_factory_with_default.items()
            if k in self.includes
        ]
        return schema_factory.build_schema(
            schema_resource=schema_factory.resource_schema_default
            if self.is_response_schema
            else schema_factory.resource_schema_default_response,
            inclusions=[
                f.resource_schema_default
                if not self.is_response_schema
                else f.resource_schema_default_response
                for f in inclusions_factory
            ],
            is_response_schema=self.is_response_schema,
        )

    def build_schema_update(self):
        """
        Builds the schema for the UPDATE CRUD API action, including specified includes
        if any.
        """
        if not self.includes:
            return self.schema_defaults[CrudApiAction.UPDATE]

        schema_factory_update = self.route_cls.schema_factories[CrudApiAction.UPDATE]
        schema_factory_create = self.route_cls.schema_factories[CrudApiAction.CREATE]

        inclusions_factory_update = [
            v
            for k, v in schema_factory_update.inclusions_factory_with_default.items()
            if k in self.includes
        ]
        inclusions_factory_create = [
            v
            for k, v in schema_factory_create.inclusions_factory_with_default.items()
            if k in self.includes
        ]

        return schema_factory_update.build_schema(
            schema_resource=schema_factory_update.resource_schema_default,
            inclusions=(
                [f.resource_schema_default for f in inclusions_factory_update]
                + [f.resource_schema_default for f in inclusions_factory_create]
            ),
            is_response_schema=self.is_response_schema,
        )

    def build_schema_create(self):
        """
        Builds the schema for the CREATE CRUD API action, including specified includes
        if any.
        """
        if not self.includes:
            return self.schema_defaults[CrudApiAction.CREATE]

        schema_factory = self.route_cls.schema_factories[CrudApiAction.CREATE]
        inclusions_factory = [
            v
            for k, v in schema_factory.inclusions_factory_with_default.items()
            if k in self.includes
        ]
        return schema_factory.build_schema(
            schema_resource=schema_factory.resource_schema_default,
            inclusions=[f.resource_schema_default for f in inclusions_factory],
            is_response_schema=self.is_response_schema,
        )

    @classmethod
    def get_builders(cls) -> dict[ApiAction, Callable]:
        """
        Returns a dictionary mapping CRUD API actions to their respective schema-
        building methods.
        """
        return {
            CrudApiAction.LIST: cls.build_schema_list,
            CrudApiAction.RETRIEVE: cls.build_schema_retrieve,
            CrudApiAction.UPDATE: cls.build_schema_update,
            CrudApiAction.CREATE: cls.build_schema_create,
        }

    def __getitem__(self, key: ApiAction) -> type[BaseModel]:
        """
        Retrieves the schema for the given CRUD API action, building it if it doesn't
        already exist.
        """
        if key not in self.data:
            if get_schema := self.get_builders().get(key):
                self.data[key] = get_schema(self)
        return super().__getitem__(key)

    def get(self, key: ApiAction, default=None) -> type[BaseModel] | None:
        try:
            return self[key]
        except KeyError:
            return default


class SchemasResponseDict(SchemasDict):
    pass
