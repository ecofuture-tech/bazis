from pydantic import (
    BaseModel,
)
from pydantic.fields import FieldInfo


def get_types(field: FieldInfo) -> list[type[BaseModel]]:
    """
    Extract types from a schema field, considering the possibility of multiple types
    in the original field.

    Tags: RAG, INTERNAL
    """
    types = []

    def get_types_from_type(type_):
        """
        Helper function to recursively extract types from a given type annotation.
        """
        if hasattr(type_, '__constraints__'):
            for arg in type_.__constraints__:
                get_types_from_type(arg)
        elif hasattr(type_, '__args__'):
            for arg in type_.__args__:
                get_types_from_type(arg)
        elif issubclass(type_, BaseModel):
            types.append(type_)

    get_types_from_type(field.annotation)

    return types


def get_nested_fields(field: FieldInfo) -> dict[str, FieldInfo]:
    """
    Extract nested fields from a schema field, considering the possibility of
    multiple types in the original field.

    Tags: RAG, INTERNAL
    """
    annotation = field.annotation

    if hasattr(annotation, '__args__'):
        for arg in annotation.__args__:
            if issubclass(arg, BaseModel):
                annotation = arg
                break
    elif hasattr(annotation, '__constraints__'):
        for arg in annotation.__constraints__:
            if issubclass(arg, BaseModel):
                annotation = arg
                break

    if issubclass(annotation, BaseModel):
        return annotation.model_fields

    return {}
