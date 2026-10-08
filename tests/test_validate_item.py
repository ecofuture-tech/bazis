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
`JsonApiMixin.validate_item` is called once per write of an item, whichever way it is
written (the create, update and relationships endpoints, `save()` in the admin and in
scripts, the many-to-many managers), after the write and before the commit; its failure
answers 422 `ERR_ITEM_INVALID` on the API and rolls the write back. The models that do not
override it pay nothing.
"""

import json

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models.signals import m2m_changed
from django.test.utils import CaptureQueriesContext

import pytest
from bazis_test_utils.utils import get_api_client
from validation.models import Booking, Equipment, Person, Room
from visibility.models import Note

from bazis.core.errors import JsonApiItemInvalidException
from bazis.core.item_validation import defer_validate_item, reverse_items_link


# all the fields of a new booking, without the primary key and `dt_updated` (auto_now)
BOOKING_FIELDS = frozenset({'dt_created', 'title', 'start', 'end', 'room'})
URL = '/api/v1/validation/booking/'


@pytest.fixture
def calls():
    Booking.calls.clear()
    yield Booking.calls
    Booking.calls.clear()


def only_call(calls, pk=None):
    assert len(calls) == 1, calls
    call_pk, changes = calls[0]
    if pk is not None:
        assert call_pk == pk
    return changes


def booking_data(*, start=10, end=20, room=None, participants=None, title='Standup', pk=None):
    data = {
        'type': 'validation.booking',
        'attributes': {'title': title, 'start': start, 'end': end},
    }
    if pk:
        data['id'] = str(pk)
    relationships = {}
    if room is not None:
        relationships['room'] = {'data': {'type': 'validation.room', 'id': str(room.pk)}}
    if participants is not None:
        relationships['participants'] = {
            'data': [{'type': 'validation.person', 'id': str(p.pk)} for p in participants]
        }
    if relationships:
        data['relationships'] = relationships
    return {'data': data}


def relation(*objs):
    return {'data': [{'type': obj.get_resource_label(), 'id': str(obj.pk)} for obj in objs]}


def assert_invalid(response, *, pointer=None, parameter=None):
    assert response.status_code == 422, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_ITEM_INVALID'
    if pointer:
        assert error['source']['pointer'] == pointer
    if parameter:
        assert error['source']['parameter'] == parameter


def make_booking(room=None, start=10, end=20, title='Standup'):
    booking = Booking.objects.create(title=title, start=start, end=end, room=room)
    Booking.calls.clear()
    return booking


# the API


@pytest.mark.django_db(transaction=True)
def test_create_validates_once(sample_app, calls):
    room = Room.objects.create(name='Blue')
    people = [Person.objects.create(name='Ann'), Person.objects.create(name='Bob')]

    response = get_api_client(sample_app).post(
        URL, json_data=booking_data(room=room, participants=people)
    )

    assert response.status_code == 201, response.text
    changes = only_call(calls, Booking.objects.get().pk)
    assert changes.is_new is True
    assert changes.source == 'create'
    assert changes.fields == BOOKING_FIELDS
    assert changes.relations == {'participants'}
    assert changes.user is None


@pytest.mark.django_db(transaction=True)
def test_create_invalid_is_rolled_back(sample_app, calls):
    response = get_api_client(sample_app).post(URL, json_data=booking_data(start=20, end=10))

    assert_invalid(response, pointer='/data/attributes/end')
    assert not Booking.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_update_validates_once(sample_app, calls):
    booking = make_booking()
    person = Person.objects.create(name='Ann')
    client = get_api_client(sample_app)

    response = client.patch(
        f'{URL}{booking.pk}/',
        json_data={'data': {**booking_data(title='Retro', pk=booking.pk)['data']}},
    )
    assert response.status_code == 200, response.text
    changes = only_call(calls, booking.pk)
    assert (changes.is_new, changes.source) == (False, 'update')
    assert changes.fields == {'title'}
    assert changes.relations == set()

    calls.clear()
    response = client.patch(
        f'{URL}{booking.pk}/',
        json_data={
            'data': {
                'id': str(booking.pk),
                'type': 'validation.booking',
                'relationships': {'participants': relation(person)},
            }
        },
    )
    assert response.status_code == 200, response.text
    changes = only_call(calls, booking.pk)
    assert changes.fields == set()
    assert changes.relations == {'participants'}


@pytest.mark.django_db(transaction=True)
def test_update_invalid_is_rolled_back(sample_app, calls):
    room = Room.objects.create(name='Blue')
    make_booking(room, 10, 20)
    booking = make_booking(room, 30, 40, title='Retro')

    response = get_api_client(sample_app).patch(
        f'{URL}{booking.pk}/',
        json_data=booking_data(start=15, end=40, title='Moved', pk=booking.pk),
    )

    assert_invalid(response, pointer='/data/relationships/room')
    booking.refresh_from_db()
    assert (booking.title, booking.start) == ('Retro', 30)


@pytest.mark.django_db(transaction=True)
def test_relationships_to_one(sample_app, calls):
    blue, green = Room.objects.create(name='Blue'), Room.objects.create(name='Green')
    make_booking(green, 10, 20)
    booking = make_booking(blue, 15, 25)
    url = f'{URL}{booking.pk}/relationships/room'
    client = get_api_client(sample_app)

    # the room is taken at this time: the change is refused and rolled back
    response = client.patch(
        url, json_data={'data': {'type': 'validation.room', 'id': str(green.pk)}}
    )
    assert_invalid(response, parameter='/related_field_name')
    booking.refresh_from_db()
    assert booking.room_id == blue.pk
    calls.clear()

    response = client.patch(url, json_data={'data': None})
    assert response.status_code == 204, response.text
    changes = only_call(calls, booking.pk)
    assert (changes.is_new, changes.source) == (False, 'relationships')
    assert changes.fields == {'room'}
    assert changes.relations == set()


@pytest.mark.django_db(transaction=True)
def test_relationships_many_to_many(sample_app, calls):
    room = Room.objects.create(name='Blue', seats=2)
    booking = make_booking(room)
    ann, bob, eve = (Person.objects.create(name=name) for name in ('Ann', 'Bob', 'Eve'))
    url = f'{URL}{booking.pk}/relationships/participants'
    client = get_api_client(sample_app)

    for method, payload, expected in (
        ('POST', relation(ann, bob), {ann.pk, bob.pk}),
        ('DELETE', relation(bob), {ann.pk}),
        ('PATCH', relation(bob, eve), {bob.pk, eve.pk}),
    ):
        calls.clear()
        response = client.client.request(method, url, headers=client.headers, json=payload)
        assert response.status_code == 204, (method, response.text)
        changes = only_call(calls, booking.pk)
        assert (changes.source, changes.fields, changes.relations) == (
            'relationships',
            set(),
            {'participants'},
        ), method
        assert set(booking.participants.values_list('pk', flat=True)) == expected

    # a third participant does not fit the room: rolled back
    response = client.post(url, json_data=relation(ann))
    assert_invalid(response, parameter='/related_field_name')
    assert set(booking.participants.values_list('pk', flat=True)) == {bob.pk, eve.pk}


@pytest.mark.django_db(transaction=True)
def test_relationships_reverse_foreign_key_validate_the_linked_items(sample_app, calls):
    blue, green = Room.objects.create(name='Blue'), Room.objects.create(name='Green')
    make_booking(green, 10, 20)
    booking = make_booking(blue, 15, 25)
    client = get_api_client(sample_app)

    # moving the booking into the other room through the room validates the booking
    response = client.post(
        f'/api/v1/validation/room/{green.pk}/relationships/bookings', json_data=relation(booking)
    )
    assert_invalid(response, parameter='/related_field_name')
    booking.refresh_from_db()
    assert booking.room_id == blue.pk

    calls.clear()
    other = make_booking(None, 30, 40)
    response = client.post(
        f'/api/v1/validation/room/{green.pk}/relationships/bookings', json_data=relation(other)
    )
    assert response.status_code == 204, response.text
    changes = only_call(calls, other.pk)
    assert (changes.source, changes.fields) == ('save', {'room'})


@pytest.mark.django_db(transaction=True)
def test_reverse_many_to_many_through_the_api(sample_app, calls):
    booking = make_booking(Room.objects.create(name='Blue', seats=1))
    ann, bob = Person.objects.create(name='Ann'), Person.objects.create(name='Bob')
    client = get_api_client(sample_app)

    response = client.post(
        f'/api/v1/validation/person/{ann.pk}/relationships/bookings', json_data=relation(booking)
    )
    assert response.status_code == 204, response.text
    changes = only_call(calls, booking.pk)
    assert changes.relations == {'participants'}

    response = client.post(
        f'/api/v1/validation/person/{bob.pk}/relationships/bookings', json_data=relation(booking)
    )
    assert_invalid(response, parameter='/related_field_name')
    assert list(booking.participants.all()) == [ann]


# outside the API


@pytest.mark.django_db
def test_save_validates_once(calls):
    room = Room.objects.create(name='Blue')
    booking = Booking.objects.create(title='Standup', start=10, end=20, room=room)
    changes = only_call(calls, booking.pk)
    assert (changes.is_new, changes.source, changes.user) == (True, 'save', None)
    assert changes.fields == BOOKING_FIELDS
    assert changes.relations == set()

    calls.clear()
    booking.title = 'Retro'
    booking.save()
    changes = only_call(calls, booking.pk)
    assert (changes.is_new, changes.fields) == (False, {'title'})

    # only the saved fields
    calls.clear()
    booking.start, booking.title = 12, 'Planning'
    booking.save(update_fields=['start'])
    assert only_call(calls).fields == {'start'}

    # an item loaded again
    calls.clear()
    booking = Booking.objects.get(pk=booking.pk)
    booking.room = None
    booking.save()
    assert only_call(calls).fields == {'room'}


@pytest.mark.django_db
def test_save_invalid_is_rolled_back(calls):
    booking = make_booking(start=10, end=20)

    booking.end = 5
    with pytest.raises(JsonApiItemInvalidException) as e:
        booking.save()

    assert e.value.status == 422
    assert e.value.error.message_dict == {'end': ['The booking must end after it starts']}
    assert e.value.item is booking
    # the save is rolled back (to its savepoint): the transaction goes on
    assert Booking.objects.get(pk=booking.pk).end == 20
    with pytest.raises(JsonApiItemInvalidException):
        Booking.objects.create(title='Broken', start=3, end=1)
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_many_to_many_managers(calls):
    room = Room.objects.create(name='Blue', seats=2)
    booking, other = make_booking(room, 10, 20), make_booking(room, 30, 40)
    ann, bob, eve = (Person.objects.create(name=name) for name in ('Ann', 'Bob', 'Eve'))

    booking.participants.add(ann, bob)
    changes = only_call(calls, booking.pk)
    assert (changes.source, changes.fields, changes.relations) == ('save', set(), {'participants'})

    # the other side of the relation: the bookings the person is added to
    calls.clear()
    eve.bookings.add(other)
    changes = only_call(calls, other.pk)
    assert changes.relations == {'participants'}

    calls.clear()
    ann.bookings.clear()
    assert [pk for pk, _ in calls] == [booking.pk]

    # the manager writes without a savepoint: a failure rolls back the enclosing block
    calls.clear()
    with pytest.raises(JsonApiItemInvalidException), transaction.atomic():
        booking.participants.add(ann, eve)
    assert set(booking.participants.values_list('pk', flat=True)) == {bob.pk}


@pytest.mark.django_db
def test_defer_validate_item_validates_once_at_the_end(calls, django_user_model):
    """A script or an admin form: several writes of an item, one validation."""
    user = django_user_model.objects.create(username='admin')
    room = Room.objects.create(name='Blue', seats=2)
    ann = Person.objects.create(name='Ann')

    with defer_validate_item(user=user):
        booking = Booking.objects.create(title='Standup', start=10, end=20)
        booking.participants.set([ann])
        booking.room = room
        booking.save()
        assert calls == []

    changes = only_call(calls, booking.pk)
    assert (changes.is_new, changes.source, changes.user) == (True, 'save', user)
    assert changes.fields == BOOKING_FIELDS
    assert changes.relations == {'participants'}

    # a failure at the end rolls back all the writes of the block
    calls.clear()
    with pytest.raises(JsonApiItemInvalidException):
        with defer_validate_item():
            booking.title = 'Moved'
            booking.save()
            Booking.objects.create(title='Overlap', start=15, end=25, room=room)
    assert Booking.objects.get().title == 'Standup'


@pytest.mark.django_db
def test_validate_item_writing_items_is_not_recursive(calls, monkeypatch):
    room = Room.objects.create(name='Blue')
    validate_item = Booking.validate_item

    def validate_and_write(self, changes):
        validate_item(self, changes)
        if self.title == 'Standup':
            # the item itself: not validated again
            self.title = 'Standup!'
            self.save()
            # another item: validated in turn
            Booking.objects.create(title='Follow-up', start=self.end, end=self.end + 5, room=room)

    monkeypatch.setattr(Booking, 'validate_item', validate_and_write)
    booking = Booking.objects.create(title='Standup', start=10, end=20, room=room)

    assert [pk for pk, _ in calls] == [booking.pk, Booking.objects.get(title='Follow-up').pk]
    assert Booking.objects.get(pk=booking.pk).title == 'Standup!'


@pytest.mark.django_db
def test_admin_form(admin_client, admin_user, calls):
    room = Room.objects.create(name='Blue', seats=2)
    make_booking(room, 10, 20)
    ann = Person.objects.create(name='Ann')
    url = '/admin/validation/booking/add/'
    form = {'title': 'Retro', 'start': 30, 'end': 40, 'room': room.pk, 'participants': [ann.pk]}

    response = admin_client.post(url, form)
    assert response.status_code == 302, response.content
    booking = Booking.objects.get(title='Retro')
    changes = only_call(calls, booking.pk)
    assert (changes.is_new, changes.source, changes.user) == (True, 'save', admin_user)
    assert changes.fields == BOOKING_FIELDS
    assert changes.relations == {'participants'}

    # an overlap: the form shows the error on its field and nothing is saved
    calls.clear()
    response = admin_client.post(url, {**form, 'title': 'Overlap', 'start': 15})
    assert response.status_code == 200
    assert response.context['adminform'].form.errors == {
        'room': ['The room is booked at this time']
    }
    assert not Booking.objects.filter(title='Overlap').exists()


@pytest.mark.django_db
def test_models_without_validate_item_pay_nothing():
    assert not Person.has_validate_item() and Booking.has_validate_item()

    with CaptureQueriesContext(connection) as queries:
        person = Person.objects.create(name='Ann')
        person.name = 'Bob'
        person.save()
    assert len(queries) == 2
    assert not any('SAVEPOINT' in q['sql'] for q in queries.captured_queries)
    assert '_bazis_validate_snapshot' not in Person.objects.get().__dict__

    # Django checks the targets of add() with a query when the relation has a receiver
    assert not m2m_changed.has_listeners(Note.tags.through)
    assert m2m_changed.has_listeners(Booking.participants.through)


@pytest.mark.django_db(transaction=True)
def test_included_item_errors_point_to_it(sample_app, calls):
    response = get_api_client(sample_app).post(
        '/api/v1/validation/room/?include=bookings',
        json_data={
            'data': {'type': 'validation.room', 'attributes': {'name': 'Blue'}},
            'included': [
                {
                    'type': 'validation.booking',
                    'bs:action': 'add',
                    'attributes': {'title': 'Standup', 'start': 20, 'end': 10},
                }
            ],
        },
    )

    assert_invalid(response, pointer='/included/0/attributes/end')
    assert not Room.objects.exists() and not Booking.objects.exists()


@pytest.mark.django_db
def test_writes_after_a_validation_are_validated_again(calls):
    """The admin validates in the middle of its block (after save_related)."""
    room = Room.objects.create(name='Blue')
    make_booking(room, 10, 20)

    with pytest.raises(JsonApiItemInvalidException):
        with defer_validate_item() as scope:
            booking = Booking.objects.create(title='Retro', start=30, end=40, room=room)
            scope.validate()
            booking.start = 15
            booking.save()

    assert [changes.fields for _, changes in calls] == [BOOKING_FIELDS, {'start'}]
    assert Booking.objects.count() == 1


@pytest.mark.django_db
def test_set_validates_once_on_the_final_state(calls, monkeypatch):
    """Django sets a relation with remove() and add(): validated once, after both."""
    booking, other = make_booking(start=10, end=20), make_booking(start=30, end=40)
    ann, bob, eve = (Person.objects.create(name=name) for name in ('Ann', 'Bob', 'Eve'))
    booking.participants.set([ann, bob])
    calls.clear()

    validate_item = Booking.validate_item
    states = []

    def validate_and_record(self, changes):
        states.append((self.title, set(self.participants.values_list('name', flat=True))))
        validate_item(self, changes)

    monkeypatch.setattr(Booking, 'validate_item', validate_and_record)

    booking.participants.set([bob, eve])
    assert states == [('Standup', {'Bob', 'Eve'})]
    assert only_call(calls, booking.pk).relations == {'participants'}

    # the other side: each booking whose participants change, once
    states.clear()
    eve.bookings.set([other])
    assert sorted(states) == [('Standup', {'Bob'}), ('Standup', {'Eve'})]

    # add(), remove() and clear() validate each change
    states.clear()
    booking.participants.add(ann)
    booking.participants.remove(ann)
    booking.participants.clear()
    assert states == [('Standup', {'Ann', 'Bob'}), ('Standup', {'Bob'}), ('Standup', set())]


@pytest.mark.django_db
def test_failed_save_keeps_the_values_of_the_database(calls):
    booking = make_booking(start=10, end=20)

    booking.end = 5
    with pytest.raises(JsonApiItemInvalidException):
        booking.save()

    # end is still not saved: the next save writes it as a change
    calls.clear()
    booking.start = 1
    booking.save()
    assert only_call(calls).fields == {'start', 'end'}
    assert Booking.objects.get(pk=booking.pk).end == 5


@pytest.mark.django_db
def test_reverse_items_are_linked_by_their_foreign_key(calls):
    room = Room.objects.create(name='Blue')
    booking = make_booking(start=10, end=20)
    stale = Booking.objects.get(pk=booking.pk)
    Booking.objects.filter(pk=booking.pk).update(title='Renamed')

    with CaptureQueriesContext(connection) as queries:
        reverse_items_link(room.bookings, 'add', [stale])

    updates = [q['sql'] for q in queries.captured_queries if q['sql'].startswith('UPDATE')]
    assert len(updates) == 1 and '"title"' not in updates[0]
    assert Booking.objects.get(pk=booking.pk).title == 'Renamed'
    assert only_call(calls, booking.pk).fields == {'room'}

    calls.clear()
    reverse_items_link(room.bookings, 'set', [])
    assert Booking.objects.get(pk=booking.pk).room_id is None
    assert only_call(calls).fields == {'room'}


@pytest.mark.django_db(transaction=True)
def test_included_item_errors_point_to_it_on_update(sample_app, calls):
    room = Room.objects.create(name='Blue')
    booking = make_booking(room, 10, 20)

    response = get_api_client(sample_app).patch(
        f'/api/v1/validation/room/{room.pk}/?include=bookings',
        json_data={
            'data': {
                'id': str(room.pk),
                'type': 'validation.room',
                'bs:action': 'change',
                'attributes': {'name': 'Green'},
            },
            'included': [
                {
                    'id': str(booking.pk),
                    'type': 'validation.booking',
                    'bs:action': 'change',
                    'attributes': {'end': 5},
                }
            ],
        },
    )

    assert_invalid(response, pointer='/included/0/attributes/end')
    assert Room.objects.get().name == 'Blue'
    assert Booking.objects.get().end == 20


@pytest.fixture
def equipment_calls():
    Equipment.calls.clear()
    yield Equipment.calls
    Equipment.calls.clear()


@pytest.mark.django_db
def test_hidden_many_to_many(equipment_calls):
    """A relation without a reverse one (`related_name='+'`) has one side to validate."""
    ann, bob = Person.objects.create(name='Ann'), Person.objects.create(name='Bob')
    equipment = Equipment.objects.create(name='Projector', room=Room.objects.create(name='Blue'))
    equipment_calls.clear()

    equipment.keepers.add(ann)
    equipment.keepers.set([bob])
    assert [changes.relations for _, changes in equipment_calls] == [{'keepers'}, {'keepers'}]


@pytest.mark.django_db
def test_reverse_non_null_foreign_key(equipment_calls):
    blue, green = Room.objects.create(name='Blue'), Room.objects.create(name='Green')
    equipment = Equipment.objects.create(name='Projector', room=blue)
    equipment_calls.clear()

    reverse_items_link(green.equipment, 'add', [equipment])
    assert Equipment.objects.get().room_id == green.pk
    assert [changes.fields for _, changes in equipment_calls] == [{'room'}]

    # an item whose foreign key cannot be null is not unlinked (as Django's set())
    equipment_calls.clear()
    reverse_items_link(green.equipment, 'set', [])
    assert Equipment.objects.get().room_id == green.pk
    assert equipment_calls == []


@pytest.mark.django_db
def test_raw_changes_are_not_validated(calls, tmp_path):
    room, ann = Room.objects.create(name='Blue'), Person.objects.create(name='Ann')
    fixture = tmp_path / 'bookings.json'
    fixture.write_text(
        json.dumps(
            [
                {
                    'model': 'validation.booking',
                    'pk': '7d4f3c1e-0d3a-4b55-9d4e-0f8b6d0c2a11',
                    'fields': {
                        'title': 'Loaded',
                        'start': 20,
                        'end': 10,
                        'room': str(room.pk),
                        'participants': [str(ann.pk)],
                    },
                }
            ]
        )
    )
    calls.clear()

    call_command('loaddata', str(fixture), verbosity=0)

    assert calls == []
    assert list(Booking.objects.get().participants.all()) == [ann]


@pytest.mark.django_db
def test_items_saving_each_other_are_stopped(calls, monkeypatch):
    first, second = make_booking(start=10, end=20), make_booking(start=30, end=40)
    validate_item = Booking.validate_item

    def validate_and_save_the_other(self, changes):
        validate_item(self, changes)
        Booking.objects.exclude(pk=self.pk).get().save()

    monkeypatch.setattr(Booking, 'validate_item', validate_and_save_the_other)

    with pytest.raises(ImproperlyConfigured, match='save each other'):
        first.save()
    assert {pk for pk, _ in calls} == {first.pk, second.pk}
