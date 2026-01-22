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

# ruff: noqa: E402, N807


from fastapi import FastAPI

from starlette.routing import BaseRoute


# Monkey patch: Deduplicates FastAPI routes
# Issue: Complex nested routes can create duplicate entries in router
# Solution: Filter routes to ensure uniqueness before returning
@property
def routes(self) -> list[BaseRoute]:
    """
    Returns unique routes from FastAPI router.
    Prevents route duplication in complex nested route configurations.

    Override of FastAPI.routes property to filter duplicates.
    """
    routes_uniq = []
    for r in self.router.routes:
        if r not in routes_uniq:
            routes_uniq.append(r)
    return routes_uniq


FastAPI.routes = routes

######################################################################

import typing
from typing import Literal

from pydantic import BaseModel
from pydantic._internal import _generate_schema

from pydantic_core import to_jsonable_python


if typing.TYPE_CHECKING:
    from pydantic import IncEx
    from pydantic.config import JsonDict
    from pydantic.json_schema import JsonSchemaValue


def add_json_schema_extra(
    json_schema: 'JsonSchemaValue',
    json_schema_extra: typing.Union['JsonDict', typing.Callable[['JsonDict'], None], None],
):
    """
    Monkey patch: Adds custom fields to Pydantic JSON schema generation.

    Extends Pydantic's schema generation to support:
    - Dictionary-based schema extras
    - Callable schema modifiers

    Enables custom OpenAPI extensions and metadata.
    """
    if isinstance(json_schema_extra, dict):
        json_schema.update(to_jsonable_python(json_schema_extra, serialize_unknown=True))
    elif callable(json_schema_extra):
        json_schema_extra(json_schema)


_generate_schema.add_json_schema_extra = add_json_schema_extra


def model_dump(
    self,
    *,
    mode: Literal['json', 'python'] | str = 'python',
    include: 'IncEx' = None,
    exclude: 'IncEx' = None,
    by_alias: bool = False,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
    round_trip: bool = False,
    warnings: bool = True,
) -> dict[str, typing.Any]:
    """
    Monkey patch: Enhanced Pydantic model serialization with fallback.

    Overrides BaseModel.model_dump to add string fallback for unknown types
    in JSON mode. Prevents serialization errors for custom objects.

    Args:
        mode: 'json' or 'python' serialization mode
        include/exclude: Field inclusion/exclusion patterns
        by_alias: Use field aliases in output
        exclude_unset/defaults/none: Filter output values
        round_trip: Enable round-trip serialization
        warnings: Show validation warnings

    Returns:
        Serialized model as dictionary
    """
    return self.__pydantic_serializer__.to_python(
        self,
        mode=mode,
        by_alias=by_alias,
        include=include,
        exclude=exclude,
        exclude_unset=exclude_unset,
        exclude_defaults=exclude_defaults,
        exclude_none=exclude_none,
        round_trip=round_trip,
        warnings=warnings,
        fallback=(lambda obj: str(obj)) if mode == 'json' else None,
    )


BaseModel.model_dump = model_dump

######################################################################
from pydantic import json_schema


def to_jsonable_python_str(value, **kwargs):
    """
    Monkey patch: Forces serialize_unknown=True in Pydantic JSON conversion.

    Ensures unknown types are serialized (usually as strings) rather than
    raising errors. Improves compatibility with Django and custom types.
    """
    kwargs['serialize_unknown'] = True
    return to_jsonable_python(value, **kwargs)


json_schema.to_jsonable_python = to_jsonable_python_str

######################################################################

from django.utils.functional import Promise

from fastapi import encoders


_jsonable_encoder = encoders.jsonable_encoder


def jsonable_encoder(obj, *args, **kwargs):
    """
    Monkey patch: FastAPI JSON encoder with Django compatibility.

    Enhancements:
    - Converts Django Promise objects (lazy translations) to strings
    - Disables SQLAlchemy safe mode (not needed in Django context)

    Critical for Django i18n integration with FastAPI responses.

    Args:
        obj: Object to encode
        sqlalchemy_safe: Disabled by default
    """
    kwargs['sqlalchemy_safe'] = False
    if isinstance(obj, Promise):
        return str(obj)
    return _jsonable_encoder(obj, *args, **kwargs)


encoders.jsonable_encoder = jsonable_encoder


######################################################################

from typing import Any

from pydantic_core import core_schema
from translated_fields.fields import TranslatedField


def __get_pydantic_core_schema__(
    cls,
    source_type: Any,
    handler: Any,
) -> core_schema.CoreSchema:
    """
    We tell Pydantic that TranslatedField returns a string.
    """

    # TranslatedField, when accessed, returns a string for the current language
    # Therefore, we simply use the schema for a string
    def serialize_translated_field(value: Any) -> str | None:
        """
        Serializer - the output is always a string or None.
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value
        # Just in case, convert to a string
        return str(value)

    def validate_translated_field(value: Any) -> str | None:
        """
        Validator - accepts strings and None.
        TranslatedField via getattr will always return a string or None.
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, TranslatedField):
            # If for some reason we received the descriptor itself (should not happen),
            # this is a configuration error
            raise ValueError(
                'Received a TranslatedField object instead of a string. '
                'Make sure you are using from_attributes=True'
            )
        # Try to convert to a string
        return str(value)

    # Create a schema: accept str or None, return str or None
    string_schema = core_schema.str_schema()
    none_schema = core_schema.none_schema()

    # Union schema for str | None
    union_schema = core_schema.union_schema(
        [
            string_schema,
            none_schema,
        ]
    )

    # Wrap in a validator
    validated_schema = core_schema.no_info_after_validator_function(
        validate_translated_field,
        union_schema,
    )

    # Add a serializer
    return core_schema.json_or_python_schema(
        json_schema=validated_schema,
        python_schema=validated_schema,
        serialization=core_schema.plain_serializer_function_ser_schema(
            serialize_translated_field,
            return_schema=union_schema,
        ),
    )


# Add the method to the TranslatedField class
TranslatedField.__get_pydantic_core_schema__ = classmethod(__get_pydantic_core_schema__)

from translated_fields import fields as translated_fields_module

from bazis.core.utils.translated_field_utils import translated_attrgetter


translated_fields_module.translated_attrgetter = translated_attrgetter
