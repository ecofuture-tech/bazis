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


@pytest.mark.django_db(transaction=True)
def test_unknown_path_returns_jsonapi_error(sample_app):
    response = get_api_client(sample_app).get('/api/v1/unknown/path/')

    assert response.status_code == 404
    assert response.json()['errors'][0]['status'] == 404


@pytest.mark.django_db(transaction=True)
def test_method_not_allowed_returns_jsonapi_error_with_headers(sample_app):
    response = get_api_client(sample_app).put('/api/healthcheck')

    assert response.status_code == 405
    assert response.json()['errors'][0]['status'] == 405
    assert response.headers['allow'] == 'GET'


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_value',
    ["name') OR ('1'='1", 'id=not-a-uuid'],
)
def test_malformed_filter_returns_bad_request(sample_app, filter_value):
    response = get_api_client(sample_app).get(
        '/api/v1/entity/vehicle_brand/', params={'filter': filter_value}
    )

    assert response.status_code == 400
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_FILTER'
    assert error['source'] == {'pointer': '/query/filter'}
