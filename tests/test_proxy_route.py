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
A route class of a proxy model has no create and update actions; it excludes them in a list
of its own, not in the list it inherits.
"""

from django.test.utils import isolate_apps

import pytest
from entity.models import ParentEntity

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase


@pytest.fixture
def keep_default_route(monkeypatch):
    """The route classes defined by a test do not stay the default route of the model."""
    monkeypatch.setattr(ParentEntity, '_default_route', ParentEntity.get_default_route())


def actions_of(route_cls):
    return {route.openapi_extra['x-bazis']['action'] for route in route_cls.as_router().routes}


@isolate_apps('entity')
def test_proxy_route_does_not_change_the_list_of_its_parent(keep_default_route):
    class ParentEntityProxy(ParentEntity):
        class Meta:
            app_label = 'entity'
            proxy = True

    class BaseRouteSet(JsonapiRouteBase):
        abstract = True
        actions_exclude = ['action_list_id']

    class ProxyRouteSet(BaseRouteSet):
        model = ParentEntityProxy

    class ProxyChildRouteSet(ProxyRouteSet):
        pass

    class PlainRouteSet(BaseRouteSet):
        model = ParentEntity

    assert BaseRouteSet.actions_exclude == ['action_list_id']
    assert ProxyRouteSet.actions_exclude == ['action_list_id', 'action_create', 'action_update']
    assert ProxyChildRouteSet.actions_exclude == ProxyRouteSet.actions_exclude

    proxy_actions = actions_of(ProxyRouteSet)
    assert 'action_retrieve' in proxy_actions
    assert not proxy_actions & {'action_create', 'action_update', 'action_list_id'}

    plain_actions = actions_of(PlainRouteSet)
    assert {'action_create', 'action_update'} <= plain_actions
    assert 'action_list_id' not in plain_actions
