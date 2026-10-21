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
The labels of the Django choices (`enumDict`) in the OpenAPI schemas of the pydantic models,
e.g. the body of an action: the same key the schemas of the model fields carry.
"""

import enum
from typing import Literal

from django.db import models
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from fastapi import FastAPI

from pydantic import BaseModel

import pytest


class WorkType(models.TextChoices):
    PLUMBING = 'plumbing', _('Creation time')
    REPAIR = 'repair', _('Access denied')


class Priority(models.IntegerChoices):
    LOW = 1, _('Creation time')
    HIGH = 2, _('Access denied')


class Plain(enum.Enum):
    A = 'a'
    B = 'b'


class Inner(BaseModel):
    kind: WorkType


class Body(BaseModel):
    work_type: WorkType
    priority: Priority
    maybe: WorkType | None = None
    many: list[WorkType] = []
    inner: Inner | None = None
    literal: Literal['plumbing', 'repair'] = 'plumbing'
    plain: Plain = Plain.A


@pytest.fixture
def two_languages(monkeypatch):
    # not the fixture `settings`: see test_request_language
    from django.conf import settings

    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    monkeypatch.setattr(settings, 'LANGUAGE_CODE', 'en')


def openapi(language: str = 'en') -> dict:
    app = FastAPI()

    @app.post('/work/')
    def work(body: Body) -> dict:
        return {}

    with translation.override(language):
        return app.openapi()['components']['schemas']


def test_choices_have_labels_in_the_order_of_the_choices():
    schemas = openapi()
    assert schemas['WorkType'] == {
        'enum': ['plumbing', 'repair'],
        'title': 'WorkType',
        'type': 'string',
        'enumDict': {'plumbing': 'Creation time', 'repair': 'Access denied'},
    }
    assert list(schemas['WorkType']['enumDict']) == ['plumbing', 'repair']
    assert schemas['Priority']['enum'] == [1, 2]
    # the keys of a JSON object are strings, as in the schemas of the model fields
    # the keys of a JSON object are strings, as in the schemas of the model fields
    assert schemas['Priority']['enumDict'] == {'1': 'Creation time', '2': 'Access denied'}


def test_labels_are_in_the_active_language(two_languages):
    assert openapi('ru')['WorkType']['enumDict'] == {
        'plumbing': 'Время добавления',
        'repair': 'Доступ запрещён',
    }
    assert openapi('en')['WorkType']['enumDict']['plumbing'] == 'Creation time'
    assert openapi('ru')['Priority']['enumDict']['2'] == 'Доступ запрещён'


def test_choices_in_optional_list_and_nested_models():
    schemas = openapi()
    props = schemas['Body']['properties']
    assert props['work_type'] == {'$ref': '#/components/schemas/WorkType'}
    assert props['maybe']['anyOf'][0] == {'$ref': '#/components/schemas/WorkType'}
    assert props['many']['items'] == {'$ref': '#/components/schemas/WorkType'}
    assert schemas['Inner']['properties']['kind'] == {'$ref': '#/components/schemas/WorkType'}
    assert set(schemas['WorkType']['enumDict']) == {'plumbing', 'repair'}


def test_literal_and_plain_enum_have_no_labels():
    schemas = openapi()
    assert schemas['Body']['properties']['literal'] == {
        'type': 'string',
        'enum': ['plumbing', 'repair'],
        'default': 'plumbing',
        'title': 'Literal',
    }
    assert 'enumDict' not in schemas['Plain']
    assert schemas['Plain']['enum'] == ['a', 'b']
