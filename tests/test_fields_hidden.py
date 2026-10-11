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
`InitialBase.get_fields_hidden()`: the internal columns a package adds to a model (the
selector arrays of bazis-permit) are not in the default schemas of the routes; a route
that names one in `include` or `origin` has it.
"""

import pytest
from catalog.models import Memo
from catalog.routes import MemoRouteSet

from bazis.core.schemas import CrudApiAction, SchemaFields
from bazis.core.schemas.factory import SchemaFactory


def fields(action=CrudApiAction.RETRIEVE, fields_struct=None) -> set[str]:
    return set(
        SchemaFactory(
            route_cls=MemoRouteSet, model=Memo, api_action=action, fields_struct=fields_struct
        ).fields
    )


def test_no_hidden_fields_by_default():
    assert Memo.get_fields_hidden() == set()
    assert {'code', 'category'} <= fields()


@pytest.fixture
def hidden(monkeypatch):
    monkeypatch.setattr(Memo, 'get_fields_hidden', classmethod(lambda cls: {'code', 'category'}))


@pytest.mark.parametrize(
    'action', [CrudApiAction.LIST, CrudApiAction.RETRIEVE, CrudApiAction.CREATE, CrudApiAction.UPDATE]
)
def test_hidden_fields_are_left_out(hidden, action):
    assert 'title' in fields(action)
    assert not {'code', 'category'} & fields(action)


def test_a_route_names_a_hidden_field(hidden):
    assert 'code' in fields(fields_struct=SchemaFields(include={'code': None}))
    assert fields(fields_struct=SchemaFields(origin={'code': None, 'title': None})) == {
        'code',
        'title',
    }
