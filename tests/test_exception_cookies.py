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
The cookies of a `JsonApiBazisException` are set on the error response of the application:
a `JsonApiCookie` with its attributes, a plain `(key, value, max_age)` with the defaults of
Starlette, as before.
"""

from http.cookies import SimpleCookie

from fastapi.testclient import TestClient

import pytest

from bazis.core.errors import JsonApiBazisError, JsonApiBazisException, JsonApiCookie


@pytest.fixture(scope='module')
def client():
    from bazis.core.app_factory import _create_app_base, _initialize_app

    app = _create_app_base()
    _initialize_app(app)

    @app.get('/cookie-error/')
    def cookie_error():
        raise JsonApiBazisException(
            JsonApiBazisError('Sign in again', code='ERR_AUTH'),
            status=422,
            cookies=[
                JsonApiCookie(
                    'store', 'two', 120, httponly=True, secure=True, samesite='strict',
                    path='/api/',
                ),
            ],
        )

    @app.get('/tuple-cookie-error/')
    def tuple_cookie_error():
        raise JsonApiBazisException(
            JsonApiBazisError('Sign in again'), cookies=[('legacy', 'one', 60)]
        )

    return TestClient(app)


def cookies(response) -> dict:
    """The attributes of each Set-Cookie of the response by the name of the cookie."""
    attrs = ('max-age', 'path', 'samesite', 'httponly', 'secure')
    result = {}
    for header in response.headers.get_list('set-cookie'):
        ((name, morsel),) = SimpleCookie(header).items()
        result[name] = {'value': morsel.value} | {a: morsel[a] for a in attrs if morsel[a]}
    return result


def test_error_response_sets_cookie_attributes(client):
    response = client.get('/cookie-error/')

    assert response.status_code == 422
    assert response.json()['errors'][0]['code'] == 'ERR_AUTH'
    assert cookies(response)['store'] == {
        'value': 'two',
        'max-age': '120',
        'path': '/api/',
        'samesite': 'strict',
        'httponly': True,
        'secure': True,
    }


def test_plain_tuple_cookie_keeps_starlette_defaults(client):
    """A `(key, value, max_age)` cookie is set as before: path `/`, SameSite lax."""
    response = client.get('/tuple-cookie-error/')

    assert response.status_code == 400
    assert cookies(response)['legacy'] == {
        'value': 'one',
        'max-age': '60',
        'path': '/',
        'samesite': 'lax',
    }
