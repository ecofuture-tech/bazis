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

import json
from typing import Any

from django.contrib.gis.db.models import GeometryField

from pydantic import (
    BaseModel,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
)

from pydantic_core import PydanticCustomError

from bazis.core.models_abstract import InitialBase
from bazis.core.utils.geo import geojson_geometry

from .utils import get_types


# check for nullable
def not_null_validator(cls: type[BaseModel], v: Any, field: ValidationInfo):
    """
    Validator to ensure that a field value is not null if the field is marked as
    non-nullable in the schema.

    Tags: RAG, INTERNAL
    """
    field_info = cls.model_fields[field.field_name]
    if field_info.json_schema_extra.get('nullable') is False and v is None:
        raise ValueError("Can't be null")
    return v


# check for blank
def not_blank_validator(cls: type[BaseModel], v: Any, field: ValidationInfo):
    """
    Validator to ensure that a field value is not blank if the field is marked as
    non-blank in the schema: empty, or a text of only whitespace (as the forms of Django,
    which strip it). Only the request schemas check it.

    Tags: RAG, INTERNAL
    """
    field_info = cls.model_fields[field.field_name]
    if field_info.json_schema_extra.get('blank') is False and (
        not v or (isinstance(v, str) and not v.strip())
    ):
        raise ValueError("Can't be blank")
    return v


def choices_validator(
    cls: type[BaseModel], v: Any, handler: ValidatorFunctionWrapHandler, field: ValidationInfo
):
    """
    Validator (wrap, around the schema type of the field) to ensure that a value of a field
    with choices is one of them: the `enum` of the field in the schema, which is the one of
    the OpenAPI (the choices of the model field, also the callable and the grouped ones; the
    choices of the elements of an array field). A value is a choice if it is a key of the
    choices as sent (a type of `TYPES_DJANGO_TO_SCHEMA` may make an object of a code) or
    once the type has converted it (`"2"` of an integer field, a Decimal, a UUID or a date
    sent as JSON), also against the keys converted by the same type. A value the type
    refuses is not a choice either: the error is the one of the choices. Null and empty
    values of the field are left to the null and the blank validators, as in the validation
    of a Django model field; the elements of an array are all choices. Only the request
    schemas check it.

    Tags: RAG, INTERNAL
    """
    enum = cls.model_fields[field.field_name].json_schema_extra.get('enum')
    if not enum or v is None or v == '':
        # an empty value of a field is left to the null and blank validators
        return handler(v)
    is_array = isinstance(v, list)
    values = v if is_array else [v]
    if all(value in enum for value in values):
        return handler(v)
    try:
        converted = handler(v)
    except ValidationError:
        value = next(value for value in values if value not in enum)
        raise ValueError(f'Value {value!r} is not a valid choice') from None
    if not is_array and converted in (None, ''):
        return converted
    keys = None
    for value, item in zip(values, converted if is_array else [converted], strict=True):
        if value in enum or item in enum:
            continue
        if keys is None:
            keys = _converted_choices(cls.model_fields[field.field_name].annotation, enum, is_array)
        if item not in keys:
            raise ValueError(f'Value {value!r} is not a valid choice')
    return converted


def _converted_choices(annotation: Any, enum: list, is_array: bool) -> list:
    """
    The keys of the choices converted by the type of the field (of an element of an array
    field); a key the type does not take is left out.
    """
    adapter = TypeAdapter(annotation)
    keys = []
    for key in enum:
        try:
            keys.append(
                adapter.validate_python([key])[0] if is_array else adapter.validate_python(key)
            )
        except ValidationError:
            pass
    return keys


def geometry_validator(cls: type[BaseModel], v: Any, field: ValidationInfo):
    """
    Validator of the GeoJSON value of a geometry field of the model in a request (before
    the GeoJSON schema drops its other members): `geojson_geometry` (WGS 84 without `crs`,
    the type and the dimension of the field, the coordinates in range).

    Tags: RAG, INTERNAL
    """
    schema_field = cls.schema_factory.fields.get(field.field_name)
    model_field = getattr(schema_field, 'field_db_attr', None)
    if v is not None and isinstance(model_field, GeometryField):
        value = json.loads(v) if isinstance(v, str) else v
        if isinstance(value, dict):
            geojson_geometry(value, model_field)
    return v


def readonly_validator(cls: type[BaseModel], values: Any):
    """
    Validator to remove read-only fields from the values if the schema action does
    not support read-only operations.
    """
    if not cls.schema_factory.api_action.for_read_only:
        for f_name, field_info in cls.model_fields.items():
            if field_info.json_schema_extra.get('readOnly'):
                values.pop(f_name, None)
    return values


def field_validate(cls: type[BaseModel], name, value):
    """
    Validate a field value against its schema, supporting nested types.

    Tags: RAG, INTERNAL
    """
    if field_info := cls.model_fields.get(name):
        types = get_types(field_info)
        if types:
            return model_validate(types[0], value, (name,))


def model_validate(model: type[BaseModel], value, loc: tuple):
    """
    Validate a model instance against its schema, raising a ValidationError with
    detailed context if validation fails.

    Tags: RAG, INTERNAL
    """
    try:
        return model.model_validate(value)
    except ValidationError as e:
        _id = None
        _type = None
        if isinstance(value, InitialBase):
            _id = value.pk
            _type = value.get_resource_label()
        elif isinstance(value, dict) and 'id' in value:
            _id = value['id']
            _type = value['type']

        # e.errors() makes new dicts on every call: change them and raise the same ones
        errors = e.errors()
        for _e in errors:
            _e['loc'] = loc + tuple(_e['loc'])
            ctx = _e.setdefault('ctx', {})
            if _id:
                ctx['_id'] = _id
            if _type:
                ctx['_type'] = _type

        # `from_exception_data` rebuilds the built-in error types only with the context
        # they were made from (a ValueError of `value_error` is `ctx['error']`, which is
        # not in the context of the errors of `EmailStr`): a custom error keeps the type,
        # the message and the context as they are
        raise ValidationError.from_exception_data(
            e.title,
            [
                {
                    'type': PydanticCustomError(_e['type'], _e['msg'], _e['ctx']),
                    'loc': _e['loc'],
                    'input': _e['input'],
                }
                for _e in errors
            ],
        ) from e
