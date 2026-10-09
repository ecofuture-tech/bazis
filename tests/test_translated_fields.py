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
Reference data translated into the languages of the project: a `TranslatedField` of
django-translated-fields (a column per language) is one attribute of the API, in the
language of the request, and the filter, the sorting and the search use its column of
that language. They could not reach it: the attribute was not a field to filter or sort by.
"""

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Category


CATEGORIES = '/api/v1/catalog/category/'
LANGUAGES = [('en', 'English'), ('ru', 'Русский')]


@pytest.fixture
def two_languages(monkeypatch):
    # not the fixture `settings`: see tests/test_request_language.py
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGES', LANGUAGES)
    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'en')


@pytest.fixture
def categories(db):
    return {
        'apple': Category.objects.create(name_en='Apple', name_ru='Яблоко'),
        'pear': Category.objects.create(name_en='Pear', name_ru='Груша'),
        # not translated: the first language of the field is the fallback
        'plum': Category.objects.create(name_en='Plum'),
    }


def names(app, query='', lang='en'):
    response = get_api_client(app).get(f'{CATEGORIES}?lang={lang}{query}')
    assert response.status_code == 200, response.text
    return [it['attributes']['name'] for it in response.json()['data']]


@pytest.mark.django_db(transaction=True)
def test_value_in_the_language_of_the_request(sample_app, two_languages, categories):
    assert names(sample_app, '&sort=id') == ['Apple', 'Pear', 'Plum']
    assert names(sample_app, '&sort=id', lang='ru') == ['Яблоко', 'Груша', 'Plum']


@pytest.mark.django_db(transaction=True)
def test_schema_of_a_translated_field(sample_app, two_languages):
    response = get_api_client(sample_app).get(f'{CATEGORIES}schema_list/')
    assert response.status_code == 200, response.text
    schema = response.text
    # one attribute that filters and sorts, not the columns of the languages
    assert '"filterLabel":"name"' in schema.replace(' ', '')
    assert '"orderLabel":"name"' in schema.replace(' ', '')
    assert 'name_ru' not in schema

    response = get_api_client(sample_app).get(f'{CATEGORIES}route_filter_fields/')
    assert response.status_code == 200, response.text
    assert {'name': 'name', 'py_type': 'string'} in response.json()['fields']


@pytest.mark.django_db(transaction=True)
def test_sort_in_the_language_of_the_request(sample_app, two_languages, categories):
    assert names(sample_app, '&sort=name') == ['Apple', 'Pear', 'Plum']
    assert names(sample_app, '&sort=-name') == ['Plum', 'Pear', 'Apple']
    # by the column of the language: a value not translated sorts as empty
    assert names(sample_app, '&sort=name', lang='ru') == ['Plum', 'Груша', 'Яблоко']


@pytest.mark.django_db(transaction=True)
def test_filter_in_the_language_of_the_request(sample_app, two_languages, categories):
    assert names(sample_app, '&filter=name=Pear') == ['Pear']
    assert names(sample_app, '&filter=name=Груша', lang='ru') == ['Груша']
    assert names(sample_app, '&filter=name=Pear', lang='ru') == []
    assert names(sample_app, '&filter=name__istartswith=Я', lang='ru') == ['Яблоко']


@pytest.mark.django_db(transaction=True)
def test_search_in_the_language_of_the_request(sample_app, two_languages, categories):
    assert names(sample_app, '&search=ear') == ['Pear']
    assert names(sample_app, '&search=руш', lang='ru') == ['Груша']
    assert names(sample_app, '&search=ear', lang='ru') == []


@pytest.mark.django_db(transaction=True)
def test_write_the_columns_of_the_languages(sample_app, two_languages, categories):
    """The attribute is read-only (ignored); a route that adds the columns writes them."""
    pear = categories['pear']
    document = {
        'data': {
            'type': 'catalog.category',
            'id': pear.pk,
            'attributes': {'name': 'ignored', 'name_ru': 'Груши'},
        }
    }

    response = get_api_client(sample_app).patch(
        f'{CATEGORIES}{pear.pk}/?lang=ru', json_data=document
    )

    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['name'] == 'Груши'
    pear.refresh_from_db()
    assert (pear.name_en, pear.name_ru) == ('Pear', 'Груши')
