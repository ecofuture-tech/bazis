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
The default route of a model (whose `restrict_queryset` defines the visibility of the
objects of the model in the relationships of the other routes) and the check of it.
"""

import pytest
from visibility.models import Folder, Tag
from visibility.routes import FolderRouteSet, TagRouteSet

from bazis.core import introspect
from bazis.core.checks import check_default_routes
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase, RestrictedQsRouteMixin


@pytest.fixture
def keep_default_routes(monkeypatch):
    """The route classes defined by a test do not stay the default routes of the models."""
    for model in (Folder, Tag):
        monkeypatch.setattr(model, '_default_route', model.get_default_route())


def test_sample_default_routes():
    assert Folder.get_default_route() is FolderRouteSet
    assert Tag.get_default_route() is TagRouteSet


def test_abstract_route_is_never_default(keep_default_routes):
    class FolderRouteMixin(RestrictedQsRouteMixin):
        abstract = True
        model = Folder

    assert Folder.get_default_route() is FolderRouteSet


def test_last_defined_route_is_default(keep_default_routes):
    class FolderOtherRouteSet(JsonapiRouteBase):
        model = Folder

    assert Folder.get_default_route() is FolderOtherRouteSet


def test_explicit_default_route(keep_default_routes):
    # TagRouteSet declares `default_route = True`
    class TagOtherRouteSet(JsonapiRouteBase):
        model = Tag

    assert Tag.get_default_route() is TagRouteSet

    # the flag is not inherited
    class TagRouteSetChild(TagRouteSet):
        pass

    assert Tag.get_default_route() is TagRouteSet

    class TagMainRouteSet(JsonapiRouteBase):
        model = Tag
        default_route = True

    assert Tag.get_default_route() is TagMainRouteSet


def test_check_default_routes_of_the_sample():
    from bazis.core.app import app  # noqa: F401

    # several route sets of a model that do not restrict its objects (entity.Driver) are
    # not reported
    assert check_default_routes(None) == []


def test_check_several_route_sets_without_default(keep_default_routes, monkeypatch):
    class FolderOtherRouteSet(JsonapiRouteBase):
        model = Folder

    served = {FolderRouteSet: [], FolderOtherRouteSet: []}
    monkeypatch.setattr(introspect, 'loaded_app', lambda: object())
    monkeypatch.setattr(introspect, 'route_sets', lambda app: served)

    # neither restricts the folders
    assert check_default_routes(None) == []

    class FolderRestrictedRouteSet(RestrictedQsRouteMixin):
        model = Folder

        @classmethod
        def restrict_queryset(cls, qs, access_action, user=None, **kwargs):
            return qs.none()

    class TagOtherRouteSet(JsonapiRouteBase):
        model = Tag

    served.update({FolderRestrictedRouteSet: [], TagRouteSet: [], TagOtherRouteSet: []})

    # Tag has an explicit default route
    messages = check_default_routes(None)
    assert [(it.id, it.obj) for it in messages] == [('bazis.W003', 'visibility.Folder')]
    assert 'FolderRestrictedRouteSet' in messages[0].msg
    assert 'default_route = True' in messages[0].hint


def test_check_default_routes_without_app(monkeypatch):
    monkeypatch.setattr(introspect, 'loaded_app', lambda: None)
    assert check_default_routes(None) == []
