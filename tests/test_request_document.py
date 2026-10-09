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
What a request may name: a write gives only the fields of the schema of the route, a text
the forms of Django require (`blank=False`) is not blank, and `include` names only the
relations the route can include. They were left out (or written) without an error.
"""

from django.conf import settings

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Card, Memo


MEMOS = '/api/v1/catalog/memo/'


def memo_document(memo=None, **attributes):
    data = {'type': 'catalog.memo', 'attributes': attributes}
    if memo is not None:
        data['id'] = memo.pk
    return {'data': data}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    errors = response.json()['errors']
    assert len(errors) == 1, errors
    assert errors[0]['code'] == code, errors
    return errors[0]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('title', ['', '   ', '\n\t'])
def test_create_refuses_a_blank_required_text(sample_app, title):
    response = get_api_client(sample_app).post(MEMOS, json_data=memo_document(title=title))

    error = error_of(response, 422, 'ERR_VALIDATE')
    assert error['source']['pointer'] == '/data/attributes/title'
    assert not Memo.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_blank_text_where_the_model_allows_it(sample_app):
    client = get_api_client(sample_app)
    # a blank body (blank=True); the title is kept as sent, not stripped
    response = client.post(MEMOS, json_data=memo_document(title=' memo ', body='', code=''))
    assert response.status_code == 201, response.text
    memo = Memo.objects.get()
    assert (memo.title, memo.body) == (' memo ', '')


@pytest.mark.django_db(transaction=True)
def test_update_refuses_a_blank_required_text(sample_app):
    memo = Memo.objects.create(title='memo')

    response = get_api_client(sample_app).patch(
        f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, title='  ')
    )

    error = error_of(response, 422, 'ERR_VALIDATE')
    assert error['source']['pointer'] == '/data/attributes/title'
    memo.refresh_from_db()
    assert memo.title == 'memo'


@pytest.mark.django_db(transaction=True)
def test_a_blank_text_in_the_database_is_answered(sample_app):
    """The responses show the values of the database: they are not checked."""
    memo = Memo.objects.create(title='')
    client = get_api_client(sample_app)

    response = client.get(f'{MEMOS}{memo.pk}/')
    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['title'] == ''

    # an update that does not send the title
    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo))
    assert response.status_code == 200, response.text


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('name', ['code', 'unknown', 'cards_count'])
def test_update_refuses_an_attribute_out_of_the_schema(sample_app, name):
    """
    `code` is excluded from the update schema of the route, `unknown` is not a field,
    `cards_count` is a calculated field (read-only, in the schema: see below).
    """
    memo = Memo.objects.create(title='memo', code='A-1')

    response = get_api_client(sample_app).patch(
        f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, **{name: 'B-2'})
    )

    if name == 'cards_count':
        assert response.status_code == 200, response.text
        return
    error = error_of(response, 422, 'ERR_VALIDATE')
    assert error['source']['pointer'] == f'/data/attributes/{name}'
    assert error['title'] == 'extra_forbidden'
    memo.refresh_from_db()
    assert memo.code == 'A-1'


@pytest.mark.django_db(transaction=True)
def test_update_ignores_a_read_only_attribute(sample_app):
    memo = Memo.objects.create(title='memo', body='text')

    response = get_api_client(sample_app).patch(
        f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, title='new', body='changed')
    )

    assert response.status_code == 200, response.text
    memo.refresh_from_db()
    assert (memo.title, memo.body) == ('new', 'text')


@pytest.mark.django_db(transaction=True)
def test_create_refuses_a_relationship_out_of_the_schema(sample_app):
    document = memo_document(title='memo')
    document['data']['relationships'] = {'unknown': {'data': None}}

    response = get_api_client(sample_app).post(MEMOS, json_data=document)

    error = error_of(response, 422, 'ERR_VALIDATE')
    assert error['source']['pointer'] == '/data/relationships/unknown'
    assert not Memo.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_create_accepts_the_fields_of_the_schema(sample_app):
    document = memo_document(title='memo', code='A-1')
    document['data']['relationships'] = {'attachment': {'data': None}}

    response = get_api_client(sample_app).post(MEMOS, json_data=document)

    assert response.status_code == 201, response.text
    assert Memo.objects.get().code == 'A-1'


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('include', ['unknown', 'cards.attachment', 'cards,unknown', 'title'])
def test_include_of_a_relation_out_of_the_schema(sample_app, include):
    memo = Memo.objects.create(title='memo')

    response = get_api_client(sample_app).get(f'{MEMOS}{memo.pk}/?include={include}')

    error = error_of(response, 400, 'ERR_INCLUDE')
    assert error['source']['pointer'] == '/query/include'
    assert error['title'] == 'Invalid include'
    assert 'cards' not in error['detail'].split(': ', 1)[1].split(', ')


@pytest.mark.django_db(transaction=True)
def test_include_of_the_relations_of_the_schema(sample_app):
    memo = Memo.objects.create(title='memo')
    card = Card.objects.create(name='card', memo=memo)
    client = get_api_client(sample_app)

    response = client.get(f'{MEMOS}{memo.pk}/?include=cards,attachment')
    assert response.status_code == 200, response.text
    assert [(it['type'], str(it['id'])) for it in response.json()['included']] == [
        ('catalog.card', str(card.pk))
    ]

    # an update includes the relations of the update and of the create schema
    response = client.patch(
        f'{MEMOS}{memo.pk}/?include=cards', json_data=memo_document(memo, title='new')
    )
    assert response.status_code == 200, response.text


@pytest.mark.django_db(transaction=True)
def test_include_unchecked_without_strict_queries(sample_app, monkeypatch):
    """`BAZIS_FILTERS_STRICT=false` (transitional) leaves the unknown names out."""
    monkeypatch.setattr(settings, 'BAZIS_FILTERS_STRICT', False)
    memo = Memo.objects.create(title='memo')

    response = get_api_client(sample_app).get(f'{MEMOS}{memo.pk}/?include=unknown')

    assert response.status_code == 200, response.text
    assert 'included' not in response.json() or response.json()['included'] == []
