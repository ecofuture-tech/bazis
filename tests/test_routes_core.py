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
