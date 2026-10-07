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
The errors the route classes document in the OpenAPI operations (`route_responses`) and
the `route_openapi_extra` extension point.
"""

import json
import uuid

import pytest
from bazis_test_utils.utils import get_api_client

from bazis.core.errors import SchemaErrors
from bazis.core.routes_abstract.initial import (
    OPENAPI_EXTENSION,
    InitialRouteBase,
    deep_merge,
    http_get,
)
from bazis.core.schemas.enums import RouteKind


SCHEMA_ERRORS = '#/components/schemas/SchemaErrors'


@pytest.fixture(scope='module')
def operations():
    from bazis.core.app import app

    return {
        (path, method.upper()): operation
        for path, item in app.openapi()['paths'].items()
        for method, operation in item.items()
        if 'x-bazis' in operation
    }


def error_schema_refs(operation, status):
    """The schemas of the response `status` (all media types), None without the response."""
    response = operation['responses'].get(status)
    if response is None:
        return None
    return {content['schema']['$ref'] for content in response['content'].values()}


def test_item_routes_document_not_found(operations):
    """
    404 (JSON:API errors) is documented exactly on the routes of an item: the ones the
    core answers with 404 when the item does not exist.
    """
    for (path, method), operation in operations.items():
        expected = {SCHEMA_ERRORS} if '{item_id}' in path else None
        assert error_schema_refs(operation, '404') == expected, (method, path)

    kinds = {
        operation['x-bazis']['kind']
        for (path, _), operation in operations.items()
        if '{item_id}' in path
    }
    assert kinds == {'item', 'update', 'delete', 'relationship', 'schema', 'other'}


def test_relationship_routes_document_forbidden(operations):
    """
    403 is documented on the relationship routes (a read-only relationship, restricted
    objects) only: the core has no other reason to answer with 403, and with no
    authentication of its own no reason to answer with 401.
    """
    for (path, method), operation in operations.items():
        is_relationship = operation['x-bazis']['kind'] == RouteKind.RELATIONSHIP
        expected = {SCHEMA_ERRORS} if is_relationship else None
        assert error_schema_refs(operation, '403') == expected, (method, path)
        assert '401' not in operation['responses'], (method, path)


@pytest.mark.parametrize(
    'kind, statuses',
    [
        ('collection', {'200', '400', '422'}),
        ('create', {'201', '400', '422'}),
        ('item', {'200', '400', '404', '422'}),
        ('update', {'200', '400', '404', '422'}),
        ('delete', {'204', '400', '404', '422'}),
        ('relationship', {'204', '403', '404', '422'}),
    ],
)
def test_crud_responses(operations, kind, statuses):
    """The documented errors extend the responses of the CRUD routes, they do not replace them."""
    found = {
        frozenset(operation['responses'])
        for operation in operations.values()
        if operation['x-bazis']['kind'] == kind
    }
    assert found == {frozenset(statuses)}


@pytest.mark.django_db(transaction=True)
def test_documented_not_found_is_what_the_route_returns(sample_app):
    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/{uuid.uuid4()}/')

    assert response.status_code == 404
    assert SchemaErrors.model_validate(response.json()).errors[0].status == 404


def test_openapi_is_deterministic():
    """The documented responses do not depend on the order the routes were built in."""
    from bazis.core.app import app

    cached = app.openapi_schema
    try:
        dumps = []
        for _ in range(2):
            app.openapi_schema = None
            dumps.append(json.dumps(app.openapi()))
    finally:
        app.openapi_schema = cached
    assert dumps[0] == dumps[1]


class ErrorsBase(InitialRouteBase):
    abstract = True

    @classmethod
    def route_responses(cls, route_ctx):
        return {**super().route_responses(route_ctx), 401: {'description': 'Base'}}


class ErrorsRouteSet(ErrorsBase):
    @classmethod
    def route_responses(cls, route_ctx):
        return {**super().route_responses(route_ctx), 403: {'description': 'Set'}}

    @http_get('/plain/')
    def action_plain(self, **kwargs):
        pass

    @http_get('/declared/', responses={401: {'description': 'Declared'}})
    def action_declared(self, **kwargs):
        pass


def test_route_responses_extended_by_classes():
    """
    A route class (or a package) adds the statuses its routes fail with by extending
    `route_responses`; what the route declares itself takes priority.
    """
    responses = {route.name: route.responses for route in ErrorsRouteSet.as_router().routes}

    assert responses['ErrorsRouteSet_action_plain'] == {
        401: {'description': 'Base'},
        403: {'description': 'Set'},
    }
    assert responses['ErrorsRouteSet_action_declared'] == {
        401: {'description': 'Declared'},
        403: {'description': 'Set'},
    }


def test_route_responses_default_is_empty():
    class PlainRouteSet(InitialRouteBase):
        @http_get('/')
        def action_any(self, **kwargs):
            pass

    (route,) = PlainRouteSet.as_router().routes
    assert route.responses == {}


class ExtraBase(InitialRouteBase):
    abstract = True
    #: what the class adds to the OpenAPI of its routes; a subclass changes it
    security = [{'token': []}]

    @classmethod
    def route_openapi_extra(cls, route_ctx):
        return {**super().route_openapi_extra(route_ctx), 'security': cls.security}


class ExtraParent(ExtraBase):
    @http_get('/plain/')
    def action_plain(self, **kwargs):
        pass

    @http_get('/declared/', openapi_extra={'security': [], 'x-other': {'a': 1}})
    def action_declared(self, **kwargs):
        pass


class ExtraChild(ExtraParent):
    security = [{'token': []}, {}]


def registered_extra(route_cls):
    return {route.name: route.openapi_extra for route in route_cls.as_router().routes}


def test_route_openapi_extra_extended_by_classes():
    """
    A class extends `x-bazis` with its own facts, what the route declares itself wins, and
    the route context stays untouched.
    """
    extra = registered_extra(ExtraParent)

    assert extra['ExtraParent_action_plain']['security'] == [{'token': []}]
    assert extra['ExtraParent_action_plain'][OPENAPI_EXTENSION]['action'] == 'action_plain'
    assert extra['ExtraParent_action_declared']['security'] == []
    assert extra['ExtraParent_action_declared']['x-other'] == {'a': 1}
    assert ExtraParent.action_plain.route_params.openapi_extra is None
    assert ExtraParent.action_declared.route_params.openapi_extra == {
        'security': [],
        'x-other': {'a': 1},
    }


@pytest.mark.parametrize('parent_first', [True, False])
def test_route_openapi_extra_does_not_leak_between_classes(parent_first):
    """
    What a class adds to its routes depends on the class only, not on which of the parent
    and the subclass registered its routes first.
    """
    classes = [ExtraParent, ExtraChild] if parent_first else [ExtraChild, ExtraParent]
    extra = {cls.__name__: registered_extra(cls) for cls in classes}

    assert extra['ExtraParent']['ExtraParent_action_plain']['security'] == [{'token': []}]
    assert extra['ExtraChild']['ExtraChild_action_plain']['security'] == [{'token': []}, {}]


def test_deep_merge():
    base = {'a': {'b': 1, 'c': [1]}, 'd': 1}
    override = {'a': {'c': [2], 'e': 2}, 'd': {'f': 3}}

    assert deep_merge(base, override) == {'a': {'b': 1, 'c': [2], 'e': 2}, 'd': {'f': 3}}
    assert base == {'a': {'b': 1, 'c': [1]}, 'd': 1}
    assert override == {'a': {'c': [2], 'e': 2}, 'd': {'f': 3}}
