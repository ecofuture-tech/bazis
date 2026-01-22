"""
Schema definitions for route filter fields.

This module defines:
- `InputField`: a representation of a single filterable field with name and OpenAPI type.
- `FieldListModel`: a container for returning multiple `InputField` instances.
- `RouteFilterFieldsSchemas`: a custom OpenAPI schema generator that overrides the default type mapping
  for specific types such as `Decimal`, `date`, and `datetime`.

Used in conjunction with `RouteFilterFieldsService` to expose filter metadata via API.
"""


from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue

from pydantic_core import core_schema


class InputField(BaseModel):
    """Represents a filterable field with its name and inferred OpenAPI type."""

    name: str
    py_type: str


class FieldListModel(BaseModel):
    """Response model for a list of filterable fields."""

    fields: list[InputField]


class RouteFilterFieldsSchemas(GenerateJsonSchema):
    """
    Custom schema generator for route filter fields.

    Overrides how specific Python types are represented in OpenAPI schemas,
    e.g. forces Decimal to appear as 'Decimal' instead of the default 'number | string'.
    """

    def decimal_schema(self, schema: core_schema.DecimalSchema) -> JsonSchemaValue:
        """
        Override for Decimal fields — represented as custom string 'Decimal'.
        Prevents Pydantic from emitting anyOf[number, string].
        """
        return {'type': 'Decimal'}

    def date_schema(self, schema: core_schema.DateSchema) -> JsonSchemaValue:
        """
        Override for date fields — represented as 'date'.
        """
        return {'type': 'date'}

    def datetime_schema(self, schema: core_schema.DateSchema) -> JsonSchemaValue:
        """
        Override for datetime fields — represented as 'datetime'.
        """
        return {'type': 'datetime'}


class ResourceIdentifier(BaseModel):
    type: str
    id: str


class RelationshipData(BaseModel):
    """
    Universal model for JSON:API relationships.
    data can be:
    - null → to-one remove
    - object → to-one
    - list of objects → to-many
    """

    data: None | ResourceIdentifier | list[ResourceIdentifier]


openapi_relationship_examples = {
    'to_one': {
        'summary': 'To-one relationship',
        'description': 'Changing a single relationship',
        'value': {'data': {'type': 'string', 'id': 'string'}},
    },
    'to_many': {
        'summary': 'To-many relationship',
        'description': 'Changing multiple relationships',
        'value': {'data': [{'type': 'string', 'id': 'string'}, {'type': 'string', 'id': 'string'}]},
    },
}
