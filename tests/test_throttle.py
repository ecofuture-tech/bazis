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
The request rate limits of routes (`bazis.core.throttle`): a fixed window in Redis, 429
`ERR_THROTTLED` with `Retry-After`; the public actions get `BAZIS_THROTTLE_PUBLIC` (sample:
`entity.routes.CountryRouteSet`).
"""

from types import SimpleNamespace

from django import forms
from django.core.cache import cache
from django.test import override_settings

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import pytest
from bazis_test_utils.utils import get_api_client

from bazis.core.errors import JsonApiThrottledException
from bazis.core.routes_abstract.initial import OPENAPI_EXTENSION
from bazis.core.throttle import Throttle, parse_rate, throttle


URL = '/api/v1/entity/country/'


@pytest.fixture(autouse=True)
def throttle_counts():
    cache.delete_pattern('bazis:throttle:*')
    yield
    cache.delete_pattern('bazis:throttle:*')


def exempt_local(request, ident):
    return ident == 'ip:127.0.0.1'


def statuses(client, path, times):
    return [client.get(f'{URL}{path}').status_code for _ in range(times)]


@pytest.mark.django_db
def test_throttle(sample_app):
    """
    Over the rate the route answers 429 `ERR_THROTTLED` with the seconds to the next
    window in `Retry-After`; the routes of a scope share the count, the other routes are
    not limited.
    """
    client = get_api_client(sample_app)
    assert statuses(client, 'capital/', 2) == [200, 200]
    response = client.get(f'{URL}border/')
    assert response.status_code == 429
    (error,) = response.json()['errors']
    assert (error['status'], error['code']) == (429, 'ERR_THROTTLED')
    assert 1 <= int(response.headers['Retry-After']) <= 60
    assert client.get(f'{URL}greeting/').status_code == 200
    assert client.get(URL).status_code == 200


@pytest.mark.django_db
def test_throttle_off(sample_app):
    """
    `BAZIS_THROTTLE_ENABLED` off and `BAZIS_THROTTLE_EXEMPT` (an import path of a function
    of the request and whom it counts) let the requests through.
    """
    client = get_api_client(sample_app)
    with override_settings(BAZIS_THROTTLE_ENABLED=False):
        assert statuses(client, 'capital/', 3) == [200] * 3
    with override_settings(BAZIS_THROTTLE_EXEMPT=f'{__name__}.exempt_local'):
        assert statuses(client, 'capital/', 3) == [200] * 3
    assert statuses(client, 'capital/', 3) == [200, 200, 429]


@pytest.mark.django_db
def test_public_action(sample_app):
    """
    A public action without a throttle of its own is limited by `BAZIS_THROTTLE_PUBLIC`
    (dynamic: read per request), per IP address; empty: unlimited.
    """
    client = get_api_client(sample_app)
    with override_settings(BAZIS_THROTTLE_PUBLIC='1/second'):
        assert statuses(client, 'greeting/', 2) == [200, 429]
    with override_settings(BAZIS_THROTTLE_PUBLIC=''):
        assert statuses(client, 'greeting/', 3) == [200] * 3

    meta = sample_app.openapi()['paths'][f'{URL}greeting/']['get'][OPENAPI_EXTENSION]
    assert meta['public'] is True


@pytest.mark.django_db
def test_plain_fastapi_route():
    """
    `throttle` is a FastAPI dependency of any route: outside a route class it counts by the
    IP address, per route.
    """
    app = FastAPI()

    @app.exception_handler(JsonApiThrottledException)
    async def throttled(request, exc):
        # the application of Bazis answers JSON:API errors
        return JSONResponse({'code': exc.code}, status_code=exc.status_code, headers=exc.headers)

    @app.get('/ping', dependencies=[throttle('1/minute')])
    def ping():
        return 'pong'

    client = TestClient(app)
    assert client.get('/ping').status_code == 200
    response = client.get('/ping')
    assert (response.status_code, response.json()) == (429, {'code': 'ERR_THROTTLED'})
    assert 'Retry-After' in response.headers


def test_ident():
    """
    `user_or_ip` counts an authenticated user by his key, an anonymous one (or a route
    without a user) by the IP address; `ip` always by the IP address.
    """
    request = SimpleNamespace(client=SimpleNamespace(host='10.0.0.1'))
    user = SimpleNamespace(pk=7, is_anonymous=False)
    anonymous = SimpleNamespace(pk=None, is_anonymous=True)
    assert Throttle('1/s').ident(request, user) == 'user:7'
    assert Throttle('1/s').ident(request, anonymous) == 'ip:10.0.0.1'
    assert Throttle('1/s').ident(request, None) == 'ip:10.0.0.1'
    assert Throttle('1/s', key='ip').ident(request, user) == 'ip:10.0.0.1'


@pytest.mark.django_db
def test_failures_let_the_requests_through(sample_app, monkeypatch, caplog):
    """
    A failing cache (Redis down) and an invalid rate of a callable (a dynamic setting edited
    by hand) are logged and let the requests through; an invalid static rate fails at
    import.
    """
    client = get_api_client(sample_app)

    class Failing:
        def __getattr__(self, name):
            def failing(*args, **kwargs):
                raise ConnectionError('redis is down')

            return failing

    monkeypatch.setattr('bazis.core.throttle.cache', Failing())
    assert statuses(client, 'capital/', 3) == [200] * 3
    assert 'the cache failed' in caplog.text
    monkeypatch.undo()

    with override_settings(BAZIS_THROTTLE_PUBLIC='often'):
        assert statuses(client, 'greeting/', 2) == [200, 200]
    assert "Invalid throttle rate 'often'" in caplog.text


def test_public_rate_setting():
    """
    `BAZIS_THROTTLE_PUBLIC` is validated when the settings load and in the admin (the
    constance field `throttle_rate`); empty is unlimited.
    """
    from pydantic import ValidationError

    from bazis.core.conf import Settings
    from bazis.core.throttle import RateFormField

    assert Settings(BAZIS_THROTTLE_PUBLIC='').BAZIS_THROTTLE_PUBLIC == ''
    assert Settings(BAZIS_THROTTLE_PUBLIC='5/s').BAZIS_THROTTLE_PUBLIC == '5/s'
    with pytest.raises(ValidationError):
        Settings(BAZIS_THROTTLE_PUBLIC='5 per minute')

    field = RateFormField()
    assert field.clean('') == '' and field.clean('10/hour') == '10/hour'
    with pytest.raises(forms.ValidationError):
        field.clean('10/week')

    from django.conf import settings

    assert settings.CONSTANCE_CONFIG['BAZIS_THROTTLE_PUBLIC'][2] == 'throttle_rate'


@pytest.mark.django_db
def test_client_address_behind_a_proxy():
    """
    The address is the one the server gives (`request.client`): uvicorn takes it from
    `X-Forwarded-For` only of the proxies of `forwarded_allow_ips`; a client that sends the
    header itself is counted by its own address, however it varies the header.
    """
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    app = FastAPI()

    @app.exception_handler(JsonApiThrottledException)
    async def throttled(request, exc):
        return JSONResponse({}, status_code=exc.status_code, headers=exc.headers)

    @app.get('/ping', dependencies=[throttle('1/minute')])
    def ping(request: Request):
        return request.client.host

    served = ProxyHeadersMiddleware(app, trusted_hosts='10.0.0.1')
    spoofer = TestClient(served, client=('203.0.113.5', 5000))
    assert spoofer.get('/ping', headers={'X-Forwarded-For': '198.51.100.1'}).json() == '203.0.113.5'
    assert spoofer.get('/ping', headers={'X-Forwarded-For': '198.51.100.2'}).status_code == 429

    proxy = TestClient(served, client=('10.0.0.1', 5000))
    for address in ('198.51.100.7', '198.51.100.8'):
        response = proxy.get('/ping', headers={'X-Forwarded-For': address})
        assert (response.status_code, response.json()) == (200, address)


def test_rates():
    assert parse_rate('30/minute') == (30, 60)
    assert parse_rate('5/s') == (5, 1)
    assert parse_rate('100/day') == (100, 86400)
    for rate in ('30', '0/minute', 'x/minute', '3/week', None):
        with pytest.raises(ValueError):
            parse_rate(rate)
    with pytest.raises(ValueError):
        throttle('3/week')
    with pytest.raises(ValueError):
        throttle('3/minute', key='session')
    # a callable rate is read per request
    assert Throttle(lambda: '1/minute').rate() == '1/minute'
