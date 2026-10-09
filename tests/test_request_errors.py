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
A malformed request document is 422 `ERR_VALIDATE` pointing into the document the client
sent: a related id that cannot be a key of the related model, a document without `data`,
the body of the relationships endpoints (`/data`, `/data/<index>/id`, without the names of
the Pydantic types).
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


CHILDREN = '/api/v1/entity/child_entity/'
DEPENDENTS = '/api/v1/entity/dependent_entity/'


def send(client, method, url, payload):
    return client.client.request(method, url, headers=client.headers, json=payload)


def validation_errors(response) -> list[dict]:
    assert response.status_code == 422, response.text
    errors = response.json()['errors']
    assert {it['code'] for it in errors} == {'ERR_VALIDATE'}
    return errors


def sources(response) -> list[dict]:
    return [it.get('source') for it in validation_errors(response)]


@pytest.mark.django_db(transaction=True)
def test_related_id_that_is_not_a_key(sample_app):
    """It was a 500 (the Django ValidationError of the primary key of the related model)."""
    client = get_api_client(sample_app)
    child = factories.ChildEntityFactory.create()
    parent = factories.ParentEntityFactory.create()

    response = send(client, 'PATCH', f'{CHILDREN}{child.id}/', {
        'data': {
            'id': str(child.id),
            'type': 'entity.child_entity',
            'relationships': {
                'parent_entities': {'data': [
                    {'type': 'entity.parent_entity', 'id': str(parent.id)},
                    {'type': 'entity.parent_entity', 'id': 'not-a-key'},
                ]},
            },
        },
    })
    assert sources(response) == [{
        'pointer': '/data/relationships/parent_entities/data/1/id',
        'id': str(child.id),
        'type': 'entity.child_entity',
    }]
    assert not child.parent_entities.exists()

    response = send(client, 'POST', DEPENDENTS, {
        'data': {
            'type': 'entity.dependent_entity',
            'attributes': {'dependent_name': 'Dependent'},
            'relationships': {
                'parent_entity': {'data': {'type': 'entity.parent_entity', 'id': '12'}},
            },
        },
    })
    assert sources(response) == [{'pointer': '/data/relationships/parent_entity/data/id'}]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('payload', [{}, {'meta': {}}, [], 'data'])
def test_document_without_data(sample_app, payload):
    """A document without `data` was a 500 (a TypeError of the schema)."""
    client = get_api_client(sample_app)
    child = factories.ChildEntityFactory.create()

    for method, url in (('POST', CHILDREN), ('PATCH', f'{CHILDREN}{child.id}/')):
        response = send(client, method, url, payload)
        errors = validation_errors(response)
        if isinstance(payload, dict):
            assert [(it['title'], it['source']) for it in errors] == [
                ('missing', {'pointer': '/data'})
            ], method
        else:
            # not an object: the document itself
            assert [it['source'] for it in errors] == [{'pointer': ''}], method


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'field, data, pointers',
    [
        # to-many
        ('parent_entities', {'type': 'entity.parent_entity', 'id': 'x'}, ['/data']),
        ('parent_entities', [{'type': 'entity.parent_entity'}], ['/data/0/id']),
        (
            'parent_entities',
            [{'type': 'entity.parent_entity', 'id': 'x'}, {'id': 'y'}],
            ['/data/1/type'],
        ),
        ('parent_entities', [{'type': 'entity.parent_entity', 'id': 'x'}], ['/data/0/id']),
        ('parent_entities', 'x', ['/data']),
        # to-one
        ('parent_entity', [{'type': 'entity.parent_entity', 'id': 'x'}], ['/data']),
        ('parent_entity', {'type': 'entity.parent_entity'}, ['/data/id']),
        ('parent_entity', {'type': 'entity.parent_entity', 'id': 'x'}, ['/data/id']),
    ],
)
def test_relationships_endpoint_errors_point_into_its_body(sample_app, field, data, pointers):
    """
    The body of the relationships endpoints is `{"data": ...}`: the errors point there, not
    to `/data/relationships/<field>/data` of an update nor to the Pydantic types of the
    union (`/data/list[ResourceIdentifier]/0/id`); an id that cannot be a key of the
    related model is one of them (it was 400 `ERR_REQUEST`).
    """
    if field == 'parent_entities':
        url = f'{CHILDREN}{factories.ChildEntityFactory.create().id}/relationships/{field}'
    else:
        dependent = factories.DependentEntityFactory.create(
            parent_entity=factories.ParentEntityFactory.create()
        )
        url = f'{DEPENDENTS}{dependent.id}/relationships/{field}'

    client = get_api_client(sample_app)
    for method in ('PATCH', 'POST', 'DELETE') if field == 'parent_entities' else ('PATCH',):
        response = send(client, method, url, {'data': data})
        assert [it['pointer'] for it in sources(response)] == pointers, method
        assert all(set(it) == {'pointer'} for it in sources(response)), method
