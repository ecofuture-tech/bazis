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

from django.apps import apps

from entity.routes import ParentEntityRouteSet

from bazis.core.schemas.enums import CrudApiAction
from bazis.core.schemas.factory import SchemaFactory
from bazis.core.schemas.fields import SchemaField, SchemaFields


def shown(route_cls, item) -> str:
    return f'{route_cls.__name__}:{item.name}'


def test_callable_source_replaces_a_column_under_its_name():
    """
    A field with a callable source takes its value from the function, even when it is named
    as a column of the model (up to 2.19.0 the factory looked the source up as an attribute
    of the model: TypeError). It names no column, so it is read-only and can neither filter
    nor order.
    """
    model = apps.get_model('entity.ParentEntity')
    factory = SchemaFactory(
        route_cls=ParentEntityRouteSet,
        model=model,
        api_action=CrudApiAction.LIST,
        fields_struct=SchemaFields(
            include={'description': SchemaField(source=shown, title='Shown')}
        ),
    )
    field = factory.fields['description']
    assert field.source is shown
    assert (field.read_only, field.can_filter, field.can_order) == (True, None, None)
    assert field.field_db_attr is None

    attributes = factory.build_resource_schema_response().model_fields['attributes'].annotation
    item = model(name='one', description='stored')
    item.only_fields = ['name', 'description']
    value = attributes.model_validate(item)
    assert (value.name, value.description) == ('one', 'ParentEntityRouteSet:one')

    schema = attributes.model_json_schema()['properties']['description']
    assert schema['title'] == 'Shown'
    assert 'filterLabel' not in schema
    assert 'orderLabel' not in schema
