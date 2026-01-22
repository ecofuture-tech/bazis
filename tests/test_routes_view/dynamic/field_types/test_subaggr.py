"""
Aggregation

A calculated field can return aggregations from related tables.
"""

from decimal import Decimal

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_subaggr_one_field(sample_app, dynamic_vehicle_data):
    """
    One related table.

    A calculated field for a vehicle (Vehicle model) that sums the weight of all transported cargo (CarrierTask model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(
                source='carrier_tasks__fact_waste_weight',
                func='Sum',
                alias='finished_tasks_waste_weight',
                query=Q(dt_finish__isnull=False),
            ),
        ])
        def finished_tasks_waste_weight(self, dc: DependsCalc) -> Decimal | None:
            return dc.data.finished_tasks_waste_weight
    """

    url = '/api/v1/subaggr/dynamic/vehicle/?sort=id'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
        
          (SELECT Sum(U0."fact_waste_weight") AS "_resp"
           FROM "dynamic_carriertask" U0
           WHERE (U0."vehicle_id" = ("dynamic_vehicle"."id")
                  AND U0."dt_finish" IS NOT NULL)) AS "finished_tasks_waste_weight"
        FROM "dynamic_vehicle"
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    vehicle = dynamic_vehicle_data['vehicle']

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'finished_tasks_waste_weight' in attrs
        assert Decimal(attrs['finished_tasks_waste_weight']) == Decimal('4.5')
    assert found, f'Vehicle {vehicle.id} not found in response'

    url = f'/api/v1/subaggr/dynamic/vehicle/{str(vehicle.id)}'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
        
          (SELECT Sum(U0."fact_waste_weight") AS "_resp"
           FROM "dynamic_carriertask" U0
           WHERE (U0."vehicle_id" = ("dynamic_vehicle"."id")
                  AND U0."dt_finish" IS NOT NULL)) AS "finished_tasks_waste_weight"
        FROM "dynamic_vehicle"
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'finished_tasks_waste_weight' in attrs
    assert Decimal(attrs['finished_tasks_waste_weight']) == Decimal('4.5')
