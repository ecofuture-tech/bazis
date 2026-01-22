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

from django.conf import settings

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import (
    DependentEntity,
    ExtendedEntity,
    ParentEntity,
)

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_routes(sample_app):
    # parent_entity
    # LIST
    factories.ParentEntityFactory.create_batch(50)

    response = get_api_client(sample_app).get('/api/v1/entity/parent_entity/')

    assert response.status_code == 200

    data = response.json()

    assert len(data['data']) == settings.BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT

    for it in data['data']:
        assert it['type'] == 'entity.parent_entity'
        assert it['bs:action'] == 'view'
        assert 'id' in it
        assert 'attributes' in it
        assert 'relationships' in it

        _attributes = it['attributes']
        _relationships = it['relationships']

        assert 'dt_created' in _attributes
        assert 'dt_updated' in _attributes
        assert 'name' in _attributes
        assert 'description' in _attributes
        assert 'is_active' in _attributes
        assert 'price' in _attributes
        assert 'dt_approved' in _attributes
        assert 'state' in _attributes
        assert 'field' in _attributes
        assert 'extended_entity_price' in _attributes
        assert 'active_children' in _attributes
        assert 'count_active_children' in _attributes
        assert 'has_inactive_children' in _attributes

        assert 'child_entities' in _relationships
        assert 'extended_entity' in _relationships
        assert 'dependent_entities' in _relationships

        _extended_entity = _relationships['extended_entity']
        _dependent_entities = _relationships['dependent_entities']
        _child_entities = _relationships['child_entities']

        assert _extended_entity['data']['id'] is not None
        assert _extended_entity['data']['type'] == 'entity.extended_entity'
        assert isinstance(_dependent_entities['data'], list)
        assert _dependent_entities['data'][0]['id'] is not None
        assert _dependent_entities['data'][0]['type'] == 'entity.dependent_entity'
        assert _child_entities['data'] == []

    # RETRIEVE
    parent_entity = ParentEntity.objects.first()
    child_entity = factories.ChildEntityFactory.create()
    parent_entity.child_entities.add(child_entity)
    parent_entity.refresh_from_db()

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/parent_entity/{str(parent_entity.id)}/'
    )

    assert response.status_code == 200

    data = response.json()

    assert data['data']['type'] == 'entity.parent_entity'
    assert data['data']['bs:action'] == 'view'
    assert data['data']['id'] == str(parent_entity.id)

    assert data['data']['attributes']['dt_created'] == parent_entity.dt_created.isoformat().replace(
        '+00:00', 'Z'
    )
    assert data['data']['attributes']['dt_updated'] == parent_entity.dt_updated.isoformat().replace(
        '+00:00', 'Z'
    )
    assert data['data']['attributes']['name'] == parent_entity.name
    assert data['data']['attributes']['description'] == parent_entity.description
    assert data['data']['attributes']['is_active'] == parent_entity.is_active
    assert data['data']['attributes']['price'] == str(parent_entity.price)
    assert data['data']['attributes'][
        'dt_approved'
    ] == parent_entity.dt_approved.isoformat().replace('+00:00', 'Z')
    assert data['data']['attributes']['state'] == parent_entity.state
    assert data['data']['attributes']['field'] == parent_entity.field
    assert 'extended_entity_price' in data['data']['attributes']
    assert 'active_children' in data['data']['attributes']
    assert 'count_active_children' in data['data']['attributes']
    assert 'has_inactive_children' in data['data']['attributes']

    _relationships = data['data']['relationships']

    assert 'child_entities' in _relationships
    assert 'extended_entity' in _relationships
    assert 'dependent_entities' in _relationships

    _extended_entity = _relationships['extended_entity']
    _dependent_entities = _relationships['dependent_entities']
    _child_entities = _relationships['child_entities']

    assert _extended_entity['data']['id'] is not None
    assert _extended_entity['data']['type'] == 'entity.extended_entity'
    assert isinstance(_dependent_entities['data'], list)
    assert _dependent_entities['data'][0]['id'] is not None
    assert _dependent_entities['data'][0]['type'] == 'entity.dependent_entity'
    assert _child_entities['data'] is not None
    assert _child_entities['data'][0]['id'] == str(child_entity.id)
    assert _child_entities['data'][0]['type'] == 'entity.child_entity'

    # SCHEMA
    response = get_api_client(sample_app).get('/api/v1/entity/parent_entity/schema_list/')
    assert response.status_code == 200

    data = response.json()
    assert data['$defs'] is not None
    assert data['properties'] is not None
    assert data['properties']['data'] is not None
    assert data['properties']['meta'] is not None
    assert data['required'] is not None

    check_data = 0
    for schema in data['$defs'].keys():
        if (
            schema.endswith('Attributes__Attributes')
            or schema.endswith('Relationships__Data__child_entities')
            or schema.endswith('Relationships__Data__dependent_entities')
            or schema.endswith('Relationships__Data__extended_entity')
        ):
            check_data += 1
        if schema.endswith('Attributes__Attributes'):
            assert data['$defs'][schema]['properties']['name']['filterLabel'] == 'name'
            assert data['$defs'][schema]['properties']['name']['orderLabel'] == 'name'

    assert check_data == 4

    response = get_api_client(sample_app).get('/api/v1/entity/parent_entity/schema_create/')
    assert response.status_code == 200

    data = response.json()
    assert data['$defs'] is not None
    assert data['properties'] is not None
    assert data['properties']['data'] is not None
    assert data['properties']['meta'] is not None
    assert data['required'] is not None

    check_data = 0
    for schema in data['$defs'].keys():
        if (
            schema.endswith('Attributes__Attributes')
            or schema.endswith('Relationships__Data__child_entities')
            or schema.endswith('Relationships__Data__dependent_entities')
            or schema.endswith('Relationships__Data__extended_entity')
        ):
            check_data += 1
        if schema.endswith('Attributes__Attributes'):
            assert data['$defs'][schema]['properties']['price']['filterLabel'] == 'price'
            assert data['$defs'][schema]['properties']['price']['orderLabel'] == 'price'

    assert check_data == 4

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/parent_entity/{str(parent_entity.id)}/schema_retrieve/'
    )
    assert response.status_code == 200

    data = response.json()
    assert data['$defs'] is not None
    assert data['properties'] is not None
    assert data['properties']['data'] is not None
    assert data['properties']['meta'] is not None
    assert data['required'] is not None

    check_data = 0
    for schema in data['$defs'].keys():
        if (
            schema.endswith('Attributes__Attributes')
            or schema.endswith('Relationships__Data__child_entities')
            or schema.endswith('Relationships__Data__dependent_entities')
            or schema.endswith('Relationships__Data__extended_entity')
        ):
            check_data += 1

        if schema.endswith('Attributes__Attributes'):
            assert data['$defs'][schema]['properties']['is_active']['filterLabel'] == 'is_active'
            assert data['$defs'][schema]['properties']['is_active']['orderLabel'] == 'is_active'

    assert check_data == 4

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/parent_entity/{str(parent_entity.id)}/schema_update/'
    )
    assert response.status_code == 200

    data = response.json()
    assert data['$defs'] is not None
    assert data['properties'] is not None
    assert data['properties']['data'] is not None
    assert data['properties']['meta'] is not None
    assert data['required'] is not None

    check_data = 0
    for schema in data['$defs'].keys():
        if (
            schema.endswith('Attributes__Attributes')
            or schema.endswith('Relationships__Data__child_entities')
            or schema.endswith('Relationships__Data__dependent_entities')
            or schema.endswith('Relationships__Data__extended_entity')
        ):
            check_data += 1
        if schema.endswith('Attributes__Attributes'):
            assert data['$defs'][schema]['properties']['dt_updated']['filterLabel'] == 'dt_updated'
            assert data['$defs'][schema]['properties']['dt_updated']['orderLabel'] == 'dt_updated'

    assert check_data == 4

    # child_entity
    # LIST
    factories.ChildEntityFactory.create_batch(20)

    response = get_api_client(sample_app).get('/api/v1/entity/child_entity/')

    assert response.status_code == 200

    data = response.json()

    assert len(data['data']) == settings.BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT

    for it in data['data']:
        assert it['type'] == 'entity.child_entity'
        assert it['bs:action'] == 'view'
        assert 'id' in it
        assert 'attributes' in it
        assert 'relationships' in it

        _attributes = it['attributes']
        _relationships = it['relationships']

        assert 'dt_created' in _attributes
        assert 'dt_updated' in _attributes
        assert 'child_name' in _attributes
        assert 'child_description' in _attributes
        assert 'child_is_active' in _attributes
        assert 'child_price' in _attributes
        assert 'child_dt_approved' in _attributes

        assert 'parent_entities' in _relationships

    # RETRIEVE
    child_entity.refresh_from_db()
    response = get_api_client(sample_app).get(
        f'/api/v1/entity/child_entity/{str(child_entity.id)}/'
    )

    assert response.status_code == 200

    data = response.json()

    assert data['data']['type'] == 'entity.child_entity'
    assert data['data']['bs:action'] == 'view'
    assert data['data']['id'] == str(child_entity.id)

    assert data['data']['attributes']['dt_created'] == child_entity.dt_created.isoformat().replace(
        '+00:00', 'Z'
    )
    assert data['data']['attributes']['dt_updated'] == child_entity.dt_updated.isoformat().replace(
        '+00:00', 'Z'
    )
    assert data['data']['attributes']['child_name'] == child_entity.child_name
    assert data['data']['attributes']['child_description'] == child_entity.child_description
    assert data['data']['attributes']['child_is_active'] == child_entity.child_is_active
    assert data['data']['attributes']['child_price'] == str(child_entity.child_price)
    assert data['data']['attributes'][
        'child_dt_approved'
    ] == child_entity.child_dt_approved.isoformat().replace('+00:00', 'Z')

    _relationships = data['data']['relationships']

    assert 'parent_entities' in _relationships

    _parent_entities = _relationships['parent_entities']

    assert len(_parent_entities['data']) == 1
    assert _parent_entities['data'][0]['id'] == str(parent_entity.id)
    assert _parent_entities['data'][0]['type'] == 'entity.parent_entity'

    # dependent_entity
    # LIST
    response = get_api_client(sample_app).get('/api/v1/entity/dependent_entity/')
    assert response.status_code == 200

    # RETRIEVE
    dependent_entity = DependentEntity.objects.first()
    response = get_api_client(sample_app).get(
        f'/api/v1/entity/dependent_entity/{str(dependent_entity.id)}/'
    )
    assert response.status_code == 200

    # extended_entity
    # LIST
    response = get_api_client(sample_app).get('/api/v1/entity/extended_entity/')
    assert response.status_code == 200

    # RETRIEVE
    extended_entity = ExtendedEntity.objects.first()
    response = get_api_client(sample_app).get(
        f'/api/v1/entity/extended_entity/{str(extended_entity.id)}/'
    )
    assert response.status_code == 200
