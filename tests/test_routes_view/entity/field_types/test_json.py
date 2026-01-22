import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_json_list(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldJson(
            source='carrier_tasks',
            fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'driver_id'],
        ),
    ])
    """

    response = get_api_client(sample_app).get('/api/v1/json/entity/vehicle/')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               ARRAY
              (SELECT
                    JSONB_BUILD_OBJECT(('id')::text,
                    U0."id",
                    ('dt_start')::text,
                    U0."dt_start",
                    ('dt_finish')::text,
                    U0."dt_finish",
                    ('fact_waste_weight')::text,
                    U0."fact_waste_weight",
                    ('driver_id')::text,
                    U0."driver_id") AS "json"
              FROM "entity_carriertask" U0
              WHERE U0."vehicle_id" = ("entity_vehicle"."id")) AS "_carrier_tasks"
        FROM "entity_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    vehicle = sample_vehicle_data['vehicle']
    driver = sample_vehicle_data['driver']
    tasks = sample_vehicle_data['tasks']

    data = response.json()
    vehicles = data['data']
    found = False

    for v in vehicles:
        if v['id'] != str(vehicle.id):
            continue

        found = True
        attrs = v['attributes']

        assert 'carrier_task_list' in attrs
        task_list = attrs['carrier_task_list']
        assert len(task_list) == 3

        task_ids = [str(t.id) for t in tasks]
        weights = [float(t.fact_waste_weight) for t in tasks]

        for t in task_list:
            assert t['id'] in task_ids
            assert t['driver_id'] == str(driver.id)
            assert t['fact_waste_weight'] in weights

    assert found, f'Vehicle {vehicle.id} not found in response'


@pytest.mark.django_db(transaction=True)
def test_json_item(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldJson(
            source='carrier_tasks',
            fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'driver_id'],
        ),
    ])
    """

    vehicle = sample_vehicle_data['vehicle']
    driver = sample_vehicle_data['driver']
    tasks = sample_vehicle_data['tasks']

    response = get_api_client(sample_app).get(f'/api/v1/json/entity/vehicle/{str(vehicle.id)}')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               ARRAY
              (SELECT
                    JSONB_BUILD_OBJECT(('id')::text,
                    U0."id",
                    ('dt_start')::text,
                    U0."dt_start",
                    ('dt_finish')::text,
                    U0."dt_finish",
                    ('fact_waste_weight')::text,
                    U0."fact_waste_weight",
                    ('driver_id')::text,
                    U0."driver_id") AS "json"
              FROM "entity_carriertask" U0
              WHERE U0."vehicle_id" = ("entity_vehicle"."id")) AS "_carrier_tasks"
        FROM "entity_vehicle"
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'carrier_task_list' in attrs
    task_list = attrs['carrier_task_list']
    assert len(task_list) == 3

    expected_tasks = {
        str(task.id): {
            'dt_start': task.dt_start.isoformat() if task.dt_start else None,
            'dt_finish': task.dt_finish.isoformat() if task.dt_finish else None,
            'fact_waste_weight': float(task.fact_waste_weight),
            'driver_id': str(driver.id),
        }
        for task in tasks
    }

    for t in task_list:
        assert t['id'] in expected_tasks
        expected = expected_tasks[t['id']]
        assert (t['dt_start'][:23] if t['dt_start'] else None) == (
            expected['dt_start'][:23] if expected['dt_start'] else None
        )
        assert (t['dt_finish'][:23] if t['dt_finish'] else None) == (
            expected['dt_finish'][:23] if expected['dt_finish'] else None
        )
        assert t['fact_waste_weight'] == expected['fact_waste_weight']
        assert t['driver_id'] == expected['driver_id']


@pytest.mark.django_db(transaction=True)
def test_json_hierarchy(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldJson(
            source='carrier_tasks',
            fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'vehicle_id'],
            nested=[
                FieldJson(source='vehicle',
                          fields=['gnum', 'dt_created'],
                          nested=[
                              FieldJson(source='vehicle_model',
                                        fields=['engine_type'])
                          ])]
        ),
    ])
    """

    response = get_api_client(sample_app).get('/api/v1/json/entity/driver/')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_driver"."dt_created",
               "entity_driver"."dt_updated",
               "entity_driver"."id",
               "entity_driver"."first_name",
               "entity_driver"."last_name",
               "entity_driver"."contact_phone",
               "entity_driver"."org_owner_id",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'entity.division') AS "json"
           FROM "entity_division" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "entity_driver_divisions" U0
                WHERE (U0."division_id" = (V0."id")
                       AND U0."driver_id" = ("entity_driver"."id"))
                LIMIT 1)) AS "divisions__ids",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, W0."id", ('dt_start')::text, W0."dt_start", ('dt_finish')::text, W0."dt_finish", ('fact_waste_weight')::text, W0."fact_waste_weight", ('vehicle_id')::text, W0."vehicle_id", ('_vehicle')::text, ARRAY
                                       (SELECT JSONB_BUILD_OBJECT(('gnum')::text, V0."gnum", ('dt_created')::text, V0."dt_created", ('_vehicle_model')::text, ARRAY
                                                                    (SELECT JSONB_BUILD_OBJECT(('engine_type')::text, U0."engine_type") AS "json"
                                                                     FROM "entity_vehiclemodel" U0
                                                                     WHERE U0."id" = (V0."vehicle_model_id"))) AS "json"
                                        FROM "entity_vehicle" V0
                                        WHERE V0."id" = (W0."vehicle_id"))) AS "json"
           FROM "entity_carriertask" W0
           WHERE W0."driver_id" = ("entity_driver"."id")) AS "_carrier_tasks"
        FROM "entity_driver"
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    driver = sample_vehicle_data['driver']
    vehicle = sample_vehicle_data['vehicle']
    tasks = sample_vehicle_data['tasks']

    data = response.json()
    driver_data = data['data'][0]
    attrs = driver_data['attributes']

    assert driver_data['id'] == str(driver.id)
    assert attrs['first_name'] == driver.first_name
    assert attrs['last_name'] == driver.last_name
    assert attrs['contact_phone'] == driver.contact_phone

    assert driver_data['relationships']['org_owner']['data']['id'] == str(
        sample_vehicle_data['organization'].id
    )
    assert driver_data['relationships']['org_owner']['data']['type'] == 'entity.organization'
    assert driver_data['relationships']['divisions']['data'] == []

    task_list = attrs['carrier_tasks_json_hierarchy']
    assert len(task_list) == 3

    for t in task_list:
        matching = [task for task in tasks if str(task.id) == t['id']]
        assert matching, f'Task {t["id"]} not found'
        task = matching[0]

        assert (t['dt_start'][:23] if t['dt_start'] else None) == (
            task.dt_start.isoformat()[:23] if task.dt_start else None
        )
        assert (t['dt_finish'][:23] if t['dt_finish'] else None) == (
            task.dt_finish.isoformat()[:23] if task.dt_finish else None
        )
        assert t['fact_waste_weight'] == float(task.fact_waste_weight)
        assert t['vehicle_gnum'] == vehicle.gnum
