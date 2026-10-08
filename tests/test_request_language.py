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
The language of a request (`LanguageMiddleware`) and the texts of the schemas in it: the
schemas are cached once per process, and their titles must follow the language of each
request, not the language of the first request that built them.
"""

from fastapi.testclient import TestClient

import pytest

from bazis.core.i18n import request_language


LANGUAGES = [('en', 'English'), ('ru', 'Русский')]
SCHEMA_LIST = '/api/v1/entity/vehicle_model/schema_list/'


@pytest.fixture
def two_languages(monkeypatch):
    """
    The project in English and Russian. Not with the fixture `settings` of pytest-django:
    its signal `setting_changed` makes Django replace the translations of the request
    context of the core (`bazis.core.i18n.TransActive`) with thread-local ones, which the
    routes run in the thread pool do not see.
    """
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGES', LANGUAGES)
    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'en')


@pytest.mark.parametrize(
    'query, header, expected',
    [
        (None, None, 'en'),
        ('ru', None, 'ru'),
        ('RU', None, 'ru'),
        ('ru-RU', None, 'ru'),
        ('ru_RU', None, 'ru'),
        (None, 'ru-RU,ru;q=0.9,en;q=0.8', 'ru'),
        (None, 'ru-RU', 'ru'),
        # by weight, not by position
        (None, 'en;q=0.5, ru;q=0.9', 'ru'),
        # a language of the project after the ones it does not have
        (None, 'de-DE,de;q=0.9,ru;q=0.5', 'ru'),
        (None, 'de', 'en'),
        (None, '*', 'en'),
        (None, 'ru;q=0', 'en'),
        (None, 'not a header;;', 'en'),
        # ?lang wins over the header, unless the project does not have it
        ('en', 'ru', 'en'),
        ('xx', 'ru', 'ru'),
    ],
)
def test_request_language(two_languages, query, header, expected):
    assert request_language(query, header) == expected


def test_the_default_language_is_a_language_of_the_project(two_languages, monkeypatch):
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'ru-RU')

    assert request_language(None, 'de') == 'ru'


def test_default_language_code():
    from bazis.core.conf import Settings

    assert Settings.model_fields['LANGUAGE_CODE'].default == 'en'


def property_titles(schema: dict, name: str) -> set[str]:
    """
    The titles of the properties `name` of the definitions of a JSON schema.
    """
    return {
        definition['properties'][name]['title']
        for definition in schema.get('$defs', {}).values()
        if name in definition.get('properties', {})
    }


@pytest.mark.django_db
def test_schemas_follow_the_language_of_each_request(sample_app, two_languages):
    """
    One process answers the schema of a route in Russian and in English, in any order: the
    cached schema keeps the texts translatable (`dt_created` is "Creation time" of the core).
    """
    client = TestClient(sample_app)

    def titles(language):
        response = client.get(SCHEMA_LIST, headers={'Accept-Language': language})
        assert response.status_code == 200, response.text
        return property_titles(response.json(), 'dt_created')

    assert titles('ru-RU,ru;q=0.9') == {'Время добавления'}
    assert titles('en-US,en;q=0.9') == {'Creation time'}
    assert titles('ru') == {'Время добавления'}


def test_openapi_in_the_active_language(sample_app, two_languages):
    """
    `app.openapi()` (served as /openapi.json, in the language of the request) is in the
    active language, built once per language; a reset of `app.openapi_schema` builds it
    again, as with FastAPI.
    """
    from django.utils import translation

    def titles(openapi):
        schemas = openapi['components']['schemas']
        return property_titles(
            {'$defs': {k: v for k, v in schemas.items() if 'entity__vehicle_model__' in k}},
            'dt_created',
        )

    with translation.override('ru'):
        russian = sample_app.openapi()
    with translation.override('en'):
        english = sample_app.openapi()
    with translation.override('ru'):
        assert sample_app.openapi() is russian

    assert titles(russian) == {'Время добавления'}
    assert titles(english) == {'Creation time'}

    sample_app.openapi_schema = None
    with translation.override('ru'):
        rebuilt = sample_app.openapi()
    assert rebuilt is not russian
    assert rebuilt == russian
