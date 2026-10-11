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

"""
`SchemaResourceBuilder(fields=...)`: None is every field of the factory, an empty list is
none (a package that hides every field, as the field permissions of bazis-permit).
"""

import pytest


def test_empty_fields_are_none(sample_app):
    from entity.routes import ChildEntityRouteSet

    from bazis.core.schemas.builders import SchemaResourceBuilder
    from bazis.core.schemas.enums import CrudApiAction

    factory = ChildEntityRouteSet.schema_factories[CrudApiAction.RETRIEVE]

    def schema_fields(schema) -> set[str]:
        return set(schema.model_fields['attributes'].annotation.model_fields) | set(
            schema.model_fields['relationships'].annotation.model_fields
        )

    every = schema_fields(SchemaResourceBuilder(factory).build(is_response_schema=True))
    assert 'child_name' in every
    assert schema_fields(SchemaResourceBuilder(factory, fields=None).build()) >= {'child_name'}
    assert schema_fields(SchemaResourceBuilder(factory, fields=[]).build()) == set()


def test_list_object_of_an_unknown_schema_key(caplog):
    """
    `JsonApiTopListSchema`: an object takes the member of its `_schema_key`; one whose key
    has no member takes the member without a key (the fields shown in every object) and is
    logged, not a 500; without such a member it is an error.
    """
    from types import SimpleNamespace

    from bazis.core.schemas.schemas import JsonApiTopListSchema

    every, some = object(), object()
    types_map = {None: every, 1: some}
    item = SimpleNamespace(pk=7, _schema_key=1)
    assert JsonApiTopListSchema._item_type(types_map, item) is some
    assert JsonApiTopListSchema._item_type(types_map, SimpleNamespace(pk=8)) is every
    assert not caplog.records

    item._schema_key = 5
    assert JsonApiTopListSchema._item_type(types_map, item) is every
    assert 'no member for the _schema_key 5 of SimpleNamespace 7' in caplog.text
    with pytest.raises(KeyError):
        JsonApiTopListSchema._item_type({1: some}, item)
