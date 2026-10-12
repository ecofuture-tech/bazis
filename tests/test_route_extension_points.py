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
The code around every route: the middlewares of `BAZIS_MIDDLEWARES` (generators of the
route, around its whole run) and the methods `<action>__before` / `<action>__after` of a
route set (inside the run, after `route_check`).
"""

from django.conf import settings

from fastapi import HTTPException
from fastapi.responses import JSONResponse

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Memo
from catalog.routes import MemoRouteSet


MEMOS = '/api/v1/catalog/memo/'
CALLS = []


def recording(route, *args, **kwargs):
    """A middleware that sees the route and its result."""
    CALLS.append(('middleware before', route.route_ctx.name))
    result = yield
    CALLS.append(('middleware after', result.status_code))
    result.headers['x-recorded'] = 'yes'


def result_type(route, *args, **kwargs):
    """A middleware that records the type of the result of the route."""
    result = yield
    CALLS.append(type(result).__name__)


def replacing(route, *args, **kwargs):
    """A middleware whose second value replaces the result."""
    yield
    yield JSONResponse({'replaced': route.route_ctx.name})


@pytest.fixture
def calls(monkeypatch):
    CALLS.clear()
    monkeypatch.setattr(
        MemoRouteSet,
        'action_retrieve__before',
        lambda self, *args, **kwargs: CALLS.append(('before', kwargs.get('item_id'))),
        raising=False,
    )
    monkeypatch.setattr(
        MemoRouteSet,
        'action_retrieve__after',
        lambda self, *args, **kwargs: CALLS.append(('after', kwargs.get('item_id'))),
        raising=False,
    )
    return CALLS


@pytest.mark.django_db(transaction=True)
def test_middleware_and_hooks_around_a_route(sample_app, calls, monkeypatch):
    monkeypatch.setattr(
        settings, 'BAZIS_MIDDLEWARES', ['tests.test_route_extension_points.recording']
    )
    memo = Memo.objects.create(title='Memo')

    response = get_api_client(sample_app).get(f'{MEMOS}{memo.pk}/')

    assert response.status_code == 200, response.text
    assert response.headers['x-recorded'] == 'yes'
    assert calls == [
        ('middleware before', 'action_retrieve'),
        ('before', memo.pk),
        ('after', memo.pk),
        ('middleware after', 200),
    ]
    # the hooks of an action run only around it
    calls.clear()
    assert get_api_client(sample_app).get(MEMOS).status_code == 200
    assert calls == [('middleware before', 'action_list'), ('middleware after', 200)]


@pytest.mark.django_db(transaction=True)
def test_middleware_replaces_the_result(sample_app, monkeypatch):
    monkeypatch.setattr(
        settings, 'BAZIS_MIDDLEWARES', ['tests.test_route_extension_points.replacing']
    )
    response = get_api_client(sample_app).get(MEMOS)
    assert response.status_code == 200, response.text
    assert response.json() == {'replaced': 'action_list'}


@pytest.mark.django_db(transaction=True)
def test_before_hook_refuses_the_request(sample_app, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise HTTPException(status_code=409, detail='busy')

    monkeypatch.setattr(MemoRouteSet, 'action_retrieve__before', refuse, raising=False)
    memo = Memo.objects.create(title='Memo')

    response = get_api_client(sample_app).get(f'{MEMOS}{memo.pk}/')

    assert response.status_code == 409, response.text


@pytest.mark.django_db(transaction=True)
def test_middleware_gets_the_value_of_a_custom_action(sample_app, monkeypatch):
    """A JSON:API action gives a Response, a custom action the value of its method."""
    CALLS.clear()
    monkeypatch.setattr(
        settings, 'BAZIS_MIDDLEWARES', ['tests.test_route_extension_points.result_type']
    )
    memo = Memo.objects.create(title='Memo')
    client = get_api_client(sample_app)

    assert client.get(f'{MEMOS}{memo.pk}/').status_code == 200
    response = client.post(f'{MEMOS}{memo.pk}/subscribe/', json_data={'email': 'a@b.c'})
    assert response.status_code == 200, response.text

    assert CALLS == ['JsonApiResponse', 'SubscribeResponse']
