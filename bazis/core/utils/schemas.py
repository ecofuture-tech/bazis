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

import os
from typing import Any

from django.utils.functional import Promise

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode, JsonSchemaValue

from pydantic_core import CoreSchema
from pydantic_settings import BaseSettings, SettingsConfigDict


def translated(value: Any) -> Any:
    """
    The value with its lazy texts (`gettext_lazy`, `format_lazy`) as strings of the active
    language, in its dicts, lists and tuples: a JSON schema or an OpenAPI document whose
    texts stay lazy as long as it is not generated.

    Tags: RAG, EXPORT
    """
    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, dict):
        return {key: translated(it) for key, it in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(translated(it) for it in value)
    return value


class TranslatedJsonSchema(GenerateJsonSchema):
    """
    A JSON schema generator that writes the lazy texts of the models (`Field(title=_('…'))`,
    `description`, `json_schema_extra`: labels, examples) in the language active when the
    schema is generated: pydantic copies a lazy title as it is, and the schema would not be a JSON
    document. The models keep their texts lazy, so every generation is in its own language.
    The OpenAPI of the core translates its whole document in the same way.

    Tags: RAG, EXPORT
    """

    def generate(self, schema: CoreSchema, mode: JsonSchemaMode = 'validation') -> JsonSchemaValue:
        return translated(super().generate(schema, mode))

    def generate_definitions(self, inputs):
        return translated(super().generate_definitions(inputs))


class TranslatedSchemaModel(BaseModel):
    """
    A model whose `model_json_schema()` uses `TranslatedJsonSchema` unless another
    `schema_generator` is given: the base of a model with lazy texts whose JSON schema is
    read outside the OpenAPI (the payload of a transit of bazis-statusy).

    Tags: RAG, EXPORT
    """

    @classmethod
    def model_json_schema(
        cls, *args, schema_generator: type[GenerateJsonSchema] = TranslatedJsonSchema, **kwargs
    ) -> dict[str, Any]:
        return super().model_json_schema(*args, schema_generator=schema_generator, **kwargs)


class CommonResourceSchema(BaseModel):
    """
    Base schema for resources with ID and type fields.
    Used for generic resource identification across the framework.
    Flexible ID type (Any) allows strings, integers, UUIDs, etc.
    """

    id: Any
    type: str


class BazisSettings(BaseSettings):
    """
    Core settings class for Bazis framework configuration.
    Loads from environment variables with 'BS_' prefix and .env files.

    Key features:
    - Prefix: BS_ for all env vars (e.g., BS_DEBUG)
    - Nested vars: Use __ delimiter (e.g., BS_DATABASE__HOST)
    - Files: Loads from project.env and custom file via BS_ENV_FILE
    - Case-sensitive variable names
    - Extra fields ignored

    Tags: RAG, EXPORT
    """

    model_config = SettingsConfigDict(
        extra='ignore',
        env_prefix='BS_',
        env_nested_delimiter='__',
        case_sensitive=True,
        env_file=('project.env', os.getenv('BS_ENV_FILE', '.env')),
    )
