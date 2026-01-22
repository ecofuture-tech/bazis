"""
The Driver model has the divisions attribute
    divisions = models.ManyToManyField(
        Division,
        related_name='drivers',
        blank=True,
    )

Django creates under the hood an intermediate table entity_driver_divisions
for the Many-to-Many relationship between the Driver and Division models.

The relation_field method of the custom CalcQuerySet enriches the query with m2m relation data using FieldJson for this
    FieldJson(
        source=field.name,
        alias=f'{field.name}__ids',
        fields=['id', '_jsonapi_type'],
        filter_fn=lambda _qs, _ctx: _qs.model.set_jsonapi_type(_qs, _ctx),
    )

All this makes it possible to fulfill the JSON:API requirements (a specification for structuring JSON API responses) in terms of adding
for the client to the response a list of ids from the related table while minimizing the load on the database
  "relationships": {
    "divisions": {
      "data": []
    }

The current test checks the operation of this query-enrichment mechanism
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_m2m_list(sample_app, sample_vehicle_data):
    """Test for list"""

    response = get_api_client(sample_app).get('/api/v1/entity/driver/')

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
                LIMIT 1)) AS "divisions__ids"
        FROM "entity_driver"
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)


@pytest.mark.django_db(transaction=True)
def test_m2m_item(sample_app, sample_vehicle_data):
    """Test for checking relation fields, m2m."""

    driver = sample_vehicle_data['driver']

    response = get_api_client(sample_app).get(f'/api/v1/entity/driver/{str(driver.id)}')

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
                LIMIT 1)) AS "divisions__ids"
        FROM "entity_driver"
        WHERE "entity_driver"."id" = 'id_hex'::UUID
        ORDER BY "entity_driver"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, driver.id.hex)
