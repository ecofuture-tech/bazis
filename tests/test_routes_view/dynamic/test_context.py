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
Context

Using context and query, you can configure automatic filtering of data obtained from related tables.
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_context(sample_app, dynamic_vehicle_data):
    """
    Hierarchy of related tables.

    A calculated field for a vehicle (Vehicle model) with "_organization" specified in context and
    org_owner=F('_organization') in query for data from the related table with trips (CarrierTasks model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(source='carrier_tasks',
                         fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'vehicle_id'],
                         context=['_organization'],
                         query=Q(org_owner=F('_organization')))
            .add_nested([
                FieldDynamic(
                    source='driver',
                    fields=['contact_phone'])
                .add_nested([
                    FieldDynamic(source="org_owner",
                                 fields=["name"])
                ])
            ])
        ])
        def carrier_tasks_context(self, dc: DependsCalc) -> list:
            return [
                {
                    'id': task.id,
                    'dt_start': task.dt_start,
                    'dt_finish': task.dt_finish,
                    'fact_waste_weight': task.fact_waste_weight,
                    'driver_phone': task.driver[0].contact_phone,
                    'organization': task.driver[0].org_owner[0].name,
                }
                for task in dc.data.carrier_tasks
            ]
    """

    organization = dynamic_vehicle_data['organization']

    url = '/api/v1/context/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, W0."id", ('dt_start')::text, W0."dt_start", ('dt_finish')::text, W0."dt_finish", ('fact_waste_weight')::text, W0."fact_waste_weight", ('_driver')::text, ARRAY
                                       (SELECT JSONB_BUILD_OBJECT(('contact_phone')::text, V0."contact_phone", ('_org_owner')::text, ARRAY
                                                                    (SELECT JSONB_BUILD_OBJECT(('name')::text, U0."name") AS "json"
                                                                     FROM "dynamic_organization" U0
                                                                     WHERE U0."id" = (V0."org_owner_id"))) AS "json"
                                        FROM "dynamic_driver" V0
                                        WHERE V0."id" = (W0."driver_id"))) AS "json"
           FROM "dynamic_carriertask" W0
           WHERE (W0."vehicle_id" = ("dynamic_vehicle"."id")
                  AND W0."org_owner_id" = '3fa85f64-5717-4562-b3fc-2c963f66afa6')) AS "_carrier_tasks"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query, organization.id)
