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
    # assert len(data['data']) == 1

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

    for it in data['data']:
        assert (
            Decimal(it['attributes']['price']) == Decimal(500)
            and it['attributes']['is_active'] is True
        ) or Decimal(it['attributes']['price']) == Decimal(600)


@pytest.mark.django_db(transaction=True)
def test_char_field_icontain_iexact(sample_app):
    factories.ParentEntityFactory.create_batch(10, name='Apple')
    factories.ParentEntityFactory.create_batch(10, name='Banana')

    query_icontains = urlencode({'filter': 'name__icontains=app'})
    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query_icontains}')
    assert response.status_code == 200
    assert all('app' in it['attributes']['name'].lower() for it in response.json()['data'])

    query_iexact = urlencode({'filter': 'name__iexact=Apple'})
    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/?{query_iexact}')
    assert response.status_code == 200
    assert all(it['attributes']['name'] == 'Apple' for it in response.json()['data'])


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
