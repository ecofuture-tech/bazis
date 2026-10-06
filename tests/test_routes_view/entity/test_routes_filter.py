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
from urllib.parse import urlencode

from django.db.models import Q

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import (
    ChildEntity,
    ParentEntityState,
)

from tests import factories
from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_list_filter(sample_app, sample_vehicle_data):
    """Test to check List with filter"""

    query = urlencode(
        {
            'filter': 'gnum=XYZ-123',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/related/entity/vehicle/?{query}')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               "entity_vehiclemodel"."dt_created",
               "entity_vehiclemodel"."dt_updated",
               "entity_vehiclemodel"."id",
               "entity_vehiclemodel"."brand_id",
               "entity_vehiclemodel"."model",
               "entity_vehiclemodel"."engine_type",
               "entity_vehiclemodel"."capacity",
               "entity_vehiclebrand"."dt_created",
               "entity_vehiclebrand"."dt_updated",
               "entity_vehiclebrand"."id",
               "entity_vehiclebrand"."name",
               "entity_country"."dt_created",
               "entity_country"."dt_updated",
               "entity_country"."id",
               "entity_country"."name"
        FROM "entity_vehicle"
        INNER JOIN "entity_vehiclemodel" ON ("entity_vehicle"."vehicle_model_id" = "entity_vehiclemodel"."id")
        INNER JOIN "entity_vehiclebrand" ON ("entity_vehiclemodel"."brand_id" = "entity_vehiclebrand"."id")
        INNER JOIN "entity_country" ON ("entity_vehicle"."country_id" = "entity_country"."id")
        WHERE "entity_vehicle"."gnum" = 'XYZ-123'
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)


@pytest.mark.django_db(transaction=True)
def test_annotated_calcs_list_filter(sample_app, sample_vehicle_data):
    """Test to check related fields List with filter"""

    query = urlencode(
        {
            'filter': 'vehicle_model__capacity=3.50',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/related/entity/vehicle/?{query}')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               "entity_vehiclemodel"."dt_created",
               "entity_vehiclemodel"."dt_updated",
               "entity_vehiclemodel"."id",
               "entity_vehiclemodel"."brand_id",
               "entity_vehiclemodel"."model",
               "entity_vehiclemodel"."engine_type",
               "entity_vehiclemodel"."capacity",
               "entity_vehiclebrand"."dt_created",
               "entity_vehiclebrand"."dt_updated",
               "entity_vehiclebrand"."id",
               "entity_vehiclebrand"."name",
               "entity_country"."dt_created",
               "entity_country"."dt_updated",
               "entity_country"."id",
               "entity_country"."name"
        FROM "entity_vehicle"
        INNER JOIN "entity_vehiclemodel" ON ("entity_vehicle"."vehicle_model_id" = "entity_vehiclemodel"."id")
        INNER JOIN "entity_vehiclebrand" ON ("entity_vehiclemodel"."brand_id" = "entity_vehiclebrand"."id")
        INNER JOIN "entity_country" ON ("entity_vehicle"."country_id" = "entity_country"."id")
        WHERE EXISTS
            (SELECT 1 AS "a"
             FROM "entity_vehiclemodel" U0
             WHERE (U0."id" = ("entity_vehicle"."vehicle_model_id")
                    AND U0."capacity" = 3.50)
             LIMIT 1)
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)


@pytest.mark.django_db(transaction=True)
def test_boolean_fields(sample_app):
    factories.ParentEntityFactory(is_active=False)

    query = urlencode(
        {
            'filter': 'is_active=false',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert it['attributes']['is_active'] is False


@pytest.mark.django_db(transaction=True)
def test_decimal_or(sample_app):
    factories.ParentEntityFactory.create_batch(5, price=100)
    factories.ParentEntityFactory.create_batch(5, price=200)

    query = urlencode(
        {
            'filter': '(price=100|price=200)',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')
    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert Decimal(it['attributes']['price']) in {Decimal(100), Decimal(200)}


@pytest.mark.django_db(transaction=True)
def test_decimal_and(sample_app):
    factories.ParentEntityFactory.create_batch(5, price=150, is_active=True)
    factories.ParentEntityFactory.create_batch(5, price=150, is_active=False)

    query = urlencode(
        {
            'filter': 'price=150&is_active=true',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')
    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert Decimal(it['attributes']['price']) == Decimal(150)
        assert it['attributes']['is_active'] is True


@pytest.mark.django_db(transaction=True)
def test_decimal_negative(sample_app):
    factories.ParentEntityFactory.create_batch(5, price=300)
    factories.ParentEntityFactory.create_batch(5, price=400)

    query = urlencode(
        {
            'filter': '~price=300',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')
    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert Decimal(it['attributes']['price']) != Decimal(300)


@pytest.mark.django_db(transaction=True)
def test_decimal_gte_lte(sample_app):
    factories.ParentEntityFactory.create_batch(30, child_entities=True)

    # TEST: gte, lt, &, |, ()

    query = urlencode(
        {
            'filter': '((price__gte=20&price__lt=50)|(price__gte=500&price__lt=550))',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    for it in data['data']:
        price = Decimal(it['attributes']['price'])
        assert (20 <= price < 50 or 500 <= price < 550) is True


@pytest.mark.django_db(transaction=True)
def test_decimal_isnull(sample_app):
    factories.ParentEntityFactory(price=None, is_active=False)

    query = urlencode(
        {
            'filter': 'price__isnull=1',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) == 1

    for it in data['data']:
        price = it['attributes']['price']
        assert price is None


@pytest.mark.django_db(transaction=True)
def test_decimal_nested(sample_app):
    factories.ParentEntityFactory.create_batch(5, price=500, is_active=True)
    factories.ParentEntityFactory.create_batch(5, price=500, is_active=False)
    factories.ParentEntityFactory.create_batch(5, price=600, is_active=True)

    query = urlencode(
        {
            'filter': '((price=500&is_active=true)|price=600)',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')
    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert (
            Decimal(it['attributes']['price']) == Decimal(500)
            and it['attributes']['is_active'] is True
        ) or Decimal(it['attributes']['price']) == Decimal(600)


@pytest.mark.django_db(transaction=True)
def test_char_field_search_iexact(sample_app):
    factories.ParentEntityFactory.create_batch(3, name='Apple')
    factories.ParentEntityFactory.create_batch(3, name='Pineapple')
    factories.ParentEntityFactory.create_batch(3, name='Banana')

    def names(filter_str):
        response = get_api_client(sample_app).get(
            '/api/v1/entity/parent_entity/', params={'filter': filter_str}
        )
        assert response.status_code == 200
        return sorted(it['attributes']['name'] for it in response.json()['data'])

    # substring, case-insensitive
    assert names('name__$search=APP') == ['Apple'] * 3 + ['Pineapple'] * 3
    # whole value, case-insensitive
    assert names('name__iexact=apple') == ['Apple'] * 3
    assert names('name__istartswith=pine') == ['Pineapple'] * 3
    # full-text (PostgreSQL), string fields only
    assert names('name__search=apple') == ['Apple'] * 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_str',
    [
        # Django lookups that the filter does not support were compared for equality with
        # the whole value (name__in=a,b was name='a,b') and silently gave a wrong result
        'name__in=Apple,Banana',
        'name__icontains=app',
        'name__contains=App',
        'price__in=100,200',
        'is_active__in=true',
        'description__gt=a',
        'field__len=2',
        'dt_approved__date=2024-01-01',
        'name__iexact__extra=Apple',
        'has_inactive_children__in=false',
        # Django has the full-text lookup on string fields only (FieldError before)
        'price__search=1',
        'dt_approved__search=2024',
        'child_entities__child_name__in=a,b',
    ],
)
def test_unsupported_lookup_returns_bad_request(sample_app, filter_str):
    factories.ParentEntityFactory(name='Apple', price=100)

    response = get_api_client(sample_app).get(
        '/api/v1/entity/parent_entity/', params={'filter': filter_str}
    )

    assert response.status_code == 400
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_FILTER'
    assert error['source'] == {'pointer': '/query/filter'}
    assert 'is not supported' in error['detail']


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('field_name', ['description', 'field'])
def test_isnull_text_and_array_fields(sample_app, field_name):
    """`isnull` works for every field kind (a text field searched for the word "true" and
    an array field failed before)."""
    empty = factories.ParentEntityFactory(**{field_name: None})
    filled = factories.ParentEntityFactory(description='text', field=['first_field'])

    def ids(filter_str):
        response = get_api_client(sample_app).get(
            '/api/v1/entity/parent_entity/', params={'filter': filter_str}
        )
        assert response.status_code == 200
        return {it['id'] for it in response.json()['data']}

    assert ids(f'{field_name}__isnull=true') == {str(empty.pk)}
    assert str(filled.pk) in ids(f'{field_name}__isnull=false')
    assert str(empty.pk) not in ids(f'{field_name}__isnull=false')


@pytest.mark.django_db(transaction=True)
def test_char_field_negative(sample_app):
    factories.ParentEntityFactory.create_batch(30, child_entities=True)

    query = urlencode(
        {
            'filter': '~(state=state_one|state=state_two)',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    for it in data['data']:
        assert (
            it['attributes']['state'] != ParentEntityState.STATE_ONE.value
            and it['attributes']['state'] != ParentEntityState.STATE_TWO.value
        )

    query = urlencode(
        {
            'filter': '~state=state_one&~(state=state_two|state=state_three)',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    for it in data['data']:
        assert (
            it['attributes']['state'] != ParentEntityState.STATE_ONE.value
            and it['attributes']['state'] != ParentEntityState.STATE_TWO.value
            and it['attributes']['state'] != ParentEntityState.STATE_THREE.value
        )


@pytest.mark.django_db(transaction=True)
def test_array_field(sample_app):
    factories.ParentEntityFactory(field=['first_field', 'second_field'])

    query = urlencode(
        {
            'filter': 'field=first_field,second_field',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert (
            'first_field' in it['attributes']['field']
            or 'second_field' in it['attributes']['field']
        )


@pytest.mark.django_db(transaction=True)
def test_many_to_many_field(sample_app):
    factories.ParentEntityFactory()

    query = urlencode(
        {
            'filter': 'child_entities__exists=false',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) == 1

    query = urlencode(
        {
            'filter': 'is_active=true&child_entities__child_is_active=true&'
            'child_entities__child_price__lt=550',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()

    for it in data['data']:
        child_entities = it['relationships']['child_entities']['data']

        assert it['attributes']['is_active'] is True
        assert ChildEntity.objects.filter(
            Q(id__in=[c['id'] for c in child_entities])
            & (Q(child_is_active=True) | Q(child_price__lt=550)),
        ).exists()


@pytest.mark.django_db(transaction=True)
def test_calc_field(sample_app):
    child = factories.ChildEntityFactory(child_is_active=True)
    parent_entity = factories.ParentEntityFactory()
    parent_entity.child_entities.add(child)

    query = urlencode(
        {
            'filter': 'has_inactive_children=false',
        }
    )

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query}')

    assert response.status_code == 200

    data = response.json()
    assert len(data['data']) > 0

    for it in data['data']:
        assert it['attributes']['has_inactive_children'] is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_str',
    [
        # an unknown field gave no condition at all
        'nonexistent=1',
        'nonexistent__in=1',
        # a calculated field that is not a filter
        'extended_entity_price=1',
        # after a relation, an unknown name gave "has related objects"
        'child_entities__in=1,2',
        'child_entities__nonexistent=1',
        'child_entities__exists__extra=true',
        # objects of a model that does not exist or is not related
        'entity.nonexistent=1',
        'entity.vehicle=1',
        '$search__extra=x',
    ],
)
def test_unknown_filter_field_returns_bad_request(sample_app, filter_str):
    factories.ParentEntityFactory()

    response = get_api_client(sample_app).get(
        '/api/v1/entity/parent_entity/', params={'filter': filter_str}
    )

    assert response.status_code == 400
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_FILTER'
    assert error['source'] == {'pointer': '/query/filter'}


def _parent_ids(sample_app, filter_str):
    response = get_api_client(sample_app).get(
        '/api/v1/entity/parent_entity/', params={'filter': filter_str}
    )
    assert response.status_code == 200, response.json()
    return {it['id'] for it in response.json()['data']}


@pytest.mark.django_db(transaction=True)
def test_relation_exists_isnull(sample_app):
    """`isnull` of a relation is the opposite of `exists` (it was "has related objects" for
    any value)."""
    child = factories.ChildEntityFactory()
    with_children = factories.ParentEntityFactory()
    with_children.child_entities.add(child)
    without_children = factories.ParentEntityFactory()

    has = {str(with_children.pk)}
    has_not = {str(without_children.pk)}
    assert _parent_ids(sample_app, 'child_entities__exists=true') == has
    assert _parent_ids(sample_app, 'child_entities__exists=false') == has_not
    assert _parent_ids(sample_app, 'child_entities__isnull=false') == has
    assert _parent_ids(sample_app, 'child_entities__isnull=true') == has_not
    # a reverse foreign key: every parent has its dependent entity (RelatedFactory)
    assert _parent_ids(sample_app, 'dependent_entities__exists=true') == has | has_not
    assert _parent_ids(sample_app, f'child_entities__child_name={child.child_name}') == has
    assert _parent_ids(sample_app, f'entity.child_entity={child.pk}') == has


@pytest.mark.django_db(transaction=True)
def test_array_field_lookups(sample_app):
    first = factories.ParentEntityFactory(field=['first_field'])
    both = factories.ParentEntityFactory(field=['first_field', 'second_field'])
    third = factories.ParentEntityFactory(field=['third_field'])

    assert _parent_ids(sample_app, 'field=first_field,second_field') == {
        str(first.pk),
        str(both.pk),
    }
    assert _parent_ids(sample_app, 'field__overlap=third_field') == {str(third.pk)}
    assert _parent_ids(sample_app, 'field__contains=first_field,second_field') == {str(both.pk)}
    assert _parent_ids(sample_app, 'field__contained_by=first_field,third_field') == {
        str(first.pk),
        str(third.pk),
    }


@pytest.mark.django_db(transaction=True)
def test_calc_field_isnull(sample_app):
    parent = factories.ParentEntityFactory()

    assert _parent_ids(sample_app, 'has_inactive_children__isnull=false') == {str(parent.pk)}
    assert _parent_ids(sample_app, 'has_inactive_children__isnull=true') == set()
