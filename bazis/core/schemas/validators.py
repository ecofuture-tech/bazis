from typing import Any

from pydantic import (
    BaseModel,
    ValidationError,
    ValidationInfo,
)

from typing_extensions import deprecated

from bazis.core.models_abstract import InitialBase

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
    non-blank in the schema.

    Tags: RAG, INTERNAL
    """
    field_info = cls.model_fields[field.field_name]
    if field_info.json_schema_extra.get('blank') is False and not v:
        raise ValueError("Can't be blank")
    return v


@deprecated(
    'disabled because there are transition-type operations that require mandatory fields, which may well be read-only'
)
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

        for errs in e.errors():
            errs = errs if isinstance(errs, list) else [errs]
            for _e in errs:
                if isinstance(_e['loc'], tuple):
                    _e['loc'] = loc + _e['loc']
                else:
                    _e['loc'] = loc + (_e['loc'],)

                if 'ctx' not in _e:
                    _e['ctx'] = {}

                if _id:
                    _e['ctx']['_id'] = _id
                if _type:
                    _e['ctx']['_type'] = _type
        raise ValidationError.from_exception_data(str(e), e.errors()) from e
