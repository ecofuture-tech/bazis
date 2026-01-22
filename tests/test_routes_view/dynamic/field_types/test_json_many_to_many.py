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

"""
Many to many

A calculated field can return a list of values from related "many to many" tables.
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_many_to_many_background(sample_app, dynamic_vehicle_data):
    """
    Creating calculated fields in the background.

    If a model has a Many-to-Many attribute, for example the divisions attribute on the Driver model,

    .. code-block:: python

        divisions = models.ManyToManyField(
            Division,
            related_name='drivers',
            blank=True,
        )

    Then Django creates an intermediate table to store the relations between the current model and the model
    specified in the attribute with the Many-to-Many relation flag.
    For example, for a Many-to-Many relation between the Driver and Division models,
    the dynamic_driver_divisions table is created.

    The relation_field method of the custom CalcQuerySet enriches the query with data about Many-to-Many relations
    using the FieldJson calculated field for this purpose.

    .. code-block:: python

        FieldJson(
            source=field.name,
            alias=f'{field.name}__ids',
            fields=['id', '_jsonapi_type'],
            filter_fn=lambda _qs, _ctx: _qs.model.set_jsonapi_type(_qs, _ctx),
        )

    All this makes it possible to meet the JSON:API requirements (a specification for structuring API JSON responses)
    in terms of adding to the client response a list of ids from the related table while minimizing the load on the database.

    .. code-block:: python

          "relationships": {
            "divisions": {
              "data": []
            }
    """

    url = '/api/v1/dynamic/driver/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_driver"."dt_created",
               "dynamic_driver"."dt_updated",
               "dynamic_driver"."id",
               "dynamic_driver"."first_name",
               "dynamic_driver"."last_name",
               "dynamic_driver"."contact_phone",
               "dynamic_driver"."org_owner_id",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'dynamic.division') AS "json"
           FROM "dynamic_division" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "dynamic_driver_divisions" U0
                WHERE (U0."division_id" = (V0."id")
                       AND U0."driver_id" = ("dynamic_driver"."id"))
                LIMIT 1)) AS "divisions__ids"
        FROM "dynamic_driver"
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)

    driver = dynamic_vehicle_data['driver']

    url = f'/api/v1/dynamic/driver/{str(driver.id)}'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_driver"."dt_created",
               "dynamic_driver"."dt_updated",
               "dynamic_driver"."id",
               "dynamic_driver"."first_name",
               "dynamic_driver"."last_name",
               "dynamic_driver"."contact_phone",
               "dynamic_driver"."org_owner_id",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'dynamic.division') AS "json"
           FROM "dynamic_division" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "dynamic_driver_divisions" U0
                WHERE (U0."division_id" = (V0."id")
                       AND U0."driver_id" = ("dynamic_driver"."id"))
                LIMIT 1)) AS "divisions__ids"
        FROM "dynamic_driver"
        WHERE "dynamic_driver"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_driver"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, driver.id.hex)


@pytest.mark.django_db(transaction=True)
def test_many_to_many(sample_app, dynamic_vehicle_data):
    """
    Creating calculated fields for Many to many explicitly.

    A calculated field for a driver (Driver model) with a list of divisions where they worked (Division model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(
                source='divisions',
                fields=['id', 'name', 'dt_created'],
            ),
        ])
        def divisions_hired_info(self, dc: DependsCalc) -> list:
            return [
                {
                    'id': division.id,
                    'division': division.name,
                    'hired_date': division.dt_created,
                }
                for division in dc.data.divisions
            ]
    """

    url = '/api/v1/json_many_to_many/dynamic/driver/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_driver"."dt_created",
               "dynamic_driver"."dt_updated",
               "dynamic_driver"."id",
               "dynamic_driver"."first_name",
               "dynamic_driver"."last_name",
               "dynamic_driver"."contact_phone",
               "dynamic_driver"."org_owner_id",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'dynamic.division') AS "json"
           FROM "dynamic_division" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "dynamic_driver_divisions" U0
                WHERE (U0."division_id" = (V0."id")
                       AND U0."driver_id" = ("dynamic_driver"."id"))
                LIMIT 1)) AS "divisions__ids",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('name')::text, V0."name", ('dt_created')::text, V0."dt_created") AS "json"
           FROM "dynamic_division" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "dynamic_driver_divisions" U0
                WHERE (U0."division_id" = (V0."id")
                       AND U0."driver_id" = ("dynamic_driver"."id"))
                LIMIT 1)) AS "_divisions"
        FROM "dynamic_driver"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)
