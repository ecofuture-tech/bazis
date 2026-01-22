import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_context(sample_app, sample_vehicle_data):
    """Test for checking context."""

    organization = sample_vehicle_data['organization']

    response = get_api_client(sample_app).get('/api/v1/context/entity/driver/')

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
       WHERE (W0."driver_id" = ("entity_driver"."id")
              AND W0."org_owner_id" = 'id_hex')) AS "_carrier_tasks"
    FROM "entity_driver"
    LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query, organization.id)
