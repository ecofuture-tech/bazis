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

from django.test import override_settings

import pytest
from bazis_test_utils.utils import get_api_client


@override_settings(DEBUG=True, BAZIS_API_PAGINATION_PAGE_SIZE_MAX=1000)
@pytest.mark.django_db(transaction=True)
def test_apidoc():
    from bazis.core.app import app

    api_client = get_api_client(app)

    response = api_client.get('/api/openapi.json')

    assert response.status_code == 200
    assert 'openapi' in response.json().keys()
    assert 'info' in response.json().keys()
    assert 'paths' in response.json().keys()
