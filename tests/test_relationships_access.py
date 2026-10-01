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
The relationships endpoints change only the relationships the update schema of the route
exposes, with the checks of an update.
"""

import json

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_relationship_not_in_schema_is_rejected(sample_app):
    child = factories.ChildEntityFactory.create()
    other_child = factories.ChildEntityFactory.create()
    protected = factories.WithProtectedEntityFactory.create(child=other_child)
    payload = {'data': [{'type': 'entity.with_protected_entity', 'id': str(protected.id)}]}
    url = f'/api/v1/entity/child_entity/{child.id}/relationships/withprotectedentity_set'

    client = get_api_client(sample_app)
    for method in ('POST', 'PATCH', 'DELETE'):
        response = client.client.request(method, url, headers=client.headers, json=payload)
        assert response.status_code == 403, method
        assert response.json()['errors'][0]['code'] == 'ERR_RELATIONSHIP_READONLY'

    protected.refresh_from_db()
    assert protected.child_id == other_child.id


@pytest.mark.django_db(transaction=True)
def test_unknown_relationship_is_rejected(sample_app):
    child = factories.ChildEntityFactory.create()
    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/child_entity/{child.id}/relationships/unknown',
        data=json.dumps({'data': []}),
    )
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_relationship_of_missing_item(sample_app):
    response = get_api_client(sample_app).patch(
        '/api/v1/entity/child_entity/9b657232-4178-4d7f-8b0c-e8ab16f2b309/relationships/parent_entities',
        data=json.dumps({'data': []}),
    )
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_relationship_of_invalid_type_is_rejected(sample_app):
    child = factories.ChildEntityFactory.create()
    response = get_api_client(sample_app).patch(
        f'/api/v1/entity/child_entity/{child.id}/relationships/parent_entities',
        data=json.dumps({'data': {'type': 'entity.parent_entity', 'id': 'not-a-list'}}),
    )
    assert response.status_code == 422
