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
The hooks of the writes of a route, their order and what they see, the errors a hook
answers with, and a read-only route: the statements of the guide (bazis/core/AGENTS.md).
"""

from django.core.exceptions import ValidationError

from fastapi import HTTPException
from fastapi.testclient import TestClient

import pytest
from bazis_test_utils.utils import get_api_client
from validation.models import Booking, Person, Room
from validation.routes import BookingRouteSet
from visibility.models import Note

from bazis.core.errors import (
    JsonApi403Exception,
    JsonApiBazisError,
    JsonApiBazisException,
    JsonApiHttpException,
)
from bazis.core.item_validation import defer_validate_item


URL = '/api/v1/validation/booking/'


def booking(start=10, end=20, **relationships):
    data = {
        'type': 'validation.booking',
        'attributes': {'title': 'Standup', 'start': start, 'end': end},
    }
    if relationships:
        data['relationships'] = relationships
    return {'data': data}


@pytest.fixture
def events(monkeypatch):
    """The calls of the hooks of the bookings route and of validate_item, in order."""
    log = []
    original = Booking.validate_item

    def validate_item(self, changes):
        log.append(('validate_item', changes.source))
        original(self, changes)

    monkeypatch.setattr(Booking, 'validate_item', validate_item)

    def hook(name, see):
        def method(self, item, *args):
            log.append((name, see(item)))

        monkeypatch.setattr(BookingRouteSet, name, method)

    def in_db(item):
        return Booking.objects.filter(pk=item.pk).values_list('title', flat=True).first()

    hook('hook_before_create', lambda item: (item._state.adding, item.title, in_db(item)))
    hook(
        'hook_after_create',
        lambda item: (item._state.adding, in_db(item), item.participants.count()),
    )
    hook('hook_before_update', lambda item: item.title)
    hook('hook_after_update', lambda item: (item.title, in_db(item)))
    hook('hook_before_relationships_change', lambda item: item.room_id)
    hook('hook_after_relationships_change', lambda item: item.room_id)
    Booking.calls.clear()
    yield log
    Booking.calls.clear()


@pytest.mark.django_db(transaction=True)
def test_hooks_of_a_create(sample_app, events):
    """
    hook_before_create: the item is built from the attributes and the to-one relations,
    not saved; hook_after_create: saved, with its to-many relations; validate_item last.
    """
    person = Person.objects.create(name='Ann')
    people = {'data': [{'type': 'validation.person', 'id': str(person.pk)}]}

    response = get_api_client(sample_app).post(URL, json_data=booking(participants=people))

    assert response.status_code == 201, response.text
    assert events == [
        ('hook_before_create', (True, 'Standup', None)),
        ('hook_after_create', (False, 'Standup', 1)),
        ('validate_item', 'create'),
    ]


@pytest.mark.django_db(transaction=True)
def test_hooks_of_an_update(sample_app, events):
    """hook_before_update sees the values in the database, hook_after_update the new ones."""
    item = Booking.objects.create(title='Old', start=10, end=20)
    events.clear()
    data = booking()
    data['data'] |= {'id': str(item.pk), 'attributes': {'title': 'New'}}

    response = get_api_client(sample_app).patch(f'{URL}{item.pk}/', json_data=data)

    assert response.status_code == 200, response.text
    assert events == [
        ('hook_before_update', 'Old'),
        ('hook_after_update', ('New', 'New')),
        ('validate_item', 'update'),
    ]


@pytest.mark.django_db(transaction=True)
def test_hooks_of_the_relationships_endpoints(sample_app, events):
    room = Room.objects.create(name='Blue')
    item = Booking.objects.create(title='Standup', start=10, end=20)
    events.clear()

    response = get_api_client(sample_app).patch(
        f'{URL}{item.pk}/relationships/room',
        json_data={'data': {'type': 'validation.room', 'id': str(room.pk)}},
    )

    assert response.status_code == 204, response.text
    assert events == [
        ('hook_before_relationships_change', None),
        ('hook_after_relationships_change', room.pk),
        ('validate_item', 'relationships'),
    ]


@pytest.mark.django_db(transaction=True)
def test_validate_in_a_hook(sample_app, monkeypatch):
    """
    validate_item runs after hook_after_create: a hook that must see a valid item (before a
    transit, a notification) validates the writes so far with `scope.validate()`.
    """
    seen = []

    def hook_after_create(self, item):
        with defer_validate_item() as scope:
            scope.validate()
        seen.append(item.pk)

    monkeypatch.setattr(BookingRouteSet, 'hook_after_create', hook_after_create)
    client = get_api_client(sample_app)

    response = client.post(URL, json_data=booking(start=20, end=10))
    assert response.status_code == 422, response.text
    error = response.json()['errors'][0]
    assert (error['code'], error['source']) == (
        'ERR_ITEM_INVALID',
        {'pointer': '/data/attributes/end'},
    )
    assert seen == [] and not Booking.objects.exists()

    assert client.post(URL, json_data=booking()).status_code == 201
    assert seen == [Booking.objects.get().pk]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'loc, source',
    [
        (('body', 'data', 'attributes', 'title'), {'pointer': '/data/attributes/title'}),
        (('data', 'relationships', 'room'), {'pointer': '/data/relationships/room'}),
        (('attributes', 'title'), {'pointer': '/attributes/title'}),
        (('path', 'item_id'), {'parameter': '/item_id'}),
        (None, None),
    ],
)
def test_error_of_a_hook(sample_app, monkeypatch, loc, source):
    """
    The `loc` of a JsonApiBazisError is the source of the error: `path` gives a parameter,
    anything else a pointer (without a leading `body`); the status of the response is the
    status of the JsonApiBazisException (400 by default).
    """

    def hook_before_create(self, item):
        raise JsonApiBazisException(JsonApiBazisError('Not on Fridays', loc=loc), status=422)

    monkeypatch.setattr(BookingRouteSet, 'hook_before_create', hook_before_create)

    response = get_api_client(sample_app).post(URL, json_data=booking())

    assert response.status_code == 422
    error = response.json()['errors'][0]
    assert (error['status'], error['code'], error['detail']) == (
        422,
        'ERR_VALIDATE',
        'Not on Fridays',
    )
    assert error.get('source') == source
    assert not Booking.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_error_of_a_hook_without_a_status(sample_app, monkeypatch):
    def hook_before_create(self, item):
        raise JsonApiBazisException(JsonApiBazisError('Not on Fridays'))

    monkeypatch.setattr(BookingRouteSet, 'hook_before_create', hook_before_create)

    response = get_api_client(sample_app).post(URL, json_data=booking())

    assert response.status_code == 400
    assert response.json()['errors'][0]['status'] == 422


@pytest.mark.django_db(transaction=True)
def test_django_validation_error_of_a_hook_is_a_server_error(sample_app, monkeypatch):
    """Only validate_item turns a Django ValidationError into 422; in a hook it is 500."""

    def hook_before_create(self, item):
        raise ValidationError({'title': 'Not on Fridays'})

    monkeypatch.setattr(BookingRouteSet, 'hook_before_create', hook_before_create)
    client = TestClient(sample_app, raise_server_exceptions=False)

    response = client.post(
        URL, json=booking(), headers={'Content-Type': 'application/vnd.api+json'}
    )

    assert response.status_code == 500
    assert not Booking.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_read_only_route(sample_app):
    """
    A route class that lists its `actions` has only them: the projection of the notes
    (visibility.note_brief) lists and shows, it does not write nor show the attributes it
    hides (`dict_data` shows all the attributes of the model).
    """
    note = Note.objects.create(name='Secret topic')
    client = get_api_client(sample_app)
    url = '/api/v1/visibility/note_brief/'

    assert client.get(url).status_code == 200
    assert 'name' not in client.get(f'{url}{note.pk}/').json()['data'].get('attributes', {})
    assert client.get(f'{url}schema_list/').status_code == 200
    assert client.get(f'{url}{note.pk}/dict_data/').status_code == 404
    assert client.get(f'{url}schema_create/').status_code == 404
    data = {'data': {'type': 'visibility.note', 'attributes': {}}}
    assert client.post(url, json_data=data).status_code == 405
    assert client.patch(f'{url}{note.pk}/', json_data=data).status_code == 405
    assert client.delete(f'{url}{note.pk}/').status_code == 405
    tags = f'{url}{note.pk}/relationships/tags'
    for method in ('POST', 'PATCH', 'DELETE'):
        response = client.client.request(method, tags, headers=client.headers, json={'data': []})
        assert response.status_code in (404, 405), method
    Note.objects.get(name='Secret topic')


def test_schema_fields_of_an_action():
    """
    The fields of an action, read along the MRO, the parents first, in each class its
    `None` entry then its action entry: `include` and `exclude` add up, the last `origin`
    wins (so a `None` entry of a child overrides an action entry of its parent);
    `is_inherit=False` on the action leaves out the `None` entry of the same class only.
    """
    from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
    from bazis.core.schemas.enums import CrudApiAction
    from bazis.core.schemas.fields import SchemaFields

    build = JsonapiRouteBase.build_schema_attrs.__func__

    class Parent:
        fields = {None: SchemaFields(origin={'a': None, 'b': None}, exclude={'b': None})}

    class Child(Parent):
        fields = {
            None: SchemaFields(include={'c': None}),
            CrudApiAction.UPDATE: SchemaFields(origin={'a': None}, include={'d': None}),
        }

    class Strict(Parent):
        fields = {
            None: SchemaFields(include={'c': None}),
            CrudApiAction.UPDATE: SchemaFields(include={'d': None}, is_inherit=False),
        }

    update = build(Child, CrudApiAction.UPDATE, 'fields', SchemaFields)
    assert (set(update.origin), set(update.include), set(update.exclude)) == (
        {'a'},
        {'c', 'd'},
        {'b'},
    )
    listing = build(Child, CrudApiAction.LIST, 'fields', SchemaFields)
    assert (set(listing.origin), set(listing.include)) == ({'a', 'b'}, {'c'})
    strict = build(Strict, CrudApiAction.UPDATE, 'fields', SchemaFields)
    assert (set(strict.origin), set(strict.include), set(strict.exclude)) == (
        {'a', 'b'},
        {'d'},
        {'b'},
    )

    class ParentOfAction:
        fields = {CrudApiAction.UPDATE: SchemaFields(origin={'a': None})}

    class ChildOfAll(ParentOfAction):
        fields = {None: SchemaFields(origin={'b': None})}

    assert set(build(ChildOfAll, CrudApiAction.UPDATE, 'fields', SchemaFields).origin) == {'b'}


@pytest.mark.django_db(transaction=True)
def test_model_clean_is_not_called(sample_app, monkeypatch):
    """The routes do not call full_clean(): a rule in Model.clean() does not refuse a write."""

    def clean(self):
        raise ValidationError({'title': 'Not on Fridays'})

    monkeypatch.setattr(Booking, 'clean', clean)

    assert get_api_client(sample_app).post(URL, json_data=booking()).status_code == 201


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'exc, status, code',
    [
        (JsonApi403Exception(), 403, 'ERR_FORBIDDEN'),
        (JsonApiHttpException(status_code=409, detail='Taken', code='ERR_TAKEN'), 409, 'ERR_TAKEN'),
        (HTTPException(status_code=409, detail='Taken'), 409, 'ERR_REQUEST'),
    ],
)
def test_http_error_of_a_hook_keeps_its_code(sample_app, monkeypatch, exc, status, code):
    """
    A JSON:API HTTP error raised in a route keeps its code (the route answered
    ERR_REQUEST for a JsonApi403Exception); a plain HTTPException is ERR_REQUEST.
    """

    def hook_before_create(self, item):
        raise exc

    monkeypatch.setattr(BookingRouteSet, 'hook_before_create', hook_before_create)

    response = get_api_client(sample_app).post(URL, json_data=booking())

    assert response.status_code == status
    assert response.json()['errors'][0]['code'] == code
