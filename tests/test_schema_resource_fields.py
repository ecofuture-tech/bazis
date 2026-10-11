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
