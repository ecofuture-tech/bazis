"""
Testing IsExists.
The following cases are checked:
case 1. One calculated IsExists field is added:
--- getting an item by id
--- getting a list
case 2. One calculated IsExists field is added with conditions on the fields of related tables specified in query via __:
--- getting an item by id
--- getting a list
case 3. An IsExists hierarchy is added with conditions on the fields of related tables specified in a lower‑level IsExists:
--- getting an item by id
--- getting a list

Cases 2 and 3 return the same result while forming different queries:
    case 2 - EXISTS with JOIN inside
    case 3 - EXISTS with nested EXISTS (subquery in a subquery)

Despite this, the PostgreSQL planner builds the same execution plan for the query.
Limit (rows=20 loops=1)
└─  Seq Scan on entity_vehicle as entity_vehicle (rows=20 loops=1)
    (sequential scan of rows of the entity_vehicle table with a limit of 20)
   └─ Gather (rows=447573 loops=1)
      (parallelization of the execution of the following subquery)
      └─ Hash Inner Join (rows=149191 loops=3)
         Hash Cond: (v0.driver_id = u0.id)
         ├─ Seq Scan on entity_carriertask as v0 (rows=149191 loops=3)
         │  (full scan of the entity_carriertask table with filters)
         │  Filter: ((dt_start IS NOT NULL) AND (dt_finish IS NULL))
         └─ Hash (rows=13087 loops=3)
            Buckets: 16384 Batches: 1 Memory Usage: 742 kB
             └─ Seq Scan on entity_driver (full scan of the entity_driver table with filters)
                 Filter: ((contact_phone IS NOT NULL) AND (((contact_phone)::text <> ''::text) OR (contact_phone IS NULL)))
Since the final query plan is the same, it is recommended to use
an IsExists hierarchy (case 3) to describe calculated IsExists fields, because it looks more readable than using "__" (case 2).

The query plan shown above also highlights that it is important not to forget about indexes.
The sequential Seq Scan over 149191 rows of entity_carriertask requires optimization.
Since the conditional cardinality of the combination of vehicle, dt_start and dt_finish is quite high, we add an index.
class CarrierTask(DtMixin, UuidMixin, JsonApiMixin):
    ...
    class Meta:
        ...
        indexes = [
            models.Index(fields=['vehicle', 'dt_start', 'dt_finish'], name='ix_vehicle_dates'),
        ]
Do not forget to warm up statistics with ANALYZE entity_carriertask;
New query plan.
Limit (rows=20 loops=1)
└─ Seq Scan on entity_vehicle (rows=20 loops=1)
   └─ Nested Loop Inner Join (rows=1 loops=20)
      ├─ Index Scan using ix_vehicle_dates on entity_carriertask u0 (rows=1 loops=20)
      │ Index Cond: (vehicle_id = entity_vehicle.id)
      │ Filter: (dt_start IS NOT NULL AND dt_finish IS NULL)
      └─ Index Scan using entity_driver_pkey on entity_driver u2 (rows=1 loops=19)
          Index Cond: (id = u0.driver_id)
          Filter: (contact_phone IS NOT NULL AND contact_phone <> '')
Since the new index provides high selectivity, the Seq Scan was successfully replaced with an Index Scan.
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_isexists_one_field_item(sample_app, sample_vehicle_data):
    """Test for a single FieldIsExists when getting a single item by id and executing an SQL subquery
    @calc_property([
        FieldIsExists(
            source='carrier_tasks',
            query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
            alias='has_active_trip',
        ),
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get(
        f'/api/v1/has_active_trip/entity/vehicle/{str(vehicle.id)}'
    )

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "entity_carriertask" U0
                   WHERE (U0."vehicle_id" = ("entity_vehicle"."id")
                          AND U0."dt_start" IS NOT NULL
                          AND NOT (U0."dt_finish" IS NOT NULL))
                   LIMIT 1) AS "has_active_trip"
        FROM "entity_vehicle"
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'has_active_trip' in attrs
    assert attrs['has_active_trip'] is True


@pytest.mark.django_db(transaction=True)
def test_isexists_one_field_list(sample_app, sample_vehicle_data):
    """Test for a single FieldIsExists when getting a single item by id and executing an SQL subquery
    @calc_property([
        FieldIsExists(
            source='carrier_tasks',
            query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
            alias='has_active_trip',
        ),
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get('/api/v1/has_active_trip/entity/vehicle/')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "entity_carriertask" U0
                   WHERE (U0."vehicle_id" = ("entity_vehicle"."id")
                          AND U0."dt_start" IS NOT NULL
                          AND NOT (U0."dt_finish" IS NOT NULL))
                   LIMIT 1) AS "has_active_trip"
        FROM "entity_vehicle"
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


@pytest.mark.django_db(transaction=True)
def test_isexists_one_field_item_join(sample_app, sample_vehicle_data):
    """Test for a single FieldIsExists when getting an item by id and executing an SQL subquery with joins
    @calc_property([
        FieldIsExists(
            source='carrier_tasks',
            alias='has_active_trip_with_phone_join',
            query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True) & Q(driver__contact_phone__isnull=False)
                  & ~Q(driver__contact_phone='')
        )
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get(
        f'/api/v1/is_exists_join/entity/vehicle/{str(vehicle.id)}'
    )

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "entity_carriertask" U0
                   INNER JOIN "entity_driver" U2 ON (U0."driver_id" = U2."id")
                   WHERE (U0."vehicle_id" = ("entity_vehicle"."id")
                          AND U0."dt_start" IS NOT NULL
                          AND U0."dt_finish" IS NULL
                          AND U2."contact_phone" IS NOT NULL
                          AND NOT (U2."contact_phone" = ''
                                   AND U2."contact_phone" IS NOT NULL))
                   LIMIT 1) AS "has_active_trip_with_phone_join"
        FROM "entity_vehicle"
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'has_active_trip_with_phone_join' in attrs
    assert attrs['has_active_trip_with_phone_join'] is True


@pytest.mark.django_db(transaction=True)
def test_isexists_one_field_list_join(sample_app, sample_vehicle_data):
    """Test for a single FieldIsExists when getting an item by id and executing an SQL subquery with joins
    @calc_property([
        FieldIsExists(
            source='carrier_tasks',
            alias='has_active_trip_with_phone_join',
            query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True) & Q(driver__contact_phone__isnull=False)
                  & ~Q(driver__contact_phone='')
        )
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get('/api/v1/is_exists_join/entity/vehicle/')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               EXISTS
          (SELECT 1 AS "a"
           FROM "entity_carriertask" U0
           INNER JOIN "entity_driver" U2 ON (U0."driver_id" = U2."id")
           WHERE (U0."vehicle_id" = ("entity_vehicle"."id")
                  AND U0."dt_start" IS NOT NULL
                  AND U0."dt_finish" IS NULL
                  AND U2."contact_phone" IS NOT NULL
                  AND NOT (U2."contact_phone" = ''
                           AND U2."contact_phone" IS NOT NULL))
           LIMIT 1) AS "has_active_trip_with_phone_join"
        FROM "entity_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'has_active_trip_with_phone_join' in attrs
        assert attrs['has_active_trip_with_phone_join'] is True
    assert found, f'Vehicle {vehicle.id} not found in response'


@pytest.mark.django_db(transaction=True)
def test_exists_hierachy_item(sample_app, sample_vehicle_data):
    """Test for a FieldIsExists hierarchy when getting an item by id and executing an SQL subquery with subqueries
    @calc_property([
        FieldIsExists(
            source='carrier_tasks',
            alias='has_active_trip_with_phone_subquery',
            query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True) & Q(_has_drivers_with_phone=True),
            nested=[
                FieldIsExists(source='driver',
                              alias='_has_drivers_with_phone',
                              query=Q(contact_phone__isnull=False) & ~Q(contact_phone=''))
            ]
        )
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get(
        f'/api/v1/is_exists_subquery/entity/vehicle/{str(vehicle.id)}'
    )

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               EXISTS
                  (SELECT 1 AS "a"
                   FROM "entity_carriertask" V0
                   WHERE (V0."vehicle_id" = ("entity_vehicle"."id")
                          AND V0."dt_start" IS NOT NULL
                          AND V0."dt_finish" IS NULL
                          AND EXISTS
                            (SELECT 1 AS "a"
                             FROM "entity_driver" U0
                             WHERE (U0."id" = (V0."driver_id")
                                    AND U0."contact_phone" IS NOT NULL
                                    AND NOT (U0."contact_phone" = ''
                                             AND U0."contact_phone" IS NOT NULL))
                             LIMIT 1))
                   LIMIT 1) AS "has_active_trip_with_phone_subquery"
        FROM "entity_vehicle"
        WHERE "entity_vehicle"."id" = 'id_hex'::UUID
        ORDER BY "entity_vehicle"."id" ASC
        LIMIT 1;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    attrs = data['data']['attributes']

    assert 'has_active_trip_with_phone_subquery' in attrs
    assert attrs['has_active_trip_with_phone_subquery'] is True


@pytest.mark.django_db(transaction=True)
def test_exists_hierachy_list(sample_app, sample_vehicle_data):
    """Test for a FieldIsExists hierarchy when getting an item by id and executing an SQL subquery with subqueries
    @calc_property([
        FieldIsExists(
            source='carrier_tasks',
            alias='has_active_trip_with_phone_subquery',
            query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True) & Q(_has_drivers_with_phone=True),
            nested=[
                FieldIsExists(source='driver',
                              alias='_has_drivers_with_phone',
                              query=Q(contact_phone__isnull=False) & ~Q(contact_phone=''))
            ]
        )
    ])
    """

    vehicle = sample_vehicle_data['vehicle']

    response = get_api_client(sample_app).get('/api/v1/is_exists_subquery/entity/vehicle/')

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "entity_vehicle"."dt_created",
               "entity_vehicle"."dt_updated",
               "entity_vehicle"."id",
               "entity_vehicle"."vehicle_model_id",
               "entity_vehicle"."country_id",
               "entity_vehicle"."gnum",
               EXISTS
          (SELECT 1 AS "a"
           FROM "entity_carriertask" V0
           WHERE (V0."vehicle_id" = ("entity_vehicle"."id")
                  AND V0."dt_start" IS NOT NULL
                  AND V0."dt_finish" IS NULL
                  AND EXISTS
                    (SELECT 1 AS "a"
                     FROM "entity_driver" U0
                     WHERE (U0."id" = (V0."driver_id")
                            AND U0."contact_phone" IS NOT NULL
                            AND NOT (U0."contact_phone" = ''
                                     AND U0."contact_phone" IS NOT NULL))
                     LIMIT 1))
           LIMIT 1) AS "has_active_trip_with_phone_subquery"
        FROM "entity_vehicle"
        LIMIT 20;"""

    assert_sql_query(expected_sql_template, sql_query, vehicle.id.hex)

    data = response.json()
    found = False
    for item in data['data']:
        if item['id'] != str(vehicle.id):
            continue
        found = True
        attrs = item['attributes']
        assert 'has_active_trip_with_phone_subquery' in attrs
        assert attrs['has_active_trip_with_phone_subquery'] is True
    assert found, f'Vehicle {vehicle.id} not found in response'
