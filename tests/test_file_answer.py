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
A route that answers a file with its meta (bazis 2.25): `file_meta` of the decorator
declares the header `X-Bazis-Meta` in the OpenAPI, `file_answer` sends the file, its name
and the meta, and CORS shows both headers to a client of another origin.
"""

import enum
import json

from django.utils import translation
from django.utils.translation import gettext_lazy as _

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from pydantic import BaseModel, Field, computed_field

import pytest
from catalog.models import Memo

from bazis.core.routes_abstract.initial import (
    FILE_META_HEADER,
    FILE_META_MAX,
    InitialRouteBase,
    file_answer,
    http_get,
    http_post,
)


MEMOS = '/api/v1/catalog/memo/'


class Meta(BaseModel):
    count: int
    title: str = Field('', title=_('Creation time'))


class CsvResponse(Response):
    media_type = 'text/csv'


class FileRouteSet(InitialRouteBase):
    @http_post('/export/', response_class=CsvResponse, file_meta=Meta)
    def action_export(self, **kwargs):
        return file_answer('a', 'a.csv', CsvResponse.media_type, Meta(count=1))

    @http_post(
        '/created/',
        status_code=201,
        response_class=CsvResponse,
        file_meta=Meta,
        responses={
            201: {'description': 'The file', 'headers': {FILE_META_HEADER: {'description': 'Own'}}}
        },
    )
    def action_created(self, **kwargs):
        pass

    @http_get('/plain/', response_class=CsvResponse)
    def action_plain(self, **kwargs):
        pass


class InheritedRouteSet(FileRouteSet):
    pass


def operations(route_cls: type[InitialRouteBase], language: str = 'en') -> dict:
    app = FastAPI()
    app.include_router(route_cls.as_router())
    with translation.override(language):
        paths = app.openapi()['paths']
    return {path: next(iter(item.values())) for path, item in paths.items()}


def test_file_meta_declares_the_header():
    """
    The header of the meta with the schema of the model, in the answer of the status of the
    route; a route without `file_meta` declares no header.
    """
    found = operations(FileRouteSet)
    answer = found['/export/']['responses']['200']
    assert answer['content'] == {'text/csv': {'schema': {'type': 'string'}}}
    header = answer['headers'][FILE_META_HEADER]
    assert header['schema']['properties']['count'] == {'title': 'Count', 'type': 'integer'}
    assert header['schema']['required'] == ['count']
    assert 'headers' not in found['/plain/']['responses']['200']
    # an inherited route keeps it
    assert operations(InheritedRouteSet)['/export/']['responses']['200'] == answer


def test_declared_responses_win():
    """`responses` of the route are merged over the header, at the status of the route."""
    answer = operations(FileRouteSet)['/created/']['responses']['201']
    assert answer['description'] == 'The file'
    header = answer['headers'][FILE_META_HEADER]
    assert header['description'] == 'Own'
    assert header['schema']['title'] == 'Meta'


def test_lazy_title_in_the_language_of_the_document(monkeypatch):
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'en')

    def title(language):
        answer = operations(FileRouteSet, language)['/export/']['responses']['200']
        return answer['headers'][FILE_META_HEADER]['schema']['properties']['title']['title']

    assert title('ru') == 'Время добавления'
    assert title('en') == 'Creation time'


def test_file_answer():
    """
    The name of the file, also not ASCII (`filename*`); the meta as JSON in ASCII; no header
    without a meta; a meta longer than the limit is refused.
    """
    response = file_answer(
        b'\x00\x01', 'отчёт.xlsx', 'application/octet-stream', Meta(count=2, title='Март')
    )
    assert response.body == b'\x00\x01'
    assert response.media_type == 'application/octet-stream'
    assert response.headers['Content-Disposition'] == (
        "attachment; filename*=utf-8''%D0%BE%D1%82%D1%87%D1%91%D1%82.xlsx"
    )
    value = response.headers[FILE_META_HEADER]
    assert value.isascii()
    assert json.loads(value) == {'count': 2, 'title': 'Март'}

    response = file_answer('a;b', 'memos.csv', 'text/csv')
    assert response.headers['Content-Disposition'] == 'attachment; filename="memos.csv"'
    assert FILE_META_HEADER not in response.headers

    with pytest.raises(ValueError):
        file_answer('', 'a.csv', 'text/csv', Meta(count=1, title='x' * FILE_META_MAX))


class Totals(BaseModel):
    count: int
    pages: int

    @computed_field
    @property
    def label(self) -> str:
        return f'{self.count} rows'


def test_the_schema_is_the_meta_as_sent():
    """
    The schema of the header describes the JSON `file_answer` sends (`model_dump(mode='json')`):
    a computed field is in it.
    """

    class TotalsRouteSet(InitialRouteBase):
        @http_post('/totals/', response_class=CsvResponse, file_meta=Totals)
        def action_totals(self, **kwargs):
            pass

    answer = operations(TotalsRouteSet)['/totals/']['responses']['200']
    schema = answer['headers'][FILE_META_HEADER]['schema']
    assert set(schema['properties']) == {'count', 'pages', 'label'}
    response = file_answer('', 'a.csv', 'text/csv', Totals(count=2, pages=1))
    sent = json.loads(response.headers[FILE_META_HEADER])
    assert set(sent) == set(schema['properties'])


class Kind(enum.Enum):
    A = 'a'


class WithEnum(BaseModel):
    kind: Kind


class WithModel(BaseModel):
    totals: Totals


@pytest.mark.parametrize('model', [WithEnum, WithModel])
def test_a_meta_that_is_not_flat_is_refused(model):
    """
    An enum or a nested model is a reference (`#/$defs/...`) the OpenAPI cannot resolve: the
    decorator refuses the model, naming it.
    """
    with pytest.raises(ValueError, match=model.__name__):
        http_post('/x/', response_class=CsvResponse, file_meta=model)


def test_the_limit_of_the_meta():
    """The JSON of the meta of `FILE_META_MAX` characters is sent, one more is refused."""
    empty = len(json.dumps({'count': 1, 'title': ''}, separators=(',', ':')))
    fits = Meta(count=1, title='x' * (FILE_META_MAX - empty))
    value = file_answer('', 'a.csv', 'text/csv', fits).headers[FILE_META_HEADER]
    assert len(value) == FILE_META_MAX
    with pytest.raises(ValueError):
        file_answer('', 'a.csv', 'text/csv', Meta(count=1, title='x' * (FILE_META_MAX - empty + 1)))


def test_a_file_name_cannot_add_a_header():
    """Control characters (CR, LF) of a name are percent-encoded in `filename*`."""
    response = file_answer('', 'a\r\nX-Evil: 1.csv', 'text/csv')
    assert response.headers['Content-Disposition'] == (
        "attachment; filename*=utf-8''a%0D%0AX-Evil%3A%201.csv"
    )
    assert 'X-Evil' not in response.headers
    assert all(b'\r' not in value and b'\n' not in value for _, value in response.raw_headers)


@pytest.mark.django_db(transaction=True)
def test_export_answers_the_file_and_its_meta(sample_app):
    """
    The action of the sample answers the file and its meta; a client of another origin may
    read both headers (`Access-Control-Expose-Headers`).
    """
    Memo.objects.create(title='B')
    Memo.objects.create(title='A')

    client = TestClient(sample_app)
    response = client.post(f'{MEMOS}export/', headers={'Origin': 'https://front.example'})
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('text/csv')
    assert response.text == 'A\nB'
    assert response.headers['content-disposition'] == 'attachment; filename="memos.csv"'
    assert json.loads(response.headers[FILE_META_HEADER]) == {'count': 2}
    exposed = {
        it.strip().lower() for it in response.headers['access-control-expose-headers'].split(',')
    }
    assert {'content-disposition', FILE_META_HEADER.lower()} <= exposed

    operation = sample_app.openapi()['paths'][f'{MEMOS}export/']['post']
    assert FILE_META_HEADER in operation['responses']['200']['headers']
