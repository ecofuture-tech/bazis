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
A `URLField` (sample `catalog.Attachment.url`) accepts on the API a URL of the schemes of its
`URLValidator` (http, https, ftp, ftps by default) within its `max_length`, or an empty
string; its JSON schema is a flat `anyOf` of a `string`/`uri` and an empty `string`.
"""

from django.core.exceptions import ImproperlyConfigured
from django.core.validators import URLValidator
from django.db import models

from pydantic import TypeAdapter, ValidationError

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Attachment

from bazis.core.utils.django_types import url_field_type


URL = '/api/v1/catalog/attachment/'


def create(client, **attributes):
    return client.post(
        URL,
        json_data={'data': {'type': 'catalog.attachment', 'attributes': {'name': 'A'} | attributes}},
    )


@pytest.mark.django_db(transaction=True)
def test_the_schema_is_flat(sample_app):
    client = get_api_client(sample_app)
    for action in ('schema_create', 'schema_list'):
        schema = client.get(f'{URL}{action}/').json()
        (url,) = [
            props['url']
            for it in schema['$defs'].values()
            if 'url' in (props := it.get('properties', {}))
        ]
        assert url['anyOf'] == [
            {'type': 'string', 'format': 'uri', 'minLength': 1, 'maxLength': 200},
            {'type': 'string', 'maxLength': 0},
        ], action
        assert 'maxLength' not in url


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'value',
    [
        'javascript:alert(1)',
        'data:text/html,<script>alert(1)</script>',
        'file:///etc/passwd',
        'example.com',
        ' ',
        # 200 characters, 201 once normalized (the trailing slash): too long for the column
        'https://' + 'a' * 188 + '.com',
        'https://' + 'a' * 189 + '.com/',
    ],
)
def test_refused(sample_app, value):
    response = create(get_api_client(sample_app), url=value)
    assert response.status_code == 422, response.text
    assert {
        (it['code'], it['source']['pointer']) for it in response.json()['errors']
    } == {('ERR_VALIDATE', '/data/attributes/url')}
    assert not Attachment.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_accepted(sample_app):
    """
    A URL of an allowed scheme is stored normalized (pydantic adds the trailing slash of an
    empty path, lowers the scheme and the host); an empty string and a missing value are
    stored empty.
    """
    client = get_api_client(sample_app)
    cases = [
        ({'url': 'https://example.com'}, 'https://example.com/'),
        ({'url': 'HTTP://Example.com/a?b=1'}, 'http://example.com/a?b=1'),
        ({'url': 'ftp://files.example.com/x.pdf'}, 'ftp://files.example.com/x.pdf'),
        ({'url': ''}, ''),
        ({}, ''),
    ]
    for attributes, stored in cases:
        response = create(client, **attributes)
        assert response.status_code == 201, response.text
        assert response.json()['data']['attributes']['url'] == stored
        assert Attachment.objects.get(pk=response.json()['data']['id']).url == stored

    item = Attachment.objects.get(url='https://example.com/')
    response = client.patch(
        f'{URL}{item.pk}/',
        json_data={
            'data': {'id': str(item.pk), 'type': 'catalog.attachment', 'attributes': {'url': 'javascript:x'}}
        },
    )
    assert response.status_code == 422, response.text
    item.refresh_from_db()
    assert item.url == 'https://example.com/'


@pytest.mark.django_db(transaction=True)
def test_a_stored_value_is_read_as_it_is(sample_app):
    """
    A value the API did not check (written by a script, or before bazis 2.16) is read as it
    is, in the item and in the list: a read never fails on it.
    """
    item = Attachment.objects.create(name='Old', url='www.example.com')
    client = get_api_client(sample_app)
    response = client.get(f'{URL}{item.pk}/')
    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['url'] == 'www.example.com'
    response = client.get(URL)
    assert response.status_code == 200, response.text
    assert [it['attributes']['url'] for it in response.json()['data']] == ['www.example.com']


@pytest.mark.django_db(transaction=True)
def test_the_openapi_of_a_response(sample_app):
    """The responses have the flat schema of the requests."""
    schemas = sample_app.openapi()['components']['schemas']
    found = [
        props['url']
        for name, it in schemas.items()
        if 'catalog__attachment' in name and 'url' in (props := it.get('properties', {}))
    ]
    assert found
    for url in found:
        assert url['anyOf'][:2] == [
            {'type': 'string', 'format': 'uri', 'minLength': 1, 'maxLength': 200},
            {'type': 'string', 'maxLength': 0},
        ], url


def test_the_schemes_of_the_field():
    """
    The schemes are those all the URL validators of the field allow, the length its
    max_length; a nullable field adds null itself (not the type).
    """
    field = models.URLField(max_length=30, validators=[URLValidator(schemes=['https', 'ftp'])])
    adapter = TypeAdapter(url_field_type(field))
    assert str(adapter.validate_python('https://example.com')) == 'https://example.com/'
    for value in ('http://example.com', 'ftps://example.com', 'https://example.com/' + 'a' * 20):
        with pytest.raises(ValidationError):
            adapter.validate_python(value)
    with pytest.raises(ValidationError):
        adapter.validate_python(None)
    assert TypeAdapter(url_field_type(field) | None).json_schema()['anyOf'] == [
        {'type': 'string', 'format': 'uri', 'minLength': 1, 'maxLength': 30},
        {'type': 'string', 'maxLength': 0},
        {'type': 'null'},
    ]


def test_no_scheme_in_common():
    """
    `validators=` narrows the schemes of the default validator: a scheme it does not allow
    is an error of the configuration, which names the field (a subclass of URLField with
    its own `default_validators` allows other schemes).
    """
    field = models.URLField(validators=[URLValidator(schemes=['mailto'])])
    field.set_attributes_from_name('contact')
    field.model = Attachment
    with pytest.raises(ImproperlyConfigured, match=r'catalog\.Attachment\.contact: .*no scheme'):
        url_field_type(field)

    class MailtoURLField(models.URLField):
        default_validators = [URLValidator(schemes=['mailto', 'https'])]

    adapter = TypeAdapter(url_field_type(MailtoURLField()))
    assert str(adapter.validate_python('mailto:a@example.com')) == 'mailto:a@example.com'

