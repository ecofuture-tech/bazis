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
`route_filter_fields/` gives a relation filter the path of the list of the related model.
The route set of the related model may have no list (a file upload: `create` and `retrieve`
only): the relation is then listed with the `unknown` type, as a relation to a model without
a route.
"""

import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.django_db()
def test_relation_to_a_route_set_without_list_is_unknown(sample_app):
    client = get_api_client(sample_app)

    assert client.get('/api/v1/catalog/upload/').status_code in (404, 405)

    response = client.get('/api/v1/catalog/form/route_filter_fields/')

    assert response.status_code == 200
    fields = {field['name']: field['py_type'] for field in response.json()['fields']}
    assert fields['upload'] == 'unknown'
    assert fields['title'] == 'string'
