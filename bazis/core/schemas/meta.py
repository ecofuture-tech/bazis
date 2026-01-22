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
import inspect

from bazis.core.utils.functools import get_class_name, get_class_name_from_method

from .enums import ApiAction
from .fields import CallableContext, SchemaMetaField


_META_FIELDS_FOR_CLASSES = {}


@dataclasses.dataclass
class SchemaMetaFieldForMeth:
    """
    Data class representing a meta field for a method, including API actions and
    field schema.
    """

    api_actions: list[ApiAction]
    field_schema: SchemaMetaField


def meta_field(api_actions: list[ApiAction], *, title: str = None, alias: str = None):
    """
    Decorator to define a meta field for a method, including API actions, title, and
    alias.

    Tags: RAG, EXPORT
    """

    def decor(func):
        """
        Decorator function to register a meta field for a method, including API actions,
        title, and alias.
        """
        class_path = f'{func.__module__}.{get_class_name_from_method(func)}'

        if inspect.ismethod(func):
            source = func
        else:
            source = CallableContext(
                class_path=class_path,
                attr=func.__name__,
            )

        _META_FIELDS_FOR_CLASSES.setdefault(class_path, {})[alias or func.__name__] = (
            SchemaMetaFieldForMeth(
                api_actions=api_actions,
                field_schema=SchemaMetaField(
                    title=title,
                    description=func.__doc__,
                    schema_out=func.__annotations__.get('return'),
                    source=source,
                ),
            )
        )

        return func

    return decor


def get_meta_schemas(cls: type) -> dict[str, SchemaMetaFieldForMeth]:
    """
    Function to retrieve meta schemas for a given class.
    """
    return _META_FIELDS_FOR_CLASSES.get(get_class_name(cls)) or {}
