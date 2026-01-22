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

import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.django_db()
def test_filter_fields_calc_bool(sample_app):
    """
    Calculated field with Bool response.

    Calculated field for vehicles (Vehicle model) with information about whether the car
    has an active trip (CarrierTask model).

    .. code-block:: python

        @calc_property(
            [
                FieldIsExists(
                    source='carrier_tasks',
                    query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
                    alias='has_active_trip',
                ),
            ],
            as_filter=True
        )
        def has_active_trip(self) -> bool:
            return get_attr(self, 'has_active_trip', False)
    """

    url = '/api/v1/has_active_trip/entity/vehicle/route_filter_fields/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/entity/vehicle_model/'},
            {'name': 'country', 'py_type': '/api/v1/entity/country/'},
            {'name': 'has_active_trip', 'py_type': 'boolean'},
        ]
    }
