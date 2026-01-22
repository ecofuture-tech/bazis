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
One to one

A calculated field can return values from related "one to one" tables.
"""

import pytest
from bazis_test_utils.utils import get_api_client

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_related_one_to_one(sample_app, dynamic_vehicle_data):
    """
    One related table.

    A calculated field for a vehicle (Vehicle model) with factory assembly data (VehicleAssembleInfo model).

    .. code-block:: python

        @calc_property([FieldDynamic('assemble_info')])
        def vehicle_assemble_info(self, dc: DependsCalc) -> dict:
            return {
                'assembly_date': dc.data.assemble_info.assembly_date,
                'assembly_plant': dc.data.assemble_info.assembly_plant,
            }

    .. code-block:: python

        class VehicleAssembleInfo(DtMixin, UuidMixin, JsonApiMixin):

            assembly_plant = models.CharField('Assembly plant', max_length=50)
            assembly_date = models.DateField('Assembly date')
            country = models.ForeignKey(Country, verbose_name='Country', on_delete=models.CASCADE)

            vin = models.CharField('VIN', max_length=17, unique=True)

            vehicle = models.OneToOneField(
                Vehicle,
                verbose_name='Vehicle',
                related_name='assemble_info',
                on_delete=models.CASCADE
            )
    """

    url = '/api/v1/related_one_to_one/dynamic/vehicle/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "dynamic_vehicle"."dt_created",
               "dynamic_vehicle"."dt_updated",
               "dynamic_vehicle"."id",
               "dynamic_vehicle"."vehicle_model_id",
               "dynamic_vehicle"."gnum",
               "dynamic_vehicleassembleinfo"."dt_created",
               "dynamic_vehicleassembleinfo"."dt_updated",
               "dynamic_vehicleassembleinfo"."id",
               "dynamic_vehicleassembleinfo"."assembly_plant",
               "dynamic_vehicleassembleinfo"."assembly_date",
               "dynamic_vehicleassembleinfo"."country_id",
               "dynamic_vehicleassembleinfo"."vin",
               "dynamic_vehicleassembleinfo"."vehicle_id"
        FROM "dynamic_vehicle"
        LEFT OUTER JOIN "dynamic_vehicleassembleinfo" ON ("dynamic_vehicle"."id" = "dynamic_vehicleassembleinfo"."vehicle_id")
        LIMIT 20;"""
    assert_sql_query(expected_sql_template, sql_query)
