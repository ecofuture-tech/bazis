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
MEDIA_URL and STATIC_URL: a redirect to the host of the files; without a host, the
application serves them itself in DEBUG and answers 404 otherwise, never a redirect to
itself (a loop).
"""

from starlette.datastructures import URL
from starlette.requests import HTTPConnection
from starlette.testclient import TestClient

import pytest


@pytest.fixture
def files(settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_HOST_URL = None
    settings.ADMIN_HOST_URL = ''
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    settings.STATIC_ROOT = str(tmp_path / 'static')
    (tmp_path / 'media' / 'files').mkdir(parents=True)
    (tmp_path / 'media' / 'files' / 'photo.png').write_bytes(b'\x89PNG')
    (tmp_path / 'media' / 'files' / 'page.html').write_text('<script>alert(1)</script>')
    (tmp_path / 'static').mkdir()
    (tmp_path / 'static' / 'schemas_en.json').write_text('{}')
    (tmp_path / 'secret.txt').write_text('secret')
    (tmp_path / 'media' / 'files' / 'link.txt').symlink_to(tmp_path / 'secret.txt')
    return settings


@pytest.fixture
def client(sample_app):
    return TestClient(sample_app, follow_redirects=False)


def test_media_is_served_in_debug_without_a_host(files, client):
    response = client.get('/media/files/photo.png')

    assert response.status_code == 200
    assert response.content == b'\x89PNG'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Content-Security-Policy'] == 'sandbox'
    assert 'Content-Disposition' not in response.headers


def test_media_that_is_not_a_raster_image_is_downloaded(files, client):
    response = client.get('/media/files/page.html')

    assert response.status_code == 200
    assert response.headers['Content-Disposition'] == 'attachment'
    assert response.headers['Content-Security-Policy'] == 'sandbox'


@pytest.mark.parametrize(
    'path',
    [
        '/media/files/missing.png',
        '/media/..%2Fsecret.txt',
        # a symbolic link out of MEDIA_ROOT
        '/media/files/link.txt',
    ],
)
def test_missing_media_is_not_found(files, client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.json()['errors'][0]['status'] == 404


def test_static_is_served_in_debug_without_a_host(files, client):
    response = client.get('/static/schemas_en.json')

    assert response.status_code == 200
    assert response.json() == {}


@pytest.mark.parametrize(
    'media_host, admin_host, location',
    [
        ('https://media.example.com', '', 'https://media.example.com/media/files/photo.png'),
        (None, 'https://admin.example.com/', 'https://admin.example.com/media/files/photo.png'),
    ],
)
def test_media_redirects_to_its_host(files, client, media_host, admin_host, location):
    files.MEDIA_HOST_URL = media_host
    files.ADMIN_HOST_URL = admin_host

    response = client.get('/media/files/photo.png')

    assert response.status_code == 307
    assert response.headers['location'] == location


@pytest.mark.parametrize(
    'host',
    [
        'http://testserver',
        # behind a proxy that terminates TLS the request of the application is http
        'https://testserver/',
        # the default port of the scheme
        'https://testserver:443',
    ],
)
def test_a_host_that_is_the_application_is_not_redirected_to(files, client, host):
    files.ADMIN_HOST_URL = host

    assert client.get('/media/files/photo.png').status_code == 200
    assert client.get('/static/schemas_en.json').status_code == 200


@pytest.mark.parametrize('url', ['/media/files/photo.png', '/static/schemas_en.json'])
def test_a_malformed_port_of_the_request_is_not_the_application(
    files, client, monkeypatch, url
):
    """
    A port that is not a number in the Host header (Starlette before 1.0 keeps it in the
    URL of the request; later versions replace it with the address of the server) matches
    no address: a redirect to the host, never 500.
    """
    files.ADMIN_HOST_URL = 'http://testserver'
    monkeypatch.setattr(
        HTTPConnection, 'url', property(lambda request: URL(f'http://testserver:abc{request.scope["path"]}'))
    )

    response = client.get(url, headers={'Host': 'testserver:abc'})

    assert response.status_code == 307
    assert response.headers['location'] == f'http://testserver{url}'


@pytest.mark.parametrize(
    'host, location',
    [
        # the same domain, another path: the storage of another server
        ('https://testserver/storage', 'https://testserver/storage/media/files/photo.png'),
        # the same host on another port
        ('http://testserver:8001', 'http://testserver:8001/media/files/photo.png'),
    ],
)
def test_another_url_of_the_same_host_is_redirected_to(files, client, host, location):
    files.MEDIA_HOST_URL = host

    response = client.get('/media/files/photo.png')

    assert response.status_code == 307
    assert response.headers['location'] == location


@pytest.mark.parametrize(
    'url, setting',
    [
        ('/media/files/photo.png', 'BS_MEDIA_HOST_URL'),
        ('/static/schemas_en.json', 'BS_ADMIN_HOST_URL'),
    ],
)
def test_files_without_a_host_and_without_debug_are_not_found(files, client, url, setting):
    files.DEBUG = False

    response = client.get(url)

    assert response.status_code == 404
    assert setting in response.json()['errors'][0]['detail']
