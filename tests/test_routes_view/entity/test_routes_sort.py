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

from decimal import Decimal

from django.conf import settings
from django.db.models import F

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import ParentEntity

from bazis.core.utils.functools import get_attr

from tests import factories


TEXT_FIELDS = {'name', 'description'}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'sort_param',
    [
        'id',
        'dt_created',
        'dt_updated',
        'name',
        'description',
        'price',
        'dt_approved',
        '-id',
        '-dt_created',
        '-dt_updated',
        '-name',
        '-description',
        '-price',
        '-dt_approved',
    ],
)
def test_routes_sort(sample_app, sort_param):
    parent_entities = factories.ParentEntityFactory.create_batch(50, child_entities=True)

    clean_param = sort_param.lstrip('-')
    descending = sort_param.startswith('-')
    if clean_param in TEXT_FIELDS:
        # text order depends on the database collation (e.g. en_US ignores spaces and case
        # at the first level), which Python sorting does not reproduce
        order = F(clean_param).desc() if descending else F(clean_param).asc()
        parent_entities = list(
            ParentEntity.objects.filter(pk__in=[it.pk for it in parent_entities]).order_by(
                order, 'pk'
            )
        )
    else:
        # equal values are ordered by the primary key (the sort is stable)
        parent_entities = sorted(parent_entities, key=lambda x: x.id)
        parent_entities = sorted(
            parent_entities, key=lambda x: get_attr(x, clean_param), reverse=descending
        )
    # need to refresh objects from the db, as we need to update creation and update dates
    [et.refresh_from_db() for et in parent_entities]

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?sort={sort_param}')

    assert response.status_code == 200

    data = response.json()

    assert len(data['data']) == settings.BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT

    for i, it in enumerate(data['data']):
        obj = parent_entities[i]

        _attributes = it['attributes']
        _relationships = it['relationships']

        assert it['id'] == str(obj.id)
        assert _attributes['dt_created'] == obj.dt_created.isoformat().replace('+00:00', 'Z')
        assert _attributes['dt_updated'] == obj.dt_updated.isoformat().replace('+00:00', 'Z')
        assert _attributes['name'] == obj.name
        assert _attributes['description'] == obj.description
        assert _attributes['is_active'] == obj.is_active
        assert _attributes['price'] == str(obj.price)
        assert _attributes['dt_approved'] == obj.dt_approved.isoformat().replace('+00:00', 'Z')
        assert _attributes['state'] == obj.state
        assert _attributes['field'] == obj.field

        _extended_entity = _relationships['extended_entity']
        _dependent_entities = _relationships['dependent_entities']
        _child_entities = _relationships['child_entities']

        assert _extended_entity['data']['id'] == str(obj.extended_entity.pk)

        for j, _child_entity in enumerate(obj.child_entities.order_by('pk')):
            assert _child_entities['data'][j]['id'] == str(_child_entity.pk)

        for j, _dependent_entity in enumerate(obj.dependent_entities.order_by('pk')):
            assert _dependent_entities['data'][j]['id'] == str(_dependent_entity.pk)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('sort_param', ['price', '-price'])
def test_routes_sort_equal_values_are_ordered_by_pk(sample_app, sort_param):
    parent_entities = factories.ParentEntityFactory.create_batch(
        5, child_entities=False, price=Decimal('10.00')
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?sort={sort_param}')

    assert response.status_code == 200
    assert [it['id'] for it in response.json()['data']] == [
        str(it.id) for it in sorted(parent_entities, key=lambda x: x.id)
    ]
