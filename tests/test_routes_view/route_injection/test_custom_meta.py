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

from datetime import datetime

import pytest
from bazis_test_utils.utils import get_api_client


def truncate_to_seconds(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


@pytest.mark.django_db(transaction=True)
def test_vehicle_meta_timestamps(sample_app, route_injection_vehicle_data):
    """
    Checking the presence of the `timestamps` meta field in the JSON:API response.
    """
    vehicle = route_injection_vehicle_data['vehicle']
    vehicle_id = vehicle.id
    url = f'/api/v1/route_injection/vehicle/{vehicle_id}/?meta=timestamps'

    response = get_api_client(sample_app).get(url)
    assert response.status_code == 200

    actual = response.json()

    expected = {
        'data': {
            'id': str(vehicle.id),
            'type': 'route_injection.vehicle',
            'bs:action': 'view',
            'attributes': {
                'gnum': vehicle.gnum,
                'dt_created': '2025-04-27T12:28:17',
                'dt_updated': '2025-04-27T12:28:17',
            },
            'relationships': {
                'vehicle_model': {
                    'data': {
                        'id': str(vehicle.vehicle_model.id),
                        'type': 'route_injection.vehicle_model',
                    }
                }
            },
        },
        'meta': {
            'timestamps': {
                'before_db_request_timestamp': '2025-04-29T12:28:17',
                'after_db_request_timestamp': '2025-04-29T12:28:17',
                'db_request_duration_ms': 3,
            }
        },
    }

    # ===== Processing timestamps =====
    actual_timestamps = actual['meta'].pop('timestamps', {})
    expected['meta'].pop('timestamps')

    for field in ('before_db_request_timestamp', 'after_db_request_timestamp'):
        actual_value = actual_timestamps.get(field)

        assert isinstance(actual_value, str)
        # We do not compare the value directly, only check the type
        actual_dt = datetime.fromisoformat(actual_value)
        assert isinstance(actual_dt, datetime)

    assert isinstance(actual_timestamps.get('db_request_duration_ms'), int)
    assert actual_timestamps.get('db_request_duration_ms') >= 0

    # ===== Processing dt_created and dt_updated =====
    for field in ('dt_created', 'dt_updated'):
        actual_value = actual['data']['attributes'].pop(field, None)
        expected['data']['attributes'].pop(field)

        assert isinstance(actual_value, str)
        # We do not compare the value directly, only check the type
        actual_dt = datetime.fromisoformat(actual_value.replace('Z', '+00:00'))
        assert isinstance(actual_dt, datetime)

    # ===== Comparing the remaining part =====
    assert actual == expected
