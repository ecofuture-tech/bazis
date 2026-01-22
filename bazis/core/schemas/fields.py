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

import dataclasses
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from django.db.models.fields import Field as DjangoField

from pydantic import (
    BaseModel,
)

from pydantic_core import PydanticUndefined

from bazis.core.utils.django_types import TYPES_DJANGO_TO_SCHEMA_LOOKUP
from bazis.core.utils.functools import uniq_id
from bazis.core.utils.model_meta import (
    RelationInfo,
)


@dataclasses.dataclass
class CallableContext:
    """
    Dataclass representing a callable context, including the class path and the
    attribute (callable or string).

    Tags: RAG, EXPORT
    """

    class_path: str
    attr: Callable | str

    def __hash__(self):
        """
        Generates a unique hash for the CallableContext instance based on its class path
        and attribute.
        """
        return uniq_id((self.class_path, self.attr))


@dataclasses.dataclass
class SchemaField:
    """
    Class describing a schema field.

    Args:
        name (str): Name of the field in the API.
        source (str | Callable | CallableContext): Data source for the field.
            By default, it is the attribute of the object name.
        schema_out (Type[BaseModel | list]): Schema of the complex object field.
        primary_key (bool): Whether the field is a primary key.
        required (bool): Whether the field is required.
        title (str): Human-readable name for the schema.
        default (Any): Default value.
        description (str): Detailed description of the field.
        min_length (int): Minimum length of the text field.
        max_length (int): Maximum length of the text field.
        read_only (bool): Whether the field is "read-only".
        write_only (bool): Whether the field is "write-only".
        nullable (bool): Whether the field can accept None.
        blank (bool): Whether the field can be blank.
        can_filter (bool): Whether the field can be used in filtering.
        can_order (bool): Whether the field can be used in sorting.
        enum (list): Limited list of acceptable values.
        enum_dict (dict): Dictionary decoding the acceptable list of values.

    Tags: RAG, EXPORT
    """

    name: str = None
    source: str | Callable | CallableContext = None
    schema_out: type[BaseModel | list] = None
    primary_key: bool = False
    title: str = None
    default: Any = PydanticUndefined
    description: str = None
    min_length: int = None
    max_length: int = None
    required: bool = None
    nullable: bool = None
    blank: bool = None
    read_only: bool = None
    write_only: bool = None
    can_filter: bool = None
    can_order: bool = None
    enum: list = None
    enum_dict: dict = None
    field_db_attr: DjangoField = None
    field_db_rel: RelationInfo = None
    restrict_filters: list = None

    @property
    def idx(self):
        """
        Generates a unique identifier for the SchemaField instance based on its
        attributes.
        """
        return uniq_id(
            (
                self.name,
                self.source,
                self.schema_out,
                self.required,
                self.title,
                self.description,
                self.min_length,
                self.max_length,
                self.read_only,
                self.write_only,
                self.nullable,
                self.blank,
                tuple(self.enum) if self.enum else None,
                tuple(self.enum_dict.items()) if self.enum_dict else None,
                tuple(self.restrict_filters) if self.restrict_filters else None,
            )
        )

    def __str__(self):
        """
        Returns the string representation of the SchemaField, which is its name.
        """
        return self.name

    def __eq__(self, other):
        """
        Compares the SchemaField instance with another instance or string for equality
        based on its unique identifier or name.
        """
        if isinstance(other, str):
            return self.name == other
        elif isinstance(other, SchemaField):
            return self.idx == other.idx
        return False

    def __hash__(self):
        """
        Generates a unique hash for the SchemaField instance based on its unique
        identifier.
        """
        return self.idx

    def __or__(self, other):  # noqa: C901
        """
        Combines two SchemaField instances, prioritizing non-None values from the second
        instance.
        """
        source = deepcopy(self)

        if other.required is None:
            source.required = None
        elif other.required is False:
            source.required = False

        if other.nullable is None:
            source.nullable = None
        elif other.nullable is True:
            source.nullable = True

        if other.blank is None:
            source.blank = None
        elif other.blank is True:
            source.blank = True

        if other.read_only is None:
            source.read_only = None
        elif other.read_only is False:
            source.read_only = False

        if other.write_only is None:
            source.write_only = None
        elif other.write_only is False:
            source.write_only = False

        if other.can_filter is None:
            source.can_filter = None
        elif other.can_filter is True:
            source.can_filter = True

        if other.can_order is None:
            source.can_order = None
        elif other.can_order is True:
            source.can_order = True

        if other.restrict_filters is None:
            source.restrict_filters = None
        elif other.restrict_filters:
            if source.restrict_filters is None:
                source.restrict_filters = other.restrict_filters
            else:
                source.restrict_filters.extend(other.restrict_filters)

        return source

    @property
    def py_type(self) -> type:
        """
        Returns the Python type of the field based on its database attribute.
        """
        if not self.field_db_attr:
            return Any
        try:
            return TYPES_DJANGO_TO_SCHEMA_LOOKUP[self.field_db_attr]
        except KeyError:
            return Any


@dataclasses.dataclass
class SchemaFields:
    """
    Dataclass representing a collection of schema fields, including origin, include,
    exclude, and inheritance status.

    Tags: RAG, EXPORT
    """

    origin: dict[str, None | SchemaField] = dataclasses.field(default_factory=dict)
    include: dict[str, None | SchemaField] = dataclasses.field(default_factory=dict)
    exclude: dict[str, None] = dataclasses.field(default_factory=dict)
    is_inherit: bool = True


@dataclasses.dataclass
class SchemaMetaField:
    """
    Dataclass representing a meta field for a schema, including its name, title,
    description, and data source.

    Tags: RAG, EXPORT
    """

    schema_out: type
    name: str = None
    title: str = None
    description: str = None
    source: str | Callable | CallableContext = None

    def __str__(self):
        """
        Returns the string representation of the SchemaMetaField, which is its name.
        """
        return self.name

    def __eq__(self, other: 'SchemaMetaField'):
        """
        Compares the SchemaMetaField instance with another instance for equality based
        on its unique identifier.
        """
        return self.idx == other.idx

    @property
    def idx(self):
        """
        Generates a unique identifier for the SchemaMetaField instance based on its
        attributes.
        """
        return uniq_id(
            (
                self.name,
                self.source,
                self.schema_out,
                self.title,
                self.description,
            )
        )


@dataclasses.dataclass
class SchemaMetaFields:
    """
    Dataclass representing a collection of meta fields for a schema, including
    origin, include, exclude, and inheritance status.

    Tags: RAG, EXPORT
    """

    origin: dict[str, SchemaMetaField] = dataclasses.field(default_factory=dict)
    include: dict[str, SchemaMetaField] = dataclasses.field(default_factory=dict)
    exclude: dict[str, None] = dataclasses.field(default_factory=dict)
    is_inherit: bool = True


@dataclasses.dataclass
class SchemaInclusion:
    """
    Dataclass representing a schema inclusion, including fields structure and meta
    fields structure.

    Tags: RAG, EXPORT
    """

    fields_struct: 'SchemaFields' = None
    meta_fields_struct: 'SchemaMetaFields' = None


@dataclasses.dataclass
class SchemaInclusions:
    """
    Dataclass representing a collection of schema inclusions, including origin,
    include, exclude, and inheritance status.

    Tags: RAG, EXPORT
    """

    origin: dict[str, None | SchemaInclusion] = dataclasses.field(default_factory=dict)
    include: dict[str, None | SchemaInclusion] = dataclasses.field(default_factory=dict)
    exclude: dict[str, None] = dataclasses.field(default_factory=dict)
    is_inherit: bool = True

    def __bool__(self):
        """
        Returns a boolean indicating whether there are any origin or include schema
        inclusions.
        """
        return bool(self.origin or self.include)
