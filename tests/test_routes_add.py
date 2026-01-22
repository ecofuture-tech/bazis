import uuid
from urllib.parse import urlencode

from django.db import IntegrityError

import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.django_db(transaction=True)
def test_routes_add(sample_app):
    # add parent_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/parent_entity/',
        json_data={
            'data': {
                'type': 'entity.parent_entity',
                'bs:action': 'add',
                'attributes': {
                    'name': 'Test name',
                    'description': 'Test description',
                    'is_active': True,
                    'price': '100.49',
                    'dt_approved': '2024-01-12T16:54:12Z',
                    'state': 'state_one',
                    'field': ['first_field'],
                },
            },
        },
    )

    assert response.status_code == 201

    data = response.json()

    it = data['data']
    parent_entity_id = str(it['id'])
    assert it['type'] == 'entity.parent_entity'
    assert it['bs:action'] == 'view'

    attributes = it['attributes']

    assert attributes['name'] == 'Test name'
    assert attributes['description'] == 'Test description'
    assert attributes['is_active'] is True
    assert attributes['price'] == '100.49'
    assert attributes['dt_approved'] == '2024-01-12T16:54:12Z'
    assert attributes['extended_entity_price'] == '0'
    assert attributes['active_children'] == []
    assert attributes['count_active_children'] == 0
    assert attributes['has_inactive_children'] is False

    # add child_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/child_entity/',
        json_data={
            'data': {
                'type': 'entity.child_entity',
                'bs:action': 'add',
                'attributes': {
                    'child_name': 'Child test name',
                    'child_description': 'Child test description',
                    'child_is_active': True,
                    'child_price': '100.00',
                    'child_dt_approved': '2024-06-28T16:54:12Z',
                },
                'relationships': {
                    'parent_entities': {
                        'data': [
                            {
                                'id': parent_entity_id,
                                'type': 'entity.parent_entity',
                            },
                            {
                                'id': '9b657232-4178-4d7f-8b0c-e8ab16f2b309',
                                'type': 'entity.parent_entity',
                            },
                        ],
                    },
                },
            },
        },
    )
    # add dependent_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/dependent_entity/',
        json_data={
            'data': {
                'type': 'entity.dependent_entity',
                'bs:action': 'add',
                'attributes': {
                    'dependent_name': 'Dependent test name',
                    'dependent_description': 'Dependent test description',
                    'dependent_is_active': True,
                    'dependent_price': '100.00',
                    'dependent_dt_approved': '2024-06-28T16:54:12Z',
                },
                'relationships': {
                    'parent_entity': {
                        'data': {
                            'id': parent_entity_id,
                            'type': 'entity.parent_entity',
                        },
                    },
                },
            },
        },
    )

    assert response.status_code == 201

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.dependent_entity'
    assert it['bs:action'] == 'view'

    attributes = it['attributes']

    assert attributes['dependent_name'] == 'Dependent test name'
    assert attributes['dependent_description'] == 'Dependent test description'
    assert attributes['dependent_is_active'] is True
    assert attributes['dependent_price'] == '100.00'
    assert attributes['dependent_dt_approved'] == '2024-06-28T16:54:12Z'

    relationships = it['relationships']
    assert 'parent_entity' in relationships
    assert relationships['parent_entity']['data']['id'] == parent_entity_id
    assert relationships['parent_entity']['data']['type'] == 'entity.parent_entity'

    # add extended_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/extended_entity/',
        json_data={
            'data': {
                'type': 'entity.extended_entity',
                'bs:action': 'add',
                'attributes': {
                    'extended_name': 'Extended test name',
                    'extended_description': 'Extended test description',
                    'extended_is_active': True,
                    'extended_price': '100.00',
                    'extended_dt_approved': '2024-06-28T16:54:12Z',
                },
                'relationships': {
                    'parent_entity': {
                        'data': {
                            'id': parent_entity_id,
                            'type': 'entity.parent_entity',
                        },
                    },
                },
            }
        },
    )

    assert response.status_code == 201

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.extended_entity'
    assert it['bs:action'] == 'view'

    attributes = it['attributes']

    assert attributes['extended_name'] == 'Extended test name'
    assert attributes['extended_description'] == 'Extended test description'
    assert attributes['extended_is_active'] is True
    assert attributes['extended_price'] == '100.00'
    assert attributes['extended_dt_approved'] == '2024-06-28T16:54:12Z'

    relationships = it['relationships']
    assert 'parent_entity' in relationships
    assert relationships['parent_entity']['data']['id'] == parent_entity_id
    assert relationships['parent_entity']['data']['type'] == 'entity.parent_entity'


@pytest.mark.django_db(transaction=True)
def test_routes_included_add(sample_app):
    parent_entity_id = str(uuid.uuid4())

    query = urlencode(
        {
            'include': 'extended_entity,dependent_entities,child_entities',
        }
    )

    response = get_api_client(sample_app).post(
        f'/api/v1/entity/parent_entity/?{query}',
        json_data={
            'data': {
                'id': parent_entity_id,
                'type': 'entity.parent_entity',
                'bs:action': 'add',
                'attributes': {
                    'name': 'Parent test name',
                    'description': 'Parent test description',
                    'is_active': False,
                    'price': '12.56',
                    'dt_approved': '2024-01-12T16:54:12Z',
                    'state': 'state_one',
                    'field': ['first_field'],
                },
            },
            'included': [
                {
                    'type': 'entity.extended_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'extended_name': 'Extended test name',
                        'extended_description': 'Extended test description',
                        'extended_is_active': True,
                        'extended_price': '100.49',
                        'extended_dt_approved': '2024-01-12T16:54:12Z',
                    },
                    'relationships': {
                        'parent_entity': {
                            'data': {
                                'id': parent_entity_id,
                                'type': 'entity.parent_entity',
                            },
                        },
                    },
                },
                {
                    'type': 'entity.dependent_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'dependent_name': 'Dependent test name',
                        'dependent_description': 'Dependent test description',
                        'dependent_is_active': False,
                        'dependent_price': '100.49',
                        'dependent_dt_approved': '2024-01-12T16:54:12Z',
                    },
                    'relationships': {
                        'parent_entity': {
                            'data': {
                                'id': parent_entity_id,
                                'type': 'entity.parent_entity',
                            },
                        },
                    },
                },
                {
                    'type': 'entity.child_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'child_name': 'Child test name',
                        'child_description': 'Child test description',
                        'child_is_active': True,
                        'child_price': '100.49',
                        'child_dt_approved': '2024-01-12T16:54:12Z',
                    },
                    'relationships': {
                        'parent_entities': {
                            'data': [
                                {
                                    'id': parent_entity_id,
                                    'type': 'entity.parent_entity',
                                }
                            ],
                        },
                    },
                },
                {
                    'type': 'entity.child_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'child_name': 'Child test name 2',
                        'child_description': 'Child test description 2',
                        'child_is_active': False,
                        'child_price': '25.19',
                        'child_dt_approved': '2024-01-13T16:54:12Z',
                    },
                    'relationships': {
                        'parent_entities': {
                            'data': [
                                {
                                    'id': parent_entity_id,
                                    'type': 'entity.parent_entity',
                                }
                            ],
                        },
                    },
                },
            ],
        },
    )

    assert response.status_code == 201

    data = response.json()
    print(data)

    it = data['data']
    assert it['type'] == 'entity.parent_entity'
    assert it['bs:action'] == 'view'

    relationships = it['relationships']

    assert relationships['extended_entity']['data']['type'] == 'entity.extended_entity'
    assert relationships['dependent_entities']['data'][0]['type'] == 'entity.dependent_entity'
    assert relationships['child_entities']['data'][0]['type'] == 'entity.child_entity'
    assert relationships['child_entities']['data'][1]['type'] == 'entity.child_entity'


@pytest.mark.django_db(transaction=True)
def test_routes_add_error(sample_app):
    # add parent_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/parent_entity/',
        json_data={
            'data': {
                'type': 'entity.parent_entity',
                'bs:action': 'add',
                'attributes': {
                    'is_active': True,
                    'price': 'wrong value',
                },
            },
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data == {
        'errors': [
            {
                'status': 422,
                'title': 'missing',
                'code': 'ERR_VALIDATE',
                'detail': 'Field required',
                'source': {'pointer': '/attributes/name'},
            },
            {
                'status': 422,
                'title': 'decimal_parsing',
                'code': 'ERR_VALIDATE',
                'detail': 'Input should be a valid decimal',
                'source': {'pointer': '/attributes/price'},
            },
        ]
    }

    # add child_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/child_entity/',
        json_data={
            'data': {
                'type': 'entity.child_entity',
                'bs:action': 'add',
                'attributes': {
                    'child_is_active': False,
                    'child_price': '25.19',
                },
            },
        },
    )
    assert response.status_code == 422

    data = response.json()

    assert data == {
        'errors': [
            {
                'status': 422,
                'title': 'missing',
                'code': 'ERR_VALIDATE',
                'detail': 'Field required',
                'source': {'pointer': '/attributes/child_name'},
            },
        ]
    }

    # add dependent_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/dependent_entity/',
        json_data={
            'data': {
                'type': 'entity.dependent_entity',
                'bs:action': 'add',
                'attributes': {
                    'dependent_description': 'Dependent test description',
                    'dependent_is_active': False,
                    'dependent_price': '25.19',
                    'dependent_dt_approved': '2024-01-13T16:54:12Z',
                },
            },
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data == {
        'errors': [
            {
                'status': 422,
                'title': 'missing',
                'code': 'ERR_VALIDATE',
                'detail': 'Field required',
                'source': {'pointer': '/attributes/dependent_name'},
            },
            {
                'status': 422,
                'title': 'missing',
                'code': 'ERR_VALIDATE',
                'detail': 'Field required',
                'source': {'pointer': '/relationships/parent_entity'},
            },
        ]
    }

    # add extended_entity
    response = get_api_client(sample_app).post(
        '/api/v1/entity/extended_entity/',
        json_data={
            'data': {
                'type': 'entity.extended_entity',
                'bs:action': 'add',
            },
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data == {
        'errors': [
            {
                'status': 422,
                'title': 'missing',
                'code': 'ERR_VALIDATE',
                'detail': 'Field required',
                'source': {'pointer': '/attributes/extended_name'},
            },
            {
                'status': 422,
                'title': 'missing',
                'code': 'ERR_VALIDATE',
                'detail': 'Field required',
                'source': {'pointer': '/relationships/parent_entity'},
            },
        ]
    }

    with pytest.raises(IntegrityError):
        get_api_client(sample_app).post(
            '/api/v1/entity/extended_entity/',
            json_data={
                'data': {
                    'type': 'entity.extended_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'extended_name': 'Extended test name',
                        'extended_description': 'Extended test description',
                        'extended_is_active': False,
                        'extended_price': '25.19',
                        'extended_dt_approved': '2024-01-13T16:54:12Z',
                    },
                    'relationships': {
                        'parent_entity': {
                            'data': {
                                'id': '9b657232-4178-4d7f-8b0c-e8ab16f2b309',
                                'type': 'entity.parent_entity',
                            },
                        },
                    },
                },
            },
        )
