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
def test_context_errors(sample_app, sample_vehicle_data):
    """Test to check for the absence of the declared context."""

    with pytest.raises(KeyError, match="Missing keys in the request context: {'_user'}"):
        get_api_client(sample_app).get('/api/v1/context/entity/division/')

        pytest.fail('A KeyError was expected, but the request completed successfully.')


@pytest.mark.django_db(transaction=True)
def test_field_error(sample_app, sample_vehicle_data, caplog):
    """Test to check for the presence of related tables."""

    with caplog.at_level('WARNING'):
        response = get_api_client(sample_app).get('/api/v1/json/entity/division/')

    assert response.status_code == 200
    assert any(
        'Error in calculated field drivers_list1: model Division does not have related table drivers1'
        in message
        for message in caplog.messages
    )
