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

from fastapi.exceptions import ResponseValidationError

import pytest
from bazis_test_utils.utils import get_api_client


def truncate_to_seconds(dt: datetime) -> str | None:
    if dt is None:
        return None
    # Truncate microseconds and format in FastAPI style (with 'Z' instead of '+00:00')
    return dt.replace(microsecond=0).isoformat() + 'Z'  # 2025-04-30T08:44:02Z


@pytest.mark.django_db(transaction=True)
def test_get_vehicle_current_task(sample_app, route_injection_vehicle_data):
    """
    Checking the current transportation task for the vehicle.
    """

    ## Checking retrieval of the current transportation task for the vehicle.

    vehicle = route_injection_vehicle_data['vehicle']
    driver = route_injection_vehicle_data['driver']
    organization = route_injection_vehicle_data['organization']
    task2 = route_injection_vehicle_data['tasks'][1]

    vehicle_id = vehicle.id

    url = (
        f'/api/v1/custom_response_model/route_injection/vehicle/{vehicle_id}/current_carrier_task/'
    )

    response = get_api_client(sample_app).get(url)
    assert response.status_code == 200

    actual = response.json()

    expected = {
        'data': {
            'id': str(task2.id),
            'type': 'route_injection.carrier_task',
            'bs:action': 'view',
            'attributes': {
                'dt_created': truncate_to_seconds(task2.dt_created),
                'dt_updated': truncate_to_seconds(task2.dt_updated),
                'dt_start': truncate_to_seconds(task2.dt_start),
                'dt_finish': None,
                'fact_waste_weight': '4.500',
            },
            'relationships': {
                'vehicle': {'data': {'id': str(vehicle.id), 'type': 'route_injection.vehicle'}},
                'driver': {'data': {'id': str(driver.id), 'type': 'route_injection.driver'}},
                'org_owner': {
                    'data': {'id': str(organization.id), 'type': 'route_injection.organization'}
                },
            },
        }
    }

    # ===== Handling dt_created and dt_updated =====
    for field in ('dt_created', 'dt_updated', 'dt_start'):
        actual_value = actual['data']['attributes'].pop(field, None)
        expected['data']['attributes'].pop(field)

        assert isinstance(actual_value, str)
        # We do not compare the value directly, only check the type
        actual_dt = datetime.fromisoformat(actual_value.replace('Z', '+00:00'))
        assert isinstance(actual_dt, datetime)

    assert actual == expected

    ## Checking adjustment of the current transportation task for the vehicle.

    driver2 = route_injection_vehicle_data['driver2']

    response = get_api_client(sample_app).patch(
        url,
        json_data={
            'driver_id': str(driver2.id),
        },
    )

    assert response.status_code == 200

    actual = response.json()

    expected = {
        'data': {
            'id': str(task2.id),
            'type': 'route_injection.carrier_task',
            'bs:action': 'view',
            'attributes': {
                'dt_created': truncate_to_seconds(task2.dt_created),
                'dt_updated': truncate_to_seconds(task2.dt_updated),
                'dt_start': truncate_to_seconds(task2.dt_start),
                'dt_finish': None,
                'fact_waste_weight': '4.500',
            },
            'relationships': {
                'vehicle': {'data': {'id': str(vehicle.id), 'type': 'route_injection.vehicle'}},
                'driver': {'data': {'id': str(driver2.id), 'type': 'route_injection.driver'}},
                'org_owner': {
                    'data': {'id': str(organization.id), 'type': 'route_injection.organization'}
                },
            },
        },
        'meta': None,
    }

    # ===== Handling dt_created and dt_updated =====
    for field in ('dt_created', 'dt_updated', 'dt_start'):
        actual_value = actual['data']['attributes'].pop(field, None)
        expected['data']['attributes'].pop(field)

        assert isinstance(actual_value, str)
        # We do not compare the value directly, only check the type
        actual_dt = datetime.fromisoformat(actual_value.replace('Z', '+00:00'))
        assert isinstance(actual_dt, datetime)

    assert actual == expected


@pytest.mark.django_db(transaction=True)
def test_get_some_static(sample_app):
    """
    Checking custom response, positive scenario.

    For the endpoint method, it is explicitly specified that the response is a list of dictionaries, and therefore validation and response are without errors.

        def get_some_statics(self, **kwargs) -> list[dict]:
        # Check with correct response description
        return [{'k1': 'v1'}, {'k2': 'v2'}]
    """

    url = '/api/v1/custom_response_model/route_injection/vehicle/some_statics/'

    response = get_api_client(sample_app).get(url)
    assert response.status_code == 200

    actual = response.json()
    expected = [{'k1': 'v1'}, {'k2': 'v2'}]
    assert actual == expected


@pytest.mark.django_db(transaction=True)
def test_get_some_static_negative_1(sample_app):
    """
    Checking custom response, negative scenario.

    For the endpoint method, the response model is not explicitly specified, so the error only validates the presence of the id field.

        def get_some_statics_negative_1(self, **kwargs):
        # Reproducing the error when the response description is missing
        return [{'k1': 'v1'}, {'k2': 'v2'}]
    """

    url = '/api/v1/custom_response_model/route_injection/vehicle/some_statics_negative_1/'

    response = get_api_client(sample_app).get(url)
    assert response.status_code == 422

    actual = response.json()
    assert actual['errors'] == [
        {
            'code': 'ERR_VALIDATE',
            'detail': 'Field required',
            'source': {'pointer': '/id'},
            'status': 422,
            'title': 'missing',
        },
    ]


@pytest.mark.django_db(transaction=True)
def test_get_some_static_negative_2(sample_app):
    """
    Checking custom response, negative scenario.
    """

    url = '/api/v1/custom_response_model/route_injection/vehicle/some_statics_negative_2/'

    with pytest.raises(ResponseValidationError) as exc_info:
        response = get_api_client(sample_app).get(url)

    err = exc_info.value
    assert isinstance(err, ResponseValidationError)
    assert err.errors()[0]['type'] == 'dict_type'
    assert 'Input should be a valid dictionary' in err.errors()[0]['msg']

    from fastapi.testclient import TestClient

    from bazis.core.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        '/api/v1/custom_response_model/route_injection/vehicle/some_statics_negative_2/'
    )
    assert response.status_code == 500
