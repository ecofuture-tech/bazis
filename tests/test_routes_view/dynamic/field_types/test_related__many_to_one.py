"""
Many to one

A calculated field can return values from related "many to one" tables.
"""

from decimal import Decimal

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_related_one_relation_one_field(sample_app, dynamic_vehicle_data):
    """
    One related table. Single value.

    A calculated field for a vehicle (Vehicle model) with information about the payload capacity of the corresponding
    model (VehicleModel model).

    .. code-block:: python

        @calc_property([FieldDynamic('vehicle_model')])
        def vehicle_capacity(self, dc: DependsCalc) -> Decimal:
            return dc.data.vehicle_model.capacity
    """

    vehicle = dynamic_vehicle_data['vehicle']
    vehicle_model = dynamic_vehicle_data['vehicle_model']

    url = '/api/v1/related_one_relation_one_field/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehiclemodel"."dt_created",
               "dynamic_vehiclemodel"."dt_updated",
               "dynamic_vehiclemodel"."id",
               "dynamic_vehiclemodel"."brand_id",
               "dynamic_vehiclemodel"."model",
               "dynamic_vehiclemodel"."engine_type",
               "dynamic_vehiclemodel"."capacity"
        FROM "dynamic_vehicle"
        INNER JOIN "dynamic_vehiclemodel" ON ("dynamic_vehicle"."vehicle_model_id" = "dynamic_vehiclemodel"."id")
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    assert 'data' in data
    assert isinstance(data['data'], list)
    found = False

    for item in data['data']:
        attrs = item['attributes']
        if item['id'] == str(vehicle.id):
            found = True
            assert 'vehicle_capacity' in attrs
            assert Decimal(attrs['vehicle_capacity']) == vehicle_model.capacity

    assert found, f'Vehicle with ID {vehicle.id} not found in response.'

    url = f'/api/v1/related_one_relation_one_field/dynamic/vehicle/{str(vehicle.id)}'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehiclemodel"."dt_created",
               "dynamic_vehiclemodel"."dt_updated",
               "dynamic_vehiclemodel"."id",
               "dynamic_vehiclemodel"."brand_id",
               "dynamic_vehiclemodel"."model",
               "dynamic_vehiclemodel"."engine_type",
               "dynamic_vehiclemodel"."capacity"
        FROM "dynamic_vehicle"
        INNER JOIN "dynamic_vehiclemodel" ON ("dynamic_vehicle"."vehicle_model_id" = "dynamic_vehiclemodel"."id")
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""
    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'vehicle_capacity' in attrs
    assert Decimal(attrs['vehicle_capacity']) == vehicle_model.capacity


@pytest.mark.django_db(transaction=True)
def test_related_one_relation_multiple_fields(sample_app, dynamic_vehicle_data):
    """
    One related table. Multiple values.

    A calculated field for a vehicle (Vehicle model) with information about the model name and its payload capacity
    (VehicleModel model).

    .. code-block:: python

        @calc_property([FieldDynamic('vehicle_model')])
        def vehicle_model_info(self, dc: DependsCalc) -> dict:
            return {
                'model': dc.data.vehicle_model.model,
                'capacity': dc.data.vehicle_model.capacity,
            }
    """

    vehicle = dynamic_vehicle_data['vehicle']
    vehicle_model = dynamic_vehicle_data['vehicle_model']

    url = '/api/v1/related_one_relation_multiple_fields/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehiclemodel"."dt_created",
               "dynamic_vehiclemodel"."dt_updated",
               "dynamic_vehiclemodel"."id",
               "dynamic_vehiclemodel"."brand_id",
               "dynamic_vehiclemodel"."model",
               "dynamic_vehiclemodel"."engine_type",
               "dynamic_vehiclemodel"."capacity"
        FROM "dynamic_vehicle"
        INNER JOIN "dynamic_vehiclemodel" ON ("dynamic_vehicle"."vehicle_model_id" = "dynamic_vehiclemodel"."id")
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    assert 'data' in data
    assert isinstance(data['data'], list)
    found = False

    for item in data['data']:
        attrs = item['attributes']
        if item['id'] == str(vehicle.id):
            found = True

            assert 'vehicle_model_info' in attrs
            assert attrs['vehicle_model_info'] == {
                'model': vehicle_model.model,
                'capacity': str(vehicle_model.capacity),
            }

    assert found, f'Vehicle with ID {vehicle.id} not found in response.'

    url = f'/api/v1/related_one_relation_multiple_fields/dynamic/vehicle/{str(vehicle.id)}'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehiclemodel"."dt_created",
               "dynamic_vehiclemodel"."dt_updated",
               "dynamic_vehiclemodel"."id",
               "dynamic_vehiclemodel"."brand_id",
               "dynamic_vehiclemodel"."model",
               "dynamic_vehiclemodel"."engine_type",
               "dynamic_vehiclemodel"."capacity"
        FROM "dynamic_vehicle"
        INNER JOIN "dynamic_vehiclemodel" ON ("dynamic_vehicle"."vehicle_model_id" = "dynamic_vehiclemodel"."id")
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""
    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'vehicle_model_info' in attrs
    assert attrs['vehicle_model_info'] == {
        'model': vehicle_model.model,
        'capacity': str(vehicle_model.capacity),
    }


@pytest.mark.django_db(transaction=True)
def test_related_hierarchy(sample_app, dynamic_vehicle_data):
    """
    Hierarchy of related tables.

    A calculated field for a vehicle (Vehicle model) with information about the brand (Brand model) of the
    corresponding model (VehicleModel model).

    .. code-block:: python

        @calc_property([
            FieldDynamic('vehicle_model').add_nested([
                FieldDynamic('brand')
            ])
        ])
        def brand_info(self, dc: DependsCalc) -> dict:
            return {
                'id': dc.data.vehicle_model.brand.id,
                'name': dc.data.vehicle_model.brand.name,
            }
    """

    vehicle = dynamic_vehicle_data['vehicle']
    vehicle_brand = dynamic_vehicle_data['vehicle_brand']

    url = '/api/v1/related_hierarchy_one_branch/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehiclemodel"."dt_created",
               "dynamic_vehiclemodel"."dt_updated",
               "dynamic_vehiclemodel"."id",
               "dynamic_vehiclemodel"."brand_id",
               "dynamic_vehiclemodel"."model",
               "dynamic_vehiclemodel"."engine_type",
               "dynamic_vehiclemodel"."capacity",
               "dynamic_vehiclebrand"."dt_created",
               "dynamic_vehiclebrand"."dt_updated",
               "dynamic_vehiclebrand"."id",
               "dynamic_vehiclebrand"."name"
        FROM "dynamic_vehicle"
        INNER JOIN "dynamic_vehiclemodel" ON ("dynamic_vehicle"."vehicle_model_id" = "dynamic_vehiclemodel"."id")
        INNER JOIN "dynamic_vehiclebrand" ON ("dynamic_vehiclemodel"."brand_id" = "dynamic_vehiclebrand"."id")
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    assert 'data' in data
    assert isinstance(data['data'], list)
    found = False

    for item in data['data']:
        attrs = item['attributes']
        if item['id'] == str(vehicle.id):
            found = True

            assert 'brand_info' in attrs
            assert attrs['brand_info'] == {
                'id': str(vehicle_brand.id),
                'name': vehicle_brand.name,
            }

    assert found, f'Vehicle with ID {vehicle.id} not found in response.'

    url = f'/api/v1/related_hierarchy_one_branch/dynamic/vehicle/{str(vehicle.id)}'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehiclemodel"."dt_created",
               "dynamic_vehiclemodel"."dt_updated",
               "dynamic_vehiclemodel"."id",
               "dynamic_vehiclemodel"."brand_id",
               "dynamic_vehiclemodel"."model",
               "dynamic_vehiclemodel"."engine_type",
               "dynamic_vehiclemodel"."capacity",
               "dynamic_vehiclebrand"."dt_created",
               "dynamic_vehiclebrand"."dt_updated",
               "dynamic_vehiclebrand"."id",
               "dynamic_vehiclebrand"."name"
        FROM "dynamic_vehicle"
        INNER JOIN "dynamic_vehiclemodel" ON ("dynamic_vehicle"."vehicle_model_id" = "dynamic_vehiclemodel"."id")
        INNER JOIN "dynamic_vehiclebrand" ON ("dynamic_vehiclemodel"."brand_id" = "dynamic_vehiclebrand"."id")
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""
    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'brand_info' in attrs
    assert attrs['brand_info'] == {
        'id': str(vehicle_brand.id),
        'name': vehicle_brand.name,
    }
