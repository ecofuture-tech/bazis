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
A value that a schema rejects with an error that has its own context (an email with a
reserved domain, which `EmailStr` refuses) is reported as the validation error with its
message, like any other: not as the `TypeError` of the error rebuilt without the context.
"""

import pytest
from bazis_test_utils.utils import get_api_client
from validation.models import Person


@pytest.mark.django_db(transaction=True)
def test_stored_value_rejected_by_response_schema(sample_app):
    person = Person.objects.create(name='Ann', email='smoke@example.test')

    response = get_api_client(sample_app).get('/api/v1/validation/person/')

    assert response.status_code == 422, response.text
    [error] = response.json()['errors']
    assert error['code'] == 'ERR_VALIDATE'
    assert error['detail'].startswith('value is not a valid email address')
    assert error['source'] == {
        'pointer': '/attributes/email',
        'id': str(person.pk),
        'type': 'validation.person',
    }


@pytest.mark.django_db(transaction=True)
def test_invalid_request_value_stays_422(sample_app):
    response = get_api_client(sample_app).post(
        '/api/v1/validation/person/',
        json_data={
            'data': {
                'type': 'validation.person',
                'attributes': {'name': 'Ann', 'email': 'smoke@example.test'},
            }
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()['errors'][0]['code'] == 'ERR_VALIDATE'
    assert not Person.objects.exists()
