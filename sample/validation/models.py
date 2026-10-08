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
Models of the tests of `JsonApiMixin.validate_item`: a booking of a room must not overlap
another booking of the room and must not have more participants than the room has seats.
"""

from django.core.exceptions import ValidationError
from django.db import models

from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin


class Room(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField('Name', max_length=255)
    seats = models.PositiveIntegerField('Seats', default=2)


class Person(DtMixin, UuidMixin, JsonApiMixin):
    """A model that does not validate its items."""

    name = models.CharField('Name', max_length=255)


class Booking(DtMixin, UuidMixin, JsonApiMixin):
    title = models.CharField('Title', max_length=255)
    start = models.IntegerField('Start')
    end = models.IntegerField('End')
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings'
    )
    participants = models.ManyToManyField(Person, blank=True, related_name='bookings')

    #: the calls of validate_item, for the tests: (pk, changes)
    calls = []

    def validate_item(self, changes):
        self.calls.append((self.pk, changes))
        errors = {}
        if self.end <= self.start:
            errors['end'] = 'The booking must end after it starts'
        if (
            self.room_id
            and Booking.objects.filter(room_id=self.room_id, start__lt=self.end, end__gt=self.start)
            .exclude(pk=self.pk)
            .exists()
        ):
            errors['room'] = 'The room is booked at this time'
        if self.room_id and self.participants.count() > self.room.seats:
            errors['participants'] = 'The room has fewer seats'
        if errors:
            raise ValidationError(errors)


class Equipment(DtMixin, UuidMixin, JsonApiMixin):
    """
    Validates its items without a rule: a foreign key that cannot be null and a
    many-to-many relation without a reverse one (`related_name='+'`).
    """

    name = models.CharField('Name', max_length=255)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='equipment')
    keepers = models.ManyToManyField(Person, blank=True, related_name='+')

    #: the calls of validate_item, for the tests: (pk, changes)
    calls = []

    def validate_item(self, changes):
        self.calls.append((self.pk, changes))
