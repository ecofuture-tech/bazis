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
Testing FieldAggr and FieldSubAggr.
The following cases are checked:
case 1. One calculated field FieldAggr is added:
--- getting a list
--- getting an item by id
case 2. One calculated field FieldSubAggr is added:
--- getting a list
--- getting an item by id

These calculated fields allow you to obtain the same data in the end but with different queries.
In the first case a JOIN will be used, in the second case a subquery will be used.
If sorting is not explicitly specified, the resulting rows may be ordered differently,
so it is important to explicitly specify ?sort=id

Comparison of query plans:
1) FieldAggr
    Limit  (rows=20)
    └─ Aggregate  (GROUP BY entity_vehicle.id)
       └─ Nested Loop Left Join
          ├─ Index Scan using entity_vehicle_pkey on entity_vehicle
          │   → retrieves 21 rows
          └─ Index Scan on entity_carriertask using vehicle_id index
              → executed 21 times (for each vehicle)
              → returns a total of 6901 rows
2) FieldSubAggr
    Limit  (rows=20)
    └─ Index Scan using entity_vehicle_pkey on entity_vehicle
        → retrieves 20 rows
        ↓
        For each row the following is executed:
        └─ Aggregate
           └─ Bitmap Heap Scan on entity_carriertask
              └─ Bitmap Index Scan on ix_vehicle_dates
                  → filter: vehicle_id = X AND dt_start IS NOT NULL AND dt_finish IS NULL
                  → 20 repetitions (one for each row from entity_vehicle)

From the execution plans it can be seen that even with a relatively small amount of data in the
entity_vehicle and entity_carriertask tables, the number of rows processed when using JOIN reached 6901.
The reason is that in FieldAggr the filter is built into the aggregate function (SUM(...) FILTER (WHERE ...)),
and not into the WHERE clause of the query itself. That is, the JOIN is performed with all carrier_task rows
corresponding to the given vehicle_id. The filter is applied only afterwards, when everything is grouped by vehicle.id.
The plan with the subquery (FieldSubAggr) looks more optimal; it is recommended to use it.
"""

from decimal import Decimal

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_arrg_list(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldAggr(
            source='carrier_tasks__fact_waste_weight',
            func=Sum,
            alias='current_tasks_waste_weight_aggr',
            query=Q(carrier_tasks__dt_start__isnull=False) & Q(carrier_tasks__dt_finish__isnull=True),
        ),
    ])
    """

    response = get_api_client(sample_app).get('/api/v1/aggr/entity/vehicle/?sort=id')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               SUM("entity_carriertask"."fact_waste_weight") FILTER (
                                                                     WHERE ("entity_carriertask"."dt_start" IS NOT NULL
                                                                            AND "entity_carriertask"."dt_finish" IS NULL)) AS "current_tasks_waste_weight_aggr"
        FROM "entity_vehicle"
        LEFT OUTER JOIN "entity_carriertask" ON ("entity_vehicle"."id" = "entity_carriertask"."vehicle_id")
        GROUP BY "entity_vehicle"."id"
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    vehicle = sample_vehicle_data['vehicle']

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'current_tasks_waste_weight_aggr' in attrs
        assert Decimal(attrs['current_tasks_waste_weight_aggr']) == Decimal('8.0')
    assert found, f'Vehicle {vehicle.id} not found in response'


@pytest.mark.django_db(transaction=True)
def test_aggr_item(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldAggr(
            source='carrier_tasks__fact_waste_weight',
            func=Sum,
            alias='current_tasks_waste_weight_aggr',
            query=Q(carrier_tasks__dt_start__isnull=False) & Q(carrier_tasks__dt_finish__isnull=True),
        ),
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get(f'/api/v1/aggr/entity/vehicle/{str(vehicle.id)}')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               SUM("entity_carriertask"."fact_waste_weight") FILTER (
                                                                     WHERE ("entity_carriertask"."dt_start" IS NOT NULL
                                                                            AND "entity_carriertask"."dt_finish" IS NULL)) AS "current_tasks_waste_weight_aggr"
        FROM "entity_vehicle"
        LEFT OUTER JOIN "entity_carriertask" ON ("entity_vehicle"."id" = "entity_carriertask"."vehicle_id")
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        GROUP BY "entity_vehicle"."id"
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'current_tasks_waste_weight_aggr' in attrs
    assert Decimal(attrs['current_tasks_waste_weight_aggr']) == Decimal('8.0')


@pytest.mark.django_db(transaction=True)
def test_subaggr_list(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldSubAggr(
            source='carrier_tasks__fact_waste_weight',
            func='Sum',
            alias='current_tasks_waste_weight_subaggr',
            query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True),
        ),
    ])
    """

    response = get_api_client(sample_app).get('/api/v1/subaggr/entity/vehicle/?sort=id')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
        
          (SELECT Sum(U0."fact_waste_weight") AS "_resp"
           FROM "entity_carriertask" U0
           WHERE (U0."vehicle_id" = ("entity_vehicle"."id")
                  AND U0."dt_start" IS NOT NULL
                  AND U0."dt_finish" IS NULL)) AS "current_tasks_waste_weight_subaggr"
        FROM "entity_vehicle"
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    vehicle = sample_vehicle_data['vehicle']

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'current_tasks_waste_weight_subaggr' in attrs
        assert Decimal(attrs['current_tasks_waste_weight_subaggr']) == Decimal('8.0')
    assert found, f'Vehicle {vehicle.id} not found in response'


@pytest.mark.django_db(transaction=True)
def test_subaggr_item(sample_app, sample_vehicle_data):
    """
        @calc_property([
        FieldSubAggr(
            source='carrier_tasks__fact_waste_weight',
            func='Sum',
            alias='current_tasks_waste_weight_subaggr',
            query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True),
        ),
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get(f'/api/v1/subaggr/entity/vehicle/{str(vehicle.id)}')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
        
          (SELECT Sum(U0."fact_waste_weight") AS "_resp"
           FROM "entity_carriertask" U0
           WHERE (U0."vehicle_id" = ("entity_vehicle"."id")
                  AND U0."dt_start" IS NOT NULL
                  AND U0."dt_finish" IS NULL)) AS "current_tasks_waste_weight_subaggr"
        FROM "entity_vehicle"
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'current_tasks_waste_weight_subaggr' in attrs
    assert Decimal(attrs['current_tasks_waste_weight_subaggr']) == Decimal('8.0')
