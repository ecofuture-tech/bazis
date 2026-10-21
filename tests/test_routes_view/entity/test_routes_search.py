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

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import (
    ChildEntity,
    ParentEntity,
)

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_routes_searching(sample_app):
    searching_phrases = [
        'Simple text for searching',
        'Another simple text for searching',
        'This is a simple text for searching',
        'Complex text for searching',
        'Another complex text for searching',
        'This is a complex text for searching',
    ]

    for phrase in searching_phrases:
        factories.ParentEntityFactory.create(description=phrase, child_entities=True)

    query = urlencode(
        {
            'filter': 'description__$search=complex|description__$search=this',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    for it in data['data']:
        description = it['attributes']['description'].lower()
        assert 'complex' in description or 'this' in description

    child = factories.ChildEntityFactory.create(child_description='Child text')
    parent = ParentEntity.objects.first()
    parent.child_entities.add(child)

    query = urlencode(
        {
            'filter': 'child_entities__child_description__$search=child',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    for it in data['data']:
        assert ChildEntity.objects.filter(
            parent_entities=it['id'],
            child_description__icontains='child',
        ).exists()


@pytest.mark.django_db(transaction=True)
def test_search_by_default(sample_app):
    """
    The route of the parent entities declares no `search_fields`: `search` searches their
    text fields (name, description), not the choices (state), the numbers (price) nor the
    calculated fields. A word is a literal substring: `%`, `_` and the metacharacters of a
    regex match themselves, the commas split the words, the null characters are dropped.
    """
    names = {
        'juice': ParentEntity.objects.create(name='Juice 100%', description='Fresh, cold'),
        'thousand': ParentEntity.objects.create(name='Juice 1000', description='Bottled'),
        'snake': ParentEntity.objects.create(name='snake_case', description=None),
        'camel': ParentEntity.objects.create(name='snakeXcase', description='f(x) = y'),
    }

    def search(text):
        response = get_api_client(sample_app).get(
            '/api/v1/entity/parent_entity/', params={'search': text}
        )
        assert response.status_code == 200, response.text
        found = {it['id'] for it in response.json()['data']}
        return sorted(key for key, it in names.items() if str(it.pk) in found)

    assert search('juice') == ['juice', 'thousand']
    assert search('100%') == ['juice']
    assert search('e_c') == ['snake']
    assert search('f(x)') == ['camel']
    assert search('.*') == []
    assert search('juice fresh') == ['juice']
    assert search('juice,bottled') == ['thousand']
    assert search('juice cold bottled') == []
    assert search('Ju\x00ice 1000') == ['thousand']
    # not the choices, the numbers nor the calculated fields
    ParentEntity.objects.update(state='state_one', price=42)
    assert search('state_one') == []
    assert search('42') == []
    # an empty search does not filter
    assert search(' ') == sorted(names)
