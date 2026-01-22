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
Boolean

A calculated field can return a boolean flag indicating whether a combination of conditions is met.
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_isexists_one_relation(sample_app, dynamic_vehicle_data):
    """
    One related table.

    A calculated field for vehicles (the Vehicle model) with information about whether the vehicle
    has an active trip (the CarrierTask model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(
                'carrier_tasks',
                query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
                alias='has_active_trip',
            ),
        ])
        def has_active_trip(self, dc: DependsCalc) -> bool:
            return dc.data.has_active_trip
    """

    vehicle = dynamic_vehicle_data['vehicle']

    url = '/api/v1/is_exists_one_relation/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "dynamic_carriertask" U0
                   WHERE (U0."vehicle_id" = ("dynamic_vehicle"."id")
                          AND U0."dt_start" IS NOT NULL
                          AND NOT (U0."dt_finish" IS NOT NULL))
                   LIMIT 1) AS "has_active_trip"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'has_active_trip' in attrs
        assert attrs['has_active_trip'] is True
    assert found, f'Vehicle {vehicle.id} not found in response'

    url = f'/api/v1/is_exists_one_relation/dynamic/vehicle/{vehicle.id}'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "dynamic_carriertask" U0
                   WHERE (U0."vehicle_id" = ("dynamic_vehicle"."id")
                          AND U0."dt_start" IS NOT NULL
                          AND NOT (U0."dt_finish" IS NOT NULL))
                   LIMIT 1) AS "has_active_trip"
        FROM "dynamic_vehicle"
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'has_active_trip' in attrs
    assert attrs['has_active_trip'] is True


@pytest.mark.django_db(transaction=True)
def test_isexists_hierachy(sample_app, dynamic_vehicle_data):
    """
    Hierarchy of related tables.

    A hierarchy of calculated fields for the vehicle model (Vehicle) with information about whether the vehicle
    has an active trip (the CarrierTask model) and a driver on it (the Driver model)
    who meets certain conditions.

    .. code-block:: python

        @calc_property([
            FieldDynamic(source='carrier_tasks',
                         alias='has_active_trip_with_phone',
                         query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True) & Q(
                             has_drivers_with_phone=True)).add_nested([
                FieldDynamic(source='driver',
                             alias='has_drivers_with_phone',
                             query=Q(contact_phone__isnull=False) & ~Q(contact_phone=''))
            ])
        ])
        def has_active_trip_with_phone(self, dc: DependsCalc) -> bool:
            return dc.data.has_active_trip_with_phone
    """

    vehicle = dynamic_vehicle_data['vehicle']

    url = '/api/v1/is_exists_hierarchy/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               EXISTS
          (SELECT 1 AS "a"
           FROM "dynamic_carriertask" V0
           WHERE (V0."vehicle_id" = ("dynamic_vehicle"."id")
                  AND V0."dt_start" IS NOT NULL
                  AND V0."dt_finish" IS NULL
                  AND EXISTS
                    (SELECT 1 AS "a"
                     FROM "dynamic_driver" U0
                     WHERE (U0."id" = (V0."driver_id")
                            AND U0."contact_phone" IS NOT NULL
                            AND NOT (U0."contact_phone" = ''
                                     AND U0."contact_phone" IS NOT NULL))
                     LIMIT 1))
           LIMIT 1) AS "has_active_trip_with_phone"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'has_active_trip_with_phone' in attrs
        assert attrs['has_active_trip_with_phone'] is True
    assert found, f'Vehicle {vehicle.id} not found in response'

    url = f'/api/v1/is_exists_hierarchy/dynamic/vehicle/{str(vehicle.id)}'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "dynamic_carriertask" V0
                   WHERE (V0."vehicle_id" = ("dynamic_vehicle"."id")
                          AND V0."dt_start" IS NOT NULL
                          AND V0."dt_finish" IS NULL
                          AND EXISTS
                            (SELECT 1 AS "a"
                             FROM "dynamic_driver" U0
                             WHERE (U0."id" = (V0."driver_id")
                                    AND U0."contact_phone" IS NOT NULL
                                    AND NOT (U0."contact_phone" = ''
                                             AND U0."contact_phone" IS NOT NULL))
                             LIMIT 1))
                   LIMIT 1) AS "has_active_trip_with_phone"
        FROM "dynamic_vehicle"
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'has_active_trip_with_phone' in attrs
    assert attrs['has_active_trip_with_phone'] is True
