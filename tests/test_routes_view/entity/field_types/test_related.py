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

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_related_one_relation_multiple_fields(sample_app, sample_vehicle_data):
    """
    @calc_property([FieldRelated('vehicle_model')])
    def vehicle_model_info(self) -> dict:
        return {
            'model': self.vehicle_model.model,
            'capacity': self.vehicle_model.capacity,
        }
    """

    vehicle = sample_vehicle_data['vehicle']
    vehicle_model = sample_vehicle_data['vehicle_model']

    response = get_api_client(sample_app).get(
        '/api/v1/related_one_relation_multiple_fields/entity/vehicle/'
    )
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
               "entity_vehiclemodel"."capacity"
        FROM "entity_vehicle"
        INNER JOIN "entity_vehiclemodel" ON ("entity_vehicle"."vehicle_model_id" = "entity_vehiclemodel"."id")
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    assert 'data' in data
    assert isinstance(data['data'], list)

    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue

        found = True
        attrs = item['attributes']

        assert 'vehicle_model_info' in attrs
        assert attrs['vehicle_model_info'] == {
            'model': vehicle_model.model,
            'capacity': str(vehicle_model.capacity),
        }

    assert found, f'Vehicle with ID {vehicle.id} not found in response.'


@pytest.mark.django_db(transaction=True)
def test_related_hierarchy_list(sample_app, sample_vehicle_data):
    """
    @calc_property([FieldRelated('vehicle_model')])
    @calc_property(
        [FieldRelated('vehicle_model', alias='_vehicle_model',
            nested=[FieldRelated('brand', alias='_brand')])]
    )
    @calc_property([FieldRelated('vehicle_model__brand'), FieldRelated('country')])
    """

    vehicle = sample_vehicle_data['vehicle']
    vehicle_model = sample_vehicle_data['vehicle_model']
    vehicle_brand = sample_vehicle_data['vehicle_brand']
    vehicle_country = sample_vehicle_data['vehicle_country']

    response = get_api_client(sample_app).get('/api/v1/related/entity/vehicle/')
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
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    assert 'data' in data
    assert isinstance(data['data'], list)

    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue

        found = True
        attrs = item['attributes']

        # FieldRelated - check vehicle_capacity 1
        assert 'vehicle_capacity_1' in attrs
        assert Decimal(attrs['vehicle_capacity_1']) == vehicle_model.capacity

        # FieldRelated - check vehicle_capacity 2
        assert 'vehicle_capacity_2' in attrs
        assert Decimal(attrs['vehicle_capacity_2']) == vehicle_model.capacity

        # FieldRelated - check vehicle_capacity 3
        assert 'vehicle_capacity_3' in attrs
        assert Decimal(attrs['vehicle_capacity_3']) == vehicle_model.capacity

        # FieldRelated - check brand multiple fields
        assert 'brand_info' in attrs
        assert attrs['brand_info'] == {
            'id': str(vehicle_brand.id),
            'name': vehicle_brand.name,
        }

        # FieldRelated - check brand and country
        assert 'brand_and_country' in attrs
        assert attrs['brand_and_country'] == {
            'brand': vehicle_brand.name,
            'country': vehicle_country.name,
        }

    assert found, f'Vehicle with ID {vehicle.id} not found in response.'


@pytest.mark.django_db(transaction=True)
def test_related_hierarchy_item(sample_app, sample_vehicle_data):
    """
    @calc_property([FieldRelated('vehicle_model')])
    @calc_property(
        [FieldRelated('vehicle_model', alias='_vehicle_model',
            nested=[FieldRelated('brand', alias='_brand')])]
    )
    @calc_property([FieldRelated('vehicle_model__brand'), FieldRelated('country')])
    """

    vehicle = sample_vehicle_data['vehicle']
    vehicle_model = sample_vehicle_data['vehicle_model']
    vehicle_brand = sample_vehicle_data['vehicle_brand']
    vehicle_country = sample_vehicle_data['vehicle_country']

    response = get_api_client(sample_app).get(f'/api/v1/related/entity/vehicle/{str(vehicle.id)}')

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
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""
    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    # FieldRelated - check vehicle_capacity 1
    assert 'vehicle_capacity_1' in attrs
    assert Decimal(attrs['vehicle_capacity_1']) == vehicle_model.capacity

    # FieldRelated - check vehicle_capacity 2
    assert 'vehicle_capacity_2' in attrs
    assert Decimal(attrs['vehicle_capacity_2']) == vehicle_model.capacity

    # FieldRelated - check vehicle_capacity 3
    assert 'vehicle_capacity_3' in attrs
    assert Decimal(attrs['vehicle_capacity_3']) == vehicle_model.capacity

    # FieldRelated - check brand multiple fields
    assert 'brand_info' in attrs
    assert attrs['brand_info'] == {
        'id': str(vehicle_brand.id),
        'name': vehicle_brand.name,
    }

    # FieldRelated - check brand and country multiple fields from several related tables
    assert 'brand_and_country' in attrs
    assert attrs['brand_and_country'] == {
        'brand': vehicle_brand.name,
        'country': vehicle_country.name,
    }
