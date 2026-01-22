import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_slice(sample_app, sample_vehicle_data):
    """
    @calc_property([
        FieldJson(
            source='carrier_tasks',
            fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
            query=Q(dt_finish__isnull=False),
            slice=slice(1),
            order_by=['-dt_finish'],
        ),
    ])
    """

    response = get_api_client(sample_app).get('/api/v1/slice/entity/driver/')

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
          (SELECT JSONB_BUILD_OBJECT(('id')::text, U0."id", ('dt_start')::text, U0."dt_start", ('dt_finish')::text, U0."dt_finish", ('fact_waste_weight')::text, U0."fact_waste_weight") AS "json"
           FROM "entity_carriertask" U0
           WHERE (U0."driver_id" = ("entity_driver"."id")
                  AND U0."dt_finish" IS NOT NULL)
           ORDER BY U0."dt_finish" DESC
           LIMIT 1) AS "_carrier_tasks"
        FROM "entity_driver"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    driver = sample_vehicle_data['driver']
    tasks = [t for t in sample_vehicle_data['tasks'] if t.dt_finish is not None]
    latest = sorted(tasks, key=lambda x: x.dt_finish, reverse=True)[0]

    found = False
    for item in data['data']:
        if item['id'] != str(driver.id):
            continue
        found = True
        last_trip = item['attributes']['last_trip']
        assert last_trip['id'] == str(latest.id)
        assert last_trip['dt_start'][:23] == latest.dt_start.isoformat()[:23]
        assert last_trip['dt_finish'][:23] == latest.dt_finish.isoformat()[:23]
        assert last_trip['fact_waste_weight'] == float(latest.fact_waste_weight)
    assert found, f'Driver {driver.id} not found in response'


@pytest.mark.django_db(transaction=True)
def test_order_by(sample_app, sample_vehicle_data):
    """
    @calc_property([
        FieldJson(
            source='carrier_tasks',
            fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
            query=Q(dt_finish__isnull=False),
            order_by=['dt_start'],
        ),
    ])
    """

    response = get_api_client(sample_app).get('/api/v1/order_by/entity/driver/')

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
          (SELECT JSONB_BUILD_OBJECT(('id')::text, U0."id", ('dt_start')::text, U0."dt_start", ('dt_finish')::text, U0."dt_finish", ('fact_waste_weight')::text, U0."fact_waste_weight") AS "json"
           FROM "entity_carriertask" U0
           WHERE (U0."driver_id" = ("entity_driver"."id")
                  AND U0."dt_finish" IS NOT NULL)
           ORDER BY U0."dt_start" ASC) AS "_carrier_tasks"
        FROM "entity_driver"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    driver = sample_vehicle_data['driver']
    expected_tasks = sorted(
        [t for t in sample_vehicle_data['tasks'] if t.dt_finish is not None],
        key=lambda x: x.dt_start,
    )

    found = False
    for item in data['data']:
        if item['id'] != str(driver.id):
            continue
        found = True
        trips = item['attributes']['trips']
        assert len(trips) == len(expected_tasks)

        for task_json, task_obj in zip(trips, expected_tasks, strict=False):
            assert task_json['id'] == str(task_obj.id)
            assert task_json['dt_start'][:23] == task_obj.dt_start.isoformat()[:23]
            assert task_json['dt_finish'][:23] == task_obj.dt_finish.isoformat()[:23]
            assert task_json['fact_waste_weight'] == float(task_obj.fact_waste_weight)
    assert found, f'Driver {driver.id} not found in response'
