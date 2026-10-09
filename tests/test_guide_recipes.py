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
The recipes of the guide of the core (`bazis/core/AGENTS.md`): a calculated field in the
schema of a route, the numbers of `UniqNumberMixin`, a report on a proxy model.
"""

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Card, Memo


MEMOS = '/api/v1/catalog/memo/'
BUSY = '/api/v1/catalog/busy_memo/'


@pytest.mark.django_db(transaction=True)
def test_calculated_field_in_the_schema(sample_app):
    """`include={'cards_count': None}`: read-only, not required, of the type it returns."""
    client = get_api_client(sample_app)

    schema = client.get(f'{MEMOS}schema_create/').json()
    attributes = schema['$defs']
    found = [
        props['cards_count']
        for it in attributes.values()
        if 'cards_count' in (props := it.get('properties', {}))
    ]
    assert found and all(it.get('readOnly') for it in found)
    assert all(it['type'] == 'integer' for it in found)

    # not a filter: not declared `as_filter`
    response = client.get(f'{MEMOS}?filter=cards_count=1')
    assert response.status_code == 400, response.text


@pytest.mark.django_db(transaction=True)
def test_uniq_number(sample_app):
    """
    The number comes from a sequence of the resource (django-sequences, installed by the
    core) on the first save, and is kept on the next ones.
    """
    client = get_api_client(sample_app)
    numbers = []
    for title in ('a', 'b'):
        response = client.post(
            MEMOS, json_data={'data': {'type': 'catalog.memo', 'attributes': {'title': title}}}
        )
        assert response.status_code == 201, response.text
        numbers.append(int(response.json()['data']['attributes']['number']))
    assert numbers[1] == numbers[0] + 1

    memo = Memo.objects.get(title='a')
    memo.title = 'c'
    memo.save()
    memo.refresh_from_db()
    assert memo.uniq_number == numbers[0]


@pytest.mark.django_db(transaction=True)
def test_report_on_a_proxy_model(sample_app):
    """
    The route of a proxy model narrows its list and items in `get_queryset`; its calculated
    fields include one declared by a callable (`first_card`).
    """
    busy = Memo.objects.create(title='busy')
    Card.objects.create(name='a', memo=busy)
    Card.objects.create(name='b', memo=busy)
    idle = Memo.objects.create(title='idle')
    client = get_api_client(sample_app)

    response = client.get(BUSY)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert [(it['type'], str(it['id'])) for it in data] == [('catalog.busy_memo', str(busy.pk))]
    assert data[0]['attributes'] == {'title': 'busy', 'cards_count': 2, 'first_card': 'a'}

    response = client.get(f'{BUSY}{busy.pk}/')
    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['first_card'] == 'a'

    assert client.get(f'{BUSY}{idle.pk}/').status_code == 404
    # no writes
    response = client.post(
        BUSY, json_data={'data': {'type': 'catalog.busy_memo', 'attributes': {'title': 'x'}}}
    )
    assert response.status_code in (404, 405), response.text
