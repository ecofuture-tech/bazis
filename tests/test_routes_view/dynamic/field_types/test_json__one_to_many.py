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
One to many

A calculated field can return a list of values from related "one to many" tables.
"""


import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_json_one_relation(sample_app, dynamic_vehicle_data):
    """
    One related table.

    A calculated field for vehicles (Vehicle model) with a list of trips (CarrierTask model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'driver_id'],
            ),
        ])
        def carrier_task_list(self, dc: DependsCalc) -> list:
            return [
                {
                    'id': task.id,
                    'dt_start': task.dt_start,
                    'dt_finish': task.dt_finish,
                    'fact_waste_weight': task.fact_waste_weight,
                    'driver_id': task.driver_id,
                }
                for task in dc.data.carrier_tasks
            ]

    .. code-block:: python

        class CarrierTask(DtMixin, UuidMixin, JsonApiMixin):
            vehicle = models.ForeignKey(Vehicle, verbose_name='Vehicle', related_name='carrier_tasks', on_delete=models.CASCADE)
            driver = models.ForeignKey(Driver, verbose_name='Driver', related_name='carrier_tasks', on_delete=models.CASCADE)
            dt_start = models.DateTimeField('Start Time', null=True, blank=True)
            dt_finish = models.DateTimeField('Start Time', null=True, blank=True)
            fact_waste_weight = models.DecimalField('Fact Waste Weight, t', max_digits=15, decimal_places=3,
                                                    null=True, blank=True)
    """

    vehicle = dynamic_vehicle_data['vehicle']
    driver = dynamic_vehicle_data['driver']
    tasks = dynamic_vehicle_data['tasks']

    url = '/api/v1/json_one_relation/dynamic/vehicle/'

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
              FROM "dynamic_carriertask" U0
              WHERE U0."vehicle_id" = ("dynamic_vehicle"."id")) AS "_carrier_tasks"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    vehicles = data['data']

    found = False
    for v in vehicles:
        if v['id'] != str(vehicle.id):
            continue
        found = True
        tasks_list = v['attributes']['carrier_task_list']
        assert len(tasks_list) == 3
        for t in tasks_list:
            assert t['id'] in [str(tasks[0].id), str(tasks[1].id), str(tasks[2].id)]
            assert t['fact_waste_weight'] in [3.5, 4.5]
            assert t['driver_id'] == str(driver.id)
    assert found, 'Vehicle not found in the list'

    url = f'/api/v1/json_one_relation/dynamic/vehicle/{str(vehicle.id)}'

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
              FROM "dynamic_carriertask" U0
              WHERE U0."vehicle_id" = ("dynamic_vehicle"."id")) AS "_carrier_tasks"
        FROM "dynamic_vehicle"
        WHERE "dynamic_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "dynamic_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'carrier_task_list' in attrs
    assert len(attrs['carrier_task_list']) == 3
    for task in attrs['carrier_task_list']:
        assert task['id'] in [str(tasks[0].id), str(tasks[1].id), str(tasks[2].id)]
        assert task['fact_waste_weight'] in [3.5, 4.5]
        assert task['driver_id'] == str(driver.id)

    task_ids = [str(t.id) for t in tasks]
    weights = [float(t.fact_waste_weight) for t in tasks]

    returned = attrs['carrier_task_list']
    assert {t['id'] for t in returned} == set(task_ids)
    assert all(float(t['fact_waste_weight']) in weights for t in returned)


@pytest.mark.django_db(transaction=True)
def test_json_hierarchy(sample_app, dynamic_vehicle_data):
    """
    Hierarchy of related tables.

    A calculated field for a vehicle (Vehicle model) with a list of its trips (CarrierTask model),
    enriched with data about the driver (Driver model) and the organization (Organization model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(source="carrier_tasks",
                         fields=["id", "dt_start", "dt_finish", "fact_waste_weight"])
            .add_nested([
                FieldDynamic(source="driver",
                             fields=["last_name"])
                .add_nested([
                    FieldDynamic(source="org_owner",
                                 fields=["name"])
                ])
            ])
        ])
        def carrier_tasks_json_hierarchy(self, dc: DependsCalc) -> list:
            return [
                {
                    'id': task.id,
                    'dt_start': task.dt_start,
                    'dt_finish': task.dt_finish,
                    'fact_waste_weight': task.fact_waste_weight,
                    'last_name': task.driver[0].last_name,
                    'organization': task.driver[0].org_owner[0].name,
                }
                for task in dc.data.carrier_tasks
            ]
    """

    url = '/api/v1/json_hierarchy/dynamic/vehicle/'

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
                                       (SELECT JSONB_BUILD_OBJECT(('last_name')::text, V0."last_name", ('_org_owner')::text, ARRAY
                                                                    (SELECT JSONB_BUILD_OBJECT(('name')::text, U0."name") AS "json"
                                                                     FROM "dynamic_organization" U0
                                                                     WHERE U0."id" = (V0."org_owner_id"))) AS "json"
                                        FROM "dynamic_driver" V0
                                        WHERE V0."id" = (W0."driver_id"))) AS "json"
           FROM "dynamic_carriertask" W0
           WHERE W0."vehicle_id" = ("dynamic_vehicle"."id")) AS "_carrier_tasks"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)
    data = response.json()

    vehicle_data = data['data'][0]

    assert vehicle_data['id'] == str(dynamic_vehicle_data['vehicle'].id)
    assert vehicle_data['attributes']['gnum'] == dynamic_vehicle_data['vehicle'].gnum

    carrier_tasks = vehicle_data['attributes']['carrier_tasks_json_hierarchy']
    assert len(carrier_tasks) == 3, 'Expected 3 trips'

    for i, task in enumerate(carrier_tasks):
        assert task['id'] == str(dynamic_vehicle_data['tasks'][i].id)
        assert task['fact_waste_weight'] == float(
            dynamic_vehicle_data['tasks'][i].fact_waste_weight
        )
        assert task['last_name'] == dynamic_vehicle_data['driver'].last_name
        assert task['organization'] == dynamic_vehicle_data['organization'].name


@pytest.mark.django_db(transaction=True)
def test_json_order_by(sample_app, dynamic_vehicle_data):
    """
    List sorting.

    A calculated field for a vehicle (Driver model) with a list of its active trips (CarrierTask model) and
    sorting by start date.

    .. code-block:: python

        @calc_property([
            FieldDynamic(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True),
                order_by=['dt_start'],
            ),
        ])
        def active_trips(self, dc: DependsCalc) -> list:
            return [
                {
                    'id': trips.id,
                    'dt_start': trips.dt_start,
                    'dt_finish': trips.dt_finish,
                    'fact_waste_weight': trips.fact_waste_weight,
                }
                for trips in dc.data.carrier_tasks
            ]
    """

    url = '/api/v1/json_order_by/dynamic/vehicle/'

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
          (SELECT JSONB_BUILD_OBJECT(('id')::text, U0."id", ('dt_start')::text, U0."dt_start", ('dt_finish')::text, U0."dt_finish", ('fact_waste_weight')::text, U0."fact_waste_weight") AS "json"
           FROM "dynamic_carriertask" U0
           WHERE (U0."vehicle_id" = ("dynamic_vehicle"."id")
                  AND U0."dt_start" IS NOT NULL
                  AND U0."dt_finish" IS NULL)
           ORDER BY U0."dt_start" ASC) AS "_carrier_tasks"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    vehicle = dynamic_vehicle_data['vehicle']
    expected_tasks = sorted(
        [
            t
            for t in dynamic_vehicle_data['tasks']
            if t.dt_start is not None and t.dt_finish is None
        ],
        key=lambda x: x.dt_start,
    )

    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        trips = item['attributes']['active_trips']
        assert len(trips) == len(expected_tasks)

        for task_json, task_obj in zip(trips, expected_tasks, strict=False):
            assert task_json['id'] == str(task_obj.id)
            assert (task_json['dt_start'][:23] if task_json['dt_start'] else None) == (
                task_obj.dt_start.isoformat()[:23] if task_obj.dt_start else None
            )
            assert (task_json['dt_finish'][:23] if task_json['dt_finish'] else None) == (
                task_obj.dt_finish.isoformat()[:23] if task_obj.dt_finish else None
            )
            assert task_json['fact_waste_weight'] == float(task_obj.fact_waste_weight)
    assert found, f'Vehicle {vehicle.id} not found in response'


@pytest.mark.django_db(transaction=True)
def test_json_slice(sample_app, dynamic_vehicle_data):
    """
    List slice.

    A calculated field for a vehicle (Vehicle model) with information about the last completed trip
    (CarrierTask model).

    .. code-block:: python

        @calc_property([
            FieldDynamic(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                query=Q(dt_finish__isnull=False),
                slice=slice(1),
                order_by=['-dt_finish'],
            ),
        ])
        def last_trip(self, dc: DependsCalc) -> dict:
            return {
                'id': dc.data.carrier_tasks[0].id,
                'dt_start': dc.data.carrier_tasks[0].dt_start,
                'dt_finish': dc.data.carrier_tasks[0].dt_finish,
                'fact_waste_weight': dc.data.carrier_tasks[0].fact_waste_weight,
            } if dc.data.carrier_tasks else dict()
    """

    url = '/api/v1/json_slice/dynamic/vehicle/'

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
          (SELECT JSONB_BUILD_OBJECT(('id')::text, U0."id", ('dt_start')::text, U0."dt_start", ('dt_finish')::text, U0."dt_finish", ('fact_waste_weight')::text, U0."fact_waste_weight") AS "json"
           FROM "dynamic_carriertask" U0
           WHERE (U0."vehicle_id" = ("dynamic_vehicle"."id")
                  AND U0."dt_finish" IS NOT NULL)
           ORDER BY U0."dt_finish" DESC
           LIMIT 1) AS "_carrier_tasks"
        FROM "dynamic_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query)

    data = response.json()
    driver = dynamic_vehicle_data['driver']
    tasks = [t for t in dynamic_vehicle_data['tasks'] if t.dt_finish is not None]
    sorted_list = sorted(tasks, key=lambda x: x.dt_finish, reverse=True)
    if sorted_list:
        latest = sorted_list[0]
        for item in data['data']:
            if item['id'] != str(driver.id):
                continue
            last_trip = item['attributes']['last_trip']
            assert last_trip['id'] == str(latest.id)
            assert last_trip['dt_start'][:23] == latest.dt_start.isoformat()[:23]
            assert last_trip['dt_finish'][:23] == latest.dt_finish.isoformat()[:23]
            assert last_trip['fact_waste_weight'] == float(latest.fact_waste_weight)
