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
An id that cannot be a primary key of the model is an item that does not exist: every
route of an item answers 404 (the response its OpenAPI operation documents), never 500.
"""

import pytest
from bazis_test_utils.utils import get_api_client


URL = '/api/v1/entity/child_entity'

ROUTES = [
    ('GET', '/{id}/'),
    ('PATCH', '/{id}/'),
    ('DELETE', '/{id}/'),
    ('GET', '/{id}/schema_retrieve/'),
    ('GET', '/{id}/schema_update/'),
    ('GET', '/{id}/dict_data/'),
    ('POST', '/{id}/relationships/parent_entities'),
    ('PATCH', '/{id}/relationships/parent_entities'),
    ('DELETE', '/{id}/relationships/parent_entities'),
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('item_id', ['not-a-uuid', '12345'])
@pytest.mark.parametrize('method, path', ROUTES)
def test_invalid_item_id_is_not_found(sample_app, method, path, item_id):
    client = get_api_client(sample_app)
    # a relationship to change: an empty one is answered 204 without looking the item up
    related = {'type': 'entity.parent_entity', 'id': '9b657232-4178-4d7f-8b0c-e8ab16f2b309'}
    payload = {'data': [related]} if 'relationships' in path else {'data': {}}
    response = client.client.request(
        method,
        URL + path.format(id=item_id),
        headers=client.headers,
        json=payload if method != 'GET' else None,
    )

    assert response.status_code == 404, response.text
    error = response.json()['errors'][0]
    assert error['status'] == 404
