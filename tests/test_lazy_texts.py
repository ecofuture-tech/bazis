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
Lazy texts (`gettext_lazy`) in the models of a project: the OpenAPI and the JSON schemas
of `TranslatedJsonSchema` write them in the language active when they are generated.
"""

from django.utils import translation
from django.utils.translation import gettext_lazy as _

from fastapi import FastAPI, Query

from pydantic import BaseModel, Field
from pydantic.json_schema import models_json_schema

import pytest

from bazis.core.utils.schemas import TranslatedJsonSchema, TranslatedSchemaModel


# msgids of the catalog of the core
TEXTS = {
    'en': ('Creation time', 'Access denied', 'Item not found'),
    'ru': ('Время добавления', 'Доступ запрещён', 'Объект не найден'),
}


@pytest.fixture
def two_languages(monkeypatch):
    # not the fixture `settings`: see test_request_language
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'en')


class Visit(BaseModel):
    """
    A request model of a project with lazy texts. Lazy examples go in `json_schema_extra`:
    pydantic serializes `Field(examples=...)` when it defines the model.
    """

    dt: str = Field(
        title=_('Creation time'),
        description=_('Access denied'),
        json_schema_extra={
            'examples': [_('Item not found')],
            'enumDict': {'denied': _('Access denied')},
        },
    )


class VisitResult(BaseModel):
    found: bool = Field(title=_('Item not found'))


class VisitSchema(Visit, TranslatedSchemaModel):
    pass


def visit_texts(schema: dict) -> tuple[str, ...]:
    dt = schema['properties']['dt']
    assert dt['examples'] == [dt['examples'][0]]
    assert dt['enumDict'] == {'denied': dt['description']}
    return dt['title'], dt['description'], dt['examples'][0]


@pytest.mark.parametrize('language', ['en', 'ru'])
def test_openapi_with_lazy_texts(two_languages, language):
    """
    The OpenAPI of a route whose request and response models, parameters and operation
    have lazy texts is a JSON document in the active language (FastAPI refused it: a lazy
    title is not a string).
    """
    app = FastAPI()

    @app.post('/visits/', response_model=VisitResult, summary=_('Creation time'))
    def visit(body: Visit, query: str = Query('', description=_('Access denied'))):
        return VisitResult(found=True)

    created, denied, not_found = TEXTS[language]
    with translation.override(language):
        openapi = app.openapi()

    schemas = openapi['components']['schemas']
    assert visit_texts(schemas['Visit']) == TEXTS[language]
    assert schemas['VisitResult']['properties']['found']['title'] == not_found
    operation = openapi['paths']['/visits/']['post']
    assert operation['summary'] == created
    assert operation['parameters'][0]['description'] == denied


@pytest.mark.parametrize('language', ['en', 'ru'])
def test_json_schema_with_lazy_texts(two_languages, language):
    """
    `TranslatedSchemaModel.model_json_schema()` and the generator `TranslatedJsonSchema`
    (one schema, or the definitions of several models) write the lazy texts in the active
    language; the model keeps them lazy for the next generation.
    """
    with translation.override(language):
        assert visit_texts(VisitSchema.model_json_schema()) == TEXTS[language]
        assert (
            visit_texts(Visit.model_json_schema(schema_generator=TranslatedJsonSchema))
            == TEXTS[language]
        )
        _, definitions = models_json_schema(
            [(Visit, 'validation'), (VisitResult, 'serialization')],
            schema_generator=TranslatedJsonSchema,
        )
    assert visit_texts(definitions['$defs']['Visit']) == TEXTS[language]
    assert definitions['$defs']['VisitResult']['properties']['found']['title'] == TEXTS[language][2]
