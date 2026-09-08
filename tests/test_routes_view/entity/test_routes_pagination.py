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

from urllib.parse import urlencode

from django.conf import settings
from django.test import override_settings

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_pagination_limit_uses_current_setting_and_preserves_validation(sample_app):
    factories.ParentEntityFactory.create_batch(3)
    client = get_api_client(sample_app)
    path = '/api/v1/entity/parent_entity/'

    with override_settings(BAZIS_API_PAGINATION_PAGE_SIZE_MAX=2):
        valid = client.get(f'{path}?page[limit]=2')
        assert valid.status_code == 200
        assert len(valid.json()['data']) == 2
        assert client.get(f'{path}?page[limit]=3').status_code == 422
        assert client.get(f'{path}?page[limit]=-1').status_code == 422

    with override_settings(BAZIS_API_PAGINATION_PAGE_SIZE_MAX=3):
        changed = client.get(f'{path}?page[limit]=3')
        assert changed.status_code == 200
        assert len(changed.json()['data']) == 3


@pytest.mark.django_db(transaction=True)
def test_routes_sort_pagination(sample_app):
    parent_entities = factories.ParentEntityFactory.create_batch(50)
    parent_entities = sorted(parent_entities, key=lambda x: x.id)
    # need to refresh objects from the db, as we need to update creation and update dates
    [et.refresh_from_db() for et in parent_entities]

    page_size = settings.BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT

    query = urlencode(
        {
            'sort': 'id',
            'page[offset]': page_size,
            'page[limit]': page_size,
            'meta': 'pagination',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    assert len(data['data']) == page_size
    assert data['meta'] == {'pagination': {'count': 50, 'limit': 20, 'offset': 20}}

    for i, it in enumerate(data['data']):
        obj = parent_entities[i + page_size]
        assert it['id'] == str(obj.id)

    third_page_query = urlencode(
        {
            'sort': 'id',
            'meta': 'pagination',
            'page[offset]': page_size * 2,
            'page[limit]': page_size,
        }
    )
    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{third_page_query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) == 50 - (page_size * 2)
    assert data['meta'] == {'pagination': {'count': 50, 'limit': 20, 'offset': 40}}

    max_page_size = settings.BAZIS_API_PAGINATION_PAGE_SIZE_MAX
    max_query = urlencode(
        {
            'sort': 'id',
            'page[limit]': max_page_size,
            'meta': 'pagination',
        }
    )
    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{max_query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) == 50
    assert data['meta'] == {'pagination': {'count': 50, 'limit': 1000, 'offset': 0}}
