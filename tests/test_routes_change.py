from urllib.parse import urlencode

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_routes_update(sample_app):
    # update parent
    parent_entity = factories.ParentEntityFactory.create(
        name='Parent test name',
        child_entities=False,
        dependent_entities=None,
        extended_entity=None,
    )
    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/parent_entity/{parent_entity.pk}/',
        json_data={
            'data': {
                'id': str(parent_entity.pk),
                'type': 'entity.parent_entity',
                'bs:action': 'change',
                'attributes': {
                    'name': 'New parent test name',
                },
            },
        },
    )
    assert response.status_code == 200

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.parent_entity'
    assert it['bs:action'] == 'view'
    assert it['attributes']['name'] == 'New parent test name'

    # update child
    child_entity = factories.ChildEntityFactory.create(
        child_name='Child test name',
        child_is_active=True,
    )

    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/child_entity/{child_entity.pk}/',
        json_data={
            'data': {
                'id': str(child_entity.pk),
                'type': 'entity.child_entity',
                'bs:action': 'change',
                'attributes': {
                    'child_is_active': False,
                },
                # 'relationships': {
                #     'parent_entities': {
                #         'data': [{
                #             'id': str(parent_entity.pk),
                #             'type': 'entity.parent_entity',
                #         }],
                #     },
                # },
            },
        },
    )
    assert response.status_code == 200

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.child_entity'
    assert it['bs:action'] == 'view'
    assert it['attributes']['child_is_active'] is False
    assert it['attributes']['child_name'] == 'Child test name'
    # assert len(it['relationships']['parent_entities']['data']) == 1
    # assert it['relationships']['parent_entities']['data'][0]['id'] == str(parent_entity.pk)

    # update extended
    extended_entity = factories.ExtendedEntityFactory.create(
        extended_name='Extended test name',
        extended_is_active=True,
        extended_price='100.00',
        parent_entity=parent_entity,
    )
    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/extended_entity/{extended_entity.pk}/',
        json_data={
            'data': {
                'id': str(extended_entity.pk),
                'type': 'entity.extended_entity',
                'bs:action': 'change',
                'attributes': {
                    'extended_name': 'New extended test name',
                    'extended_is_active': False,
                    'extended_price': '101.00',
                },
            },
        },
    )
    assert response.status_code == 200

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.extended_entity'
    assert it['bs:action'] == 'view'
    assert it['attributes']['extended_is_active'] is False
    assert it['attributes']['extended_name'] == 'New extended test name'
    assert it['attributes']['extended_price'] == '101.00'
    assert it['relationships']['parent_entity']['data']['id'] == str(parent_entity.pk)

    # update dependent
    new_parent_entity = factories.ParentEntityFactory.create(
        name='New parent test name',
        dependent_entities=None,
    )

    dependent_entity = factories.DependentEntityFactory.create(
        dependent_name='Dependent test name',
        parent_entity=parent_entity,
    )

    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/dependent_entity/{dependent_entity.pk}/',
        json_data={
            'data': {
                'id': str(dependent_entity.pk),
                'type': 'entity.dependent_entity',
                'bs:action': 'change',
                'attributes': {},
                'relationships': {
                    'parent_entity': {
                        'data': {
                            'id': str(new_parent_entity.pk),
                            'type': 'entity.parent_entity',
                        },
                    },
                },
            },
        },
    )
    assert response.status_code == 200

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.dependent_entity'
    assert it['bs:action'] == 'view'
    assert it['attributes']['dependent_name'] == 'Dependent test name'
    assert it['relationships']['parent_entity']['data']['id'] == str(new_parent_entity.pk)


@pytest.mark.django_db(transaction=True)
def test_routes_included_update(sample_app):
    parent_entity = factories.ParentEntityFactory.create(
        name='Parent test name',
        child_entities=False,
        dependent_entities=None,
        extended_entity=None,
    )
    extended_entity = factories.ExtendedEntityFactory.create(
        extended_name='Extended test name', parent_entity=parent_entity
    )
    dependent_entity = factories.DependentEntityFactory.create(
        dependent_name='Dependent test name', parent_entity=parent_entity
    )
    child_entity_1 = factories.ChildEntityFactory.create(
        child_name='Child test name',
    )
    child_entity_2 = factories.ChildEntityFactory.create(
        child_name='Child test name 2',
    )
    child_entity_3 = factories.ChildEntityFactory.create(
        child_name='Child test name 3',
    )
    parent_entity.child_entities.add(child_entity_1)
    parent_entity.child_entities.add(child_entity_2)
    parent_entity.child_entities.add(child_entity_3)

    query = urlencode(
        {
            'include': 'extended_entity,dependent_entities,child_entities',
        }
    )

    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/parent_entity/{parent_entity.pk}/?{query}',
        json_data={
            'data': {
                'id': str(parent_entity.pk),
                'type': 'entity.parent_entity',
                'bs:action': 'change',
                'attributes': {
                    'name': 'New parent test name',
                },
            },
            'included': [
                {
                    'id': str(extended_entity.pk),
                    'type': 'entity.extended_entity',
                    'bs:action': 'change',
                    'attributes': {
                        'extended_name': 'New extended test name',
                    },
                },
                {
                    'type': 'entity.dependent_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'dependent_name': 'Dependent test name 2',
                        'dependent_description': 'Dependent test description 2',
                        'dependent_is_active': True,
                        'dependent_price': '500.41',
                        'dependent_dt_approved': '2024-01-14T17:54:12Z',
                    },
                    'relationships': {
                        'parent_entity': {
                            'data': {
                                'id': str(parent_entity.pk),
                                'type': 'entity.parent_entity',
                            },
                        },
                    },
                },
                {
                    'id': str(dependent_entity.pk),
                    'type': 'entity.dependent_entity',
                    'bs:action': 'change',
                    'attributes': {
                        'dependent_name': 'New dependent test name',
                    },
                },
                {
                    'id': str(child_entity_1.pk),
                    'type': 'entity.child_entity',
                    'bs:action': 'change',
                    'attributes': {
                        'child_name': 'New child test name',
                    },
                },
                {
                    'type': 'entity.child_entity',
                    'bs:action': 'add',
                    'attributes': {
                        'child_name': 'Child test name 4',
                        'child_description': 'Child test description 4',
                        'child_is_active': True,
                        'child_price': '421.74',
                        'child_dt_approved': '2024-01-09T03:51:12Z',
                    },
                    'relationships': {
                        'parent_entities': {
                            'data': [
                                {
                                    'id': str(parent_entity.pk),
                                    'type': 'entity.parent_entity',
                                }
                            ],
                        },
                    },
                },
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    it = data['data']
    assert it['type'] == 'entity.parent_entity'
    assert it['bs:action'] == 'view'

    relationships = it['relationships']

    assert relationships['extended_entity']['data']['type'] == 'entity.extended_entity'
    assert relationships['dependent_entities']['data'][0]['type'] == 'entity.dependent_entity'
    assert relationships['dependent_entities']['data'][1]['type'] == 'entity.dependent_entity'
    assert relationships['child_entities']['data'][0]['type'] == 'entity.child_entity'
    assert relationships['child_entities']['data'][1]['type'] == 'entity.child_entity'
    assert relationships['child_entities']['data'][2]['type'] == 'entity.child_entity'
    assert relationships['child_entities']['data'][3]['type'] == 'entity.child_entity'


@pytest.mark.django_db(transaction=True)
def test_routes_update_error(sample_app):
    parent_entity = factories.ParentEntityFactory.create(
        name='Parent test name',
        child_entities=False,
        dependent_entities=None,
        extended_entity=None,
    )

    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/parent_entity/{parent_entity.pk}/',
        json_data={
            'data': {
                'id': str(parent_entity.pk),
                'type': 'entity.parent_entity',
                'bs:action': 'change',
                'attributes': {
                    'is_active': 'wrong value',
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
                'title': 'bool_parsing',
                'code': 'ERR_VALIDATE',
                'detail': 'Input should be a valid boolean, unable to interpret input',
                'source': {'pointer': '/attributes/is_active'},
            }
        ]
    }
