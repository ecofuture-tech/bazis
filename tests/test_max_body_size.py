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
The limit of the size of a request body (`BAZIS_API_MAX_BODY_SIZE`): 413
`ERR_BODY_TOO_LARGE` by `Content-Length` before the application reads the body, and for a
body without it (chunked) as soon as the bytes received exceed the limit; without a limit
(0, the default) and within it a request is unchanged.
"""

import asyncio
import json

from django.conf import settings

from starlette.datastructures import Headers

import pytest
from entity.models import VehicleBrand

from bazis.core.conf import Settings


URL = '/api/v1/entity/vehicle_brand/'


def document(padding: int = 0) -> bytes:
    """A create of a vehicle brand, with `padding` spaces after the JSON (still valid JSON)."""
    data = {
        'data': {'type': 'entity.vehicle_brand', 'bs:action': 'add', 'attributes': {'name': 'Ford'}}
    }
    return json.dumps(data).encode() + b' ' * padding


def post(app, chunks: list[bytes], content_length: bool = True, query: bytes = b''):
    """
    A POST of the body `chunks` (one ASGI message each) to the application, with or without
    `Content-Length`. Returns the status, the headers and the JSON of the response and the
    number of the chunks the application received.
    """
    headers = [(b'content-type', b'application/vnd.api+json')]
    if content_length:
        headers.append((b'content-length', str(sum(map(len, chunks))).encode()))
    else:
        headers.append((b'transfer-encoding', b'chunked'))
    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'POST',
        'scheme': 'http',
        'path': URL,
        'raw_path': URL.encode(),
        'root_path': '',
        'query_string': query,
        'headers': headers,
        'client': ('127.0.0.1', 5000),
        'server': ('testserver', 80),
    }
    pending = list(chunks)
    received = 0
    messages = []

    async def receive():
        nonlocal received
        if not pending:
            return {'type': 'http.disconnect'}
        received += 1
        return {'type': 'http.request', 'body': pending.pop(0), 'more_body': len(pending) > 0}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start, body = messages[0], b''.join(it.get('body', b'') for it in messages[1:])
    return start['status'], Headers(raw=start['headers']), json.loads(body), received


def split(body: bytes, parts: int) -> list[bytes]:
    size = -(-len(body) // parts)
    return [body[i : i + size] for i in range(0, len(body), size)]


def assert_too_large(status, payload, detail='Request body too large'):
    assert status == 413
    [error] = payload['errors']
    assert (error['status'], error['code'], error['detail']) == (413, 'ERR_BODY_TOO_LARGE', detail)


def test_no_limit_by_default():
    assert Settings.model_fields['BAZIS_API_MAX_BODY_SIZE'].default == 0
    assert settings.BAZIS_API_MAX_BODY_SIZE == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('content_length', [True, False])
def test_without_a_limit_a_large_body_passes(sample_app, content_length):
    body = document(padding=3 * 1024 * 1024)
    status, _headers, payload, _received = post(sample_app, split(body, 8), content_length)
    assert status == 201
    assert payload['data']['attributes']['name'] == 'Ford'


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('content_length', [True, False])
def test_a_body_of_the_limit_passes(sample_app, monkeypatch, content_length):
    body = document(padding=100)
    monkeypatch.setattr(settings, 'BAZIS_API_MAX_BODY_SIZE', len(body))
    status, _headers, payload, received = post(sample_app, split(body, 4), content_length)
    assert status == 201
    assert payload['data']['attributes']['name'] == 'Ford'
    assert received == 4


@pytest.mark.django_db(transaction=True)
def test_content_length_over_the_limit_is_refused_before_the_body_is_read(sample_app, monkeypatch):
    body = document(padding=100)
    monkeypatch.setattr(settings, 'BAZIS_API_MAX_BODY_SIZE', len(body) - 1)
    status, headers, payload, received = post(sample_app, split(body, 4))
    assert_too_large(status, payload)
    # the application never ran: no chunk was received, nothing was created
    assert received == 0
    assert not VehicleBrand.objects.exists()
    # inside the language middleware
    assert 'Accept-Language' in headers['vary']


@pytest.mark.django_db(transaction=True)
def test_chunked_body_over_the_limit_is_refused_when_it_exceeds_it(sample_app, monkeypatch):
    chunks = split(document(padding=1000), 10)
    monkeypatch.setattr(settings, 'BAZIS_API_MAX_BODY_SIZE', sum(map(len, chunks[:3])))
    status, headers, payload, received = post(sample_app, chunks, content_length=False)
    assert_too_large(status, payload)
    # the reading stopped at the chunk that exceeds the limit, before the body was parsed
    assert received == 4
    assert not VehicleBrand.objects.exists()
    assert 'Accept-Language' in headers['vary']


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('content_length', [True, False])
def test_error_is_in_the_language_of_the_request(sample_app, monkeypatch, content_length):
    # not the fixture `settings`: see test_request_language
    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    monkeypatch.setattr(settings, 'BAZIS_API_MAX_BODY_SIZE', 10)
    status, _headers, payload, _received = post(
        sample_app, split(document(), 4), content_length, query=b'lang=ru'
    )
    assert_too_large(status, payload, 'Слишком большое тело запроса')


def test_the_limit_is_inside_the_cors_and_language_middlewares(sample_app):
    """
    A browser reads the error only with the headers of CORS, and its text is translated: the
    limit runs inside both, and before the rest of the application.
    """
    names = [it.cls.__name__ for it in sample_app.user_middleware]
    limit = names.index('MaxBodySizeMiddleware')
    assert names.index('CORSMiddleware') < names.index('LanguageMiddleware') < limit
    assert limit < names.index('CloseOldConnectionsMiddleware')
