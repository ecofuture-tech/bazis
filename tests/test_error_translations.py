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
The titles and the details of the errors the core answers with are in the language of the
request: the error `ERR_ITEM_INVALID` had a Russian detail (the message of the project)
under the English title `Validation error`.
"""

import pytest
from bazis_test_utils.utils import get_api_client
from validation.models import Booking

from bazis.core.errors import (
    JsonApi401Exception,
    JsonApi403Exception,
    JsonApiBazisError,
    JsonApiHttpException,
    JsonApiRequestValidationError,
)


LANGUAGES = [('en', 'English'), ('ru', 'Русский')]
RU = {'Accept-Language': 'ru'}


@pytest.fixture
def two_languages(monkeypatch):
    # not the fixture `settings`: see tests/test_request_language.py
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGES', LANGUAGES)
    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'en')


def request(app, method, url, *, headers=None, **kwargs):
    client = get_api_client(app)
    return client.client.request(method, url, headers=client.headers | (headers or {}), **kwargs)


@pytest.mark.parametrize(
    'title',
    [
        cls.title
        for cls in (
            JsonApiHttpException,
            JsonApi401Exception,
            JsonApi403Exception,
            JsonApiRequestValidationError,
            JsonApiBazisError,
        )
    ],
)
def test_the_error_titles_are_translated(title):
    from django.utils import translation

    with translation.override('en'):
        english = str(title)
    with translation.override('ru'):
        assert str(title) != english


@pytest.mark.django_db(transaction=True)
def test_item_invalid_title(sample_app, two_languages):
    data = {
        'data': {
            'type': 'validation.booking',
            'attributes': {'title': 'Standup', 'start': 20, 'end': 10},
        }
    }

    response = request(sample_app, 'POST', '/api/v1/validation/booking/', json=data, headers=RU)

    assert response.status_code == 422, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_ITEM_INVALID'
    assert error['title'] == 'Ошибка валидации'

    response = request(sample_app, 'POST', '/api/v1/validation/booking/', json=data)
    assert response.json()['errors'][0]['title'] == 'Validation error'


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('item_id', ['9b657232-4178-4d7f-8b0c-e8ab16f2b309', 'not-a-uuid'])
def test_item_not_found(sample_app, two_languages, item_id):
    url = f'/api/v1/validation/booking/{item_id}/'

    response = request(sample_app, 'GET', url, headers=RU)

    assert response.status_code == 404
    assert response.json()['errors'][0]['detail'] == 'Объект не найден'
    assert request(sample_app, 'GET', url).json()['errors'][0]['detail'] == 'Item not found'


@pytest.mark.django_db(transaction=True)
def test_read_only_relationship(sample_app, two_languages):
    from visibility.models import Folder, Note

    folder = Folder.objects.create(name='a')
    note = Note.objects.create(name='note', folder=folder)
    url = f'/api/v1/visibility/note_frozen/{note.id}/relationships/folder'
    payload = {'data': {'type': 'visibility.folder', 'id': str(folder.id)}}

    response = request(sample_app, 'PATCH', url, json=payload, headers=RU)

    assert response.status_code == 403
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_RELATIONSHIP_READONLY'
    assert error['title'] == 'Связь только для чтения'
    assert error['detail'] == 'Связь folder нельзя изменить'


@pytest.mark.django_db(transaction=True)
def test_invalid_filter(sample_app, two_languages):
    Booking.objects.create(title='Standup', start=1, end=2)

    response = request(
        sample_app, 'GET', '/api/v1/validation/booking/?filter=unknown=1', headers=RU
    )

    assert response.status_code == 400
    assert response.json()['errors'][0]['title'] == 'Недопустимый фильтр'
