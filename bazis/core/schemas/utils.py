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
