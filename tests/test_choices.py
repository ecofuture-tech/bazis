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
A create and an update accept only the choices of a field that has them: the values of the
`enum` of the OpenAPI (static, callable and grouped choices, the elements of an array field,
the field of every language of a translated one), as sent or as the type of the field
converts it.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, ValidationError, create_model

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Category, Memo, Tone

from bazis.core.schemas.builders import SchemaResourceBuilder


MEMOS = '/api/v1/catalog/memo/'
CATEGORIES = '/api/v1/catalog/category/'
PARENTS = '/api/v1/entity/parent_entity/'


def document(type_, item=None, **attributes):
    data = {'type': type_, 'attributes': attributes}
    if item is not None:
        data['id'] = str(item.pk)
    return {'data': data}


def memo_document(memo=None, **attributes):
    return document('catalog.memo', memo, **{'title': 'Memo', **attributes})


def openapi_enums(app, field):
    """The `enum` of the field in the schemas of the memos in the OpenAPI."""
    return {
        tuple(props[field]['enum'])
        for name, schema in app.openapi()['components']['schemas'].items()
        if 'catalog' in name.lower() and 'memo' in name.lower()
        for props in [schema.get('properties', {})]
        if field in props and 'enum' in props[field]
    }


def refused(response, pointer):
    assert response.status_code == 422, response.text
    errors = response.json()['errors']
    assert [(e['code'], e['source']['pointer']) for e in errors] == [('ERR_VALIDATE', pointer)]
    assert 'valid choice' in errors[0]['detail']


@pytest.mark.django_db(transaction=True)
def test_create_refuses_a_value_out_of_the_choices(sample_app):
    response = get_api_client(sample_app).post(MEMOS, json_data=memo_document(status='lost'))

    refused(response, '/data/attributes/status')
    assert not Memo.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_create_accepts_the_choices_and_their_default(sample_app):
    client = get_api_client(sample_app)

    response = client.post(MEMOS, json_data=memo_document(status='sent'))
    assert response.status_code == 201, response.text
    assert response.json()['data']['attributes']['status'] == 'sent'

    response = client.post(MEMOS, json_data=memo_document())
    assert response.status_code == 201, response.text
    assert response.json()['data']['attributes']['status'] == 'draft'


@pytest.mark.django_db(transaction=True)
def test_update_refuses_a_value_out_of_the_choices(sample_app):
    memo = Memo.objects.create(title='Memo')
    client = get_api_client(sample_app)

    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, status='lost'))
    refused(response, '/data/attributes/status')
    memo.refresh_from_db()
    assert memo.status == 'draft'

    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, status='sent'))
    assert response.status_code == 200, response.text
    memo.refresh_from_db()
    assert memo.status == 'sent'


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('kind', ['task', 'meeting', 'idea'])
def test_callable_grouped_choices_accept_the_values_of_the_groups(sample_app, kind):
    response = get_api_client(sample_app).post(MEMOS, json_data=memo_document(kind=kind))

    assert response.status_code == 201, response.text
    assert Memo.objects.get().kind == kind


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('kind', ['Work', 'work', 'Idea'])
def test_callable_grouped_choices_refuse_the_labels_of_the_groups(sample_app, kind):
    response = get_api_client(sample_app).post(MEMOS, json_data=memo_document(kind=kind))

    refused(response, '/data/attributes/kind')


@pytest.mark.django_db(transaction=True)
def test_null_and_blank_are_left_to_the_null_and_blank_checks(sample_app):
    client = get_api_client(sample_app)

    # null and blank are allowed by the field: they need not be among the choices
    response = client.post(MEMOS, json_data=memo_document(kind=None))
    assert response.status_code == 201, response.text
    response = client.post(MEMOS, json_data=memo_document(kind=''))
    assert response.status_code == 201, response.text

    # not blank: the error is the one of the blank value, once
    response = client.post(MEMOS, json_data=memo_document(status=''))
    assert response.status_code == 422, response.text
    errors = response.json()['errors']
    assert [(e['source']['pointer'], e['detail']) for e in errors] == [
        ('/data/attributes/status', "Value error, Can't be blank")
    ]

    # not null
    response = client.post(MEMOS, json_data=memo_document(status=None))
    assert response.status_code == 422, response.text
    assert 'valid choice' not in response.text


@pytest.mark.django_db(transaction=True)
def test_integer_choices(sample_app):
    client = get_api_client(sample_app)

    response = client.post(MEMOS, json_data=memo_document(mood=3))
    refused(response, '/data/attributes/mood')

    # as the type converts it: a number as a string, as in 2.18
    response = client.post(MEMOS, json_data=memo_document(mood='2'))
    assert response.status_code == 201, response.text
    assert Memo.objects.get().mood == 2
    response = client.post(MEMOS, json_data=memo_document(mood='3'))
    refused(response, '/data/attributes/mood')

    response = client.post(MEMOS, json_data=memo_document(mood=2))
    assert response.status_code == 201, response.text
    response = client.post(MEMOS, json_data=memo_document(mood=None))
    assert response.status_code == 201, response.text


@pytest.mark.django_db(transaction=True)
def test_a_type_that_makes_an_object_of_the_code_accepts_the_codes(sample_app):
    # the schema type of the field (`Tone`) makes an object of the code: the choices are
    # checked on the code that the request sends
    client = get_api_client(sample_app)

    response = client.post(MEMOS, json_data=memo_document(tone='warm'))
    assert response.status_code == 201, response.text
    assert response.json()['data']['attributes']['tone'] == 'warm'
    memo = Memo.objects.get()
    assert memo.tone is Tone.WARM

    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, tone='cold'))
    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['tone'] == 'cold'
    memo.refresh_from_db()
    assert memo.tone is Tone.COLD


@pytest.mark.django_db(transaction=True)
def test_a_type_that_makes_an_object_of_the_code_refuses_other_values(sample_app):
    client = get_api_client(sample_app)

    response = client.post(MEMOS, json_data=memo_document(tone='hot'))
    refused(response, '/data/attributes/tone')
    assert not Memo.objects.exists()

    memo = Memo.objects.create(title='Memo', tone=Tone.WARM)
    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, tone='hot'))
    refused(response, '/data/attributes/tone')
    memo.refresh_from_db()
    assert memo.tone is Tone.WARM


KEYS = {
    'rate': [Decimal('0.10'), Decimal('0.50')],
    'due': [date(2026, 1, 1), date(2026, 7, 1)],
    'ticket': [
        UUID('8a6e0804-2bd0-4672-b79d-d97027f9071a'),
        UUID('0f3b2c1d-58e4-4b7a-9c2e-6d1f0a9b8c7e'),
    ],
}


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'field, other',
    [('rate', '0.20'), ('due', '2026-02-01'), ('ticket', 'a3c1e7f0-5b2d-4e8a-9f61-2b7c0d4e5a19')],
)
def test_choices_whose_keys_are_not_json_values(sample_app, field, other):
    # the request sends the keys as the OpenAPI shows them: the type of the field converts
    # them to the keys of the choices
    ((first, second),) = openapi_enums(sample_app, field)
    client = get_api_client(sample_app)

    response = client.post(MEMOS, json_data=memo_document(**{field: first}))
    assert response.status_code == 201, response.text
    memo = Memo.objects.get()
    assert getattr(memo, field) == KEYS[field][0]

    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, **{field: second}))
    assert response.status_code == 200, response.text
    memo.refresh_from_db()
    assert getattr(memo, field) == KEYS[field][1]

    response = client.post(MEMOS, json_data=memo_document(**{field: other}))
    refused(response, f'/data/attributes/{field}')
    response = client.patch(f'{MEMOS}{memo.pk}/', json_data=memo_document(memo, **{field: other}))
    refused(response, f'/data/attributes/{field}')
    memo.refresh_from_db()
    assert getattr(memo, field) == KEYS[field][1]


def test_keys_converted_by_the_type_of_the_field():
    # keys of another type than the field (strings of a decimal field): the value converted
    # by the type is compared with the keys converted by it
    choices = {'enum': ['0.10', '0.50']}
    schema = create_model(
        'Rates',
        __validators__=SchemaResourceBuilder._value_validators(is_response_schema=False),
        rate=(Decimal | None, Field(None, json_schema_extra=choices)),
        rates=(list[Decimal], Field([], json_schema_extra=choices)),
    )

    assert schema(rate=0.1).rate == Decimal('0.1')
    assert schema(rates=[0.5, '0.10']).rates == [Decimal('0.5'), Decimal('0.10')]
    # one error, of the choices, also for a value the type refuses
    for values, value in (({'rate': 0.2}, 0.2), ({'rates': [0.5, 0.2]}, 0.2), ({'rate': 'x'}, 'x')):
        with pytest.raises(ValidationError) as error:
            schema(**values)
        assert [it['msg'] for it in error.value.errors()] == [
            f'Value error, Value {value!r} is not a valid choice'
        ]


@pytest.mark.django_db(transaction=True)
def test_every_element_of_an_array_field_is_a_choice(sample_app):
    client = get_api_client(sample_app)
    body = {'name': 'Parent', 'state': 'state_one'}

    response = client.post(
        PARENTS, json_data=document('entity.parent_entity', field=['first_field', 'nope'], **body)
    )
    refused(response, '/data/attributes/field')

    for elements in (['first_field', ''], [None], ['first_field', None]):
        response = client.post(
            PARENTS, json_data=document('entity.parent_entity', field=elements, **body)
        )
        refused(response, '/data/attributes/field')

    response = client.post(
        PARENTS,
        json_data=document('entity.parent_entity', field=['first_field', 'third_field'], **body),
    )
    assert response.status_code == 201, response.text
    response = client.post(
        PARENTS, json_data=document('entity.parent_entity', field=[], state='state_one', name='P')
    )
    assert response.status_code == 201, response.text


@pytest.mark.django_db(transaction=True)
def test_the_column_of_every_language_checks_the_choices(sample_app):
    category = Category.objects.create(name_en='Cat')
    client = get_api_client(sample_app)

    for column in ('scope_en', 'scope_ru'):
        response = client.patch(
            f'{CATEGORIES}{category.pk}/',
            json_data=document('catalog.category', category, **{column: 'x'}),
        )
        refused(response, f'/data/attributes/{column}')

    response = client.patch(
        f'{CATEGORIES}{category.pk}/',
        json_data=document('catalog.category', category, scope_ru='sent', scope_en=''),
    )
    assert response.status_code == 200, response.text
    category.refresh_from_db()
    assert (category.scope_en, category.scope_ru) == ('', 'sent')


@pytest.mark.django_db(transaction=True)
def test_the_openapi_enum_is_what_the_write_accepts(sample_app):
    assert openapi_enums(sample_app, 'status') == {('draft', 'sent')}
    # the values of the groups, not the pairs
    assert openapi_enums(sample_app, 'kind') == {('task', 'meeting', 'idea')}
    assert openapi_enums(sample_app, 'mood') == {(1, 2)}
    # the codes, not the objects of the schema type
    assert openapi_enums(sample_app, 'tone') == {('warm', 'cold')}
    # the keys that are not JSON values, as JSON
    assert openapi_enums(sample_app, 'rate') == {('0.10', '0.50')}
    assert openapi_enums(sample_app, 'due') == {('2026-01-01', '2026-07-01')}
    assert openapi_enums(sample_app, 'ticket') == {tuple(str(key) for key in KEYS['ticket'])}


@pytest.mark.django_db(transaction=True)
def test_a_database_value_out_of_the_choices_is_still_read(sample_app):
    # the choices are checked on a write only: a response shows what the database holds
    memo = Memo.objects.create(title='Old')
    Memo.objects.filter(pk=memo.pk).update(status='archived')

    response = get_api_client(sample_app).get(f'{MEMOS}{memo.pk}/')
    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['status'] == 'archived'
