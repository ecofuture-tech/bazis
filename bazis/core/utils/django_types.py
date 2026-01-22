import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Union, cast
from uuid import UUID

from django.contrib.postgres.fields import (
    BigIntegerRangeField,
    DateRangeField,
    DateTimeRangeField,
    DecimalRangeField,
    IntegerRangeField,
)
from django.core.files.uploadedfile import UploadedFile
from django.db import models as django_models
from django.db.backends.postgresql.psycopg_any import Range as PGRange

from fastapi import UploadFile

from pydantic import (
    AnyUrl,
    BaseModel,
    EmailStr,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    IPvAnyAddress,
    constr,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue

from pydantic_core import PydanticCustomError, core_schema

from .functools import ClassLookupDict


# Optional imports with graceful fallback
try:
    from django.contrib.postgres import fields as postgres_fields
except ImportError:
    postgres_fields = None

try:
    from django.contrib.gis.db.models.fields import GeometryField
    from django.contrib.gis.geos.geometry import GEOSGeometry
except ImportError:
    GeometryField = None
    GEOSGeometry = None

try:
    from picklefield.fields import PickledObjectField
except ImportError:
    PickledObjectField = None


class FilePathStr(Path):
    """
    Custom Path type for Django FileField/ImageField serialization.
    Handles file paths and URLs in Pydantic schemas.

    Converts Django FieldFile objects to string paths or URLs.
    Supports validation and JSON schema generation for file paths.

    Tags: RAG, EXPORT
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source: type[Any],
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """
        Pydantic v2 core schema: validates strings as file paths.
        """
        return core_schema.no_info_after_validator_function(cls._validate, core_schema.str_schema())

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """
        Generates OpenAPI/JSON schema with 'file-path' format.
        """
        field_schema = handler(core_schema)
        field_schema.update(format='file-path')
        return field_schema

    @classmethod
    def _validate(cls, v):
        """
        Validates file path input: accepts str, Path, or Django FieldFile.
        Extracts URL from Django file objects if available.
        """
        if isinstance(v, str | Path):
            return v
        if v:
            try:
                return str(v.url)
            except TypeError:
                raise PydanticCustomError('wrong_path', 'error in the path') from None


class UploadFileDjango(UploadFile):
    """
    FastAPI UploadFile compatible with Django UploadedFile.
    Handles file uploads bidirectionally between FastAPI and Django.

    Supports:
    - Django FieldFile (with URL extraction)
    - FastAPI UploadFile
    - String URLs
    - None/empty values

    Tags: RAG, EXPORT
    """

    @classmethod
    def _validate(cls, __input_value: Any):
        """
        Validates and normalizes file input from various sources.
        Returns None for empty/null values, URL strings, or UploadFile instances.
        """
        # Handle None and empty values
        if __input_value is None:
            return None

        # Handle Django FieldFile
        if hasattr(__input_value, 'name'):
            # Empty FieldFile (name is None or False)
            if not __input_value.name:
                return None
            # Extract URL if available
            if hasattr(__input_value, 'url'):
                return str(__input_value.url)

        if isinstance(__input_value, UploadFileDjango):
            return __input_value
        elif hasattr(__input_value, 'url'):
            return str(__input_value.url)
        elif hasattr(__input_value, 'file'):
            return cast(UploadFile, __input_value)

        # Handle string URLs
        if isinstance(__input_value, str):
            return __input_value if __input_value else None

        raise PydanticCustomError('wrong_path', 'error in the path')

    @staticmethod
    def _serialize(value: Union['UploadFileDjango', str, None]) -> UploadedFile | str | None:
        """
        Serializes to Django UploadedFile for ORM compatibility.
        Converts FastAPI UploadFile to Django format.
        """
        if value is None:
            return None
        if isinstance(value, UploadFileDjango):
            return UploadedFile(value.file, name=value.filename, content_type=value.content_type)
        elif isinstance(value, str):
            return value
        return None

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        Pydantic v2 schema with custom validation and serialization.
        Enables bidirectional FastAPI ↔ Django file handling.
        """
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.any_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize,
                info_arg=False,
                return_schema=core_schema.any_schema(),
            ),
        )


class GeoJson(BaseModel):
    """
    GeoJSON schema for GeoDjango GeometryField compatibility.
    Supports standard GeoJSON geometry types.

    Compatible with:
    - Django GEOSGeometry objects
    - GeoJSON strings
    - GeoJSON dictionaries

    Geometry types: Point, LineString, Polygon, MultiPoint,
                    MultiLineString, MultiPolygon, GeometryCollection

    Tags: RAG, EXPORT
    """

    type: Literal[
        'Point',
        'LineString',
        'Polygon',
        'MultiPoint',
        'MultiLineString',
        'MultiPolygon',
        'GeometryCollection',
    ]
    coordinates: list

    @model_validator(mode='before')
    @classmethod
    def validator(cls, data: Any) -> Any:
        """
        Validates and converts various GeoJSON input formats.
        Handles Django GEOSGeometry, JSON strings, and dictionaries.
        """
        if isinstance(data, GEOSGeometry):
            return json.loads(data.geojson)
        elif isinstance(data, str):
            try:
                geojson_obj = json.loads(data)
                return geojson_obj
            except json.JSONDecodeError:
                raise ValueError('Invalid GeoJSON string') from None
        elif isinstance(data, dict):
            return data
        else:
            raise ValueError('Invalid type for GeoJson, expected str or dict representing GeoJSON')


class EmailEmptyAllowedStr(EmailStr):
    """
    EmailStr variant allowing empty strings.
    Useful for optional email fields in Django models.

    RAG keywords: email field, optional email, empty email, email validation
    """

    @classmethod
    def _validate(cls, value: str) -> str:
        """
        Validates email or allows empty string.
        Bypasses EmailStr validation for empty values.
        """
        if value == '':
            return value
        return super()._validate(value)


class RangeType:
    """
    PostgreSQL range field type adapter for Pydantic.
    Converts Django range fields to/from tuple format (lower, upper).

    Supports: IntegerRange, BigIntegerRange, DecimalRange,
              DateTimeRange, DateRange

    Tags: RAG, EXPORT
    """

    def __get_pydantic_core_schema__(
        self,
        _source: type[Any],
        _handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """
        Pydantic v2 schema for range validation.
        """
        return core_schema.no_info_after_validator_function(
            self._validate, core_schema.str_schema()
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """
        OpenAPI schema: represents range as [min, max] array.
        """
        field_schema = handler(core_schema)
        field_schema.update(type='range', format=json.dumps(['min', 'max']), example=[1, 10])
        return field_schema

    @classmethod
    def _validate(cls, v):
        """
        Converts PostgreSQL Range to tuple (lower, upper).
        Preserves tuples and other formats.
        """
        if isinstance(v, PGRange):
            return (v.lower, v.upper)
        return v


# Django field to Pydantic type mapping
# Used for automatic schema generation from Django models
TYPES_DJANGO_TO_SCHEMA = {
    django_models.AutoField: int,
    django_models.BigIntegerField: Annotated[
        int, Field(ge=-9223372036854775808, le=9223372036854775807)
    ],
    django_models.BooleanField: bool,
    django_models.CharField: str,
    django_models.CommaSeparatedIntegerField: str,
    django_models.DateField: date,
    django_models.DateTimeField: datetime,
    django_models.DecimalField: Decimal,
    django_models.DurationField: timedelta,
    django_models.EmailField: EmailEmptyAllowedStr,
    django_models.FileField: UploadFileDjango | FilePathStr,
    django_models.FloatField: Annotated[float, Field(ge=-3.402823466e38, le=3.402823466e38)],
    django_models.ImageField: UploadFileDjango | FilePathStr,
    django_models.IntegerField: Annotated[int, Field(ge=-2147483648, le=2147483647)],
    django_models.NullBooleanField: bool,
    django_models.PositiveIntegerField: Annotated[int, Field(ge=0, le=2147483647)],
    django_models.PositiveSmallIntegerField: Annotated[int, Field(ge=0, le=32767)],
    django_models.SlugField: str,
    django_models.SmallIntegerField: Annotated[int, Field(ge=-32768, le=32767)],
    django_models.TextField: str,
    django_models.TimeField: time,
    django_models.URLField: (
        AnyUrl | Annotated[str, constr(strip_whitespace=True, min_length=0, max_length=0)] | None
    ),
    django_models.UUIDField: UUID,
    django_models.GenericIPAddressField: IPvAnyAddress,
    django_models.FilePathField: str,
    django_models.JSONField: Any,
    IntegerRangeField: RangeType,
    BigIntegerRangeField: RangeType,
    DecimalRangeField: RangeType,
    DateTimeRangeField: RangeType,
    DateRangeField: RangeType,
}

# Conditionally add PostgreSQL-specific types
if postgres_fields:
    TYPES_DJANGO_TO_SCHEMA[postgres_fields.HStoreField] = dict
    TYPES_DJANGO_TO_SCHEMA[postgres_fields.ArrayField] = list
    TYPES_DJANGO_TO_SCHEMA[postgres_fields.JSONField] = dict

# Add GeoDjango types if available
if GeometryField:
    TYPES_DJANGO_TO_SCHEMA[GeometryField] = GeoJson

# Add picklefield if available
if PickledObjectField:
    TYPES_DJANGO_TO_SCHEMA[PickledObjectField] = dict

# Lookup dictionary for efficient field type resolution
# Uses ClassLookupDict for inheritance-aware lookups
TYPES_DJANGO_TO_SCHEMA_LOOKUP = ClassLookupDict(TYPES_DJANGO_TO_SCHEMA)
