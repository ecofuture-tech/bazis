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
Models of a catalog of memos with integer keys: relations without a reverse one
(`related_name='+'`) of every kind, an aggregate over a model with a default ordering, text
fields that must not be blank and reference data translated into the languages of the
project.
"""

from enum import Enum

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, OuterRef, Subquery
from django.utils.translation import gettext_lazy as _

from translated_fields import TranslatedField, TranslatedFieldWithFallback

from bazis.core.models_abstract import JsonApiMixin, UniqNumberMixin
from bazis.core.utils.django_types import TYPES_DJANGO_TO_SCHEMA
from bazis.core.utils.orm import FieldAnnotate, FieldDynamic, calc_property


class MemoStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SENT = 'sent', 'Sent'


def memo_kinds():
    """Callable choices of a field, in groups."""
    return [('Work', [('task', 'Task'), ('meeting', 'Meeting')]), ('idea', 'Idea')]


class Tone(Enum):
    """A tone of a memo: an object of its code, which the database and the API hold."""

    WARM = 'warm'
    COLD = 'cold'


class ToneField(models.CharField):
    """
    A CharField of the codes of the tones, whose value is the `Tone`. Its schema type is
    `Tone` (`TYPES_DJANGO_TO_SCHEMA`, as `GeoJson` of a geometry field): a request sends the
    code, the schema makes the object of it, a response shows the code.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 10)
        kwargs.setdefault('choices', [(tone.value, tone.name.title()) for tone in Tone])
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return Tone(value) if value else value

    def get_prep_value(self, value):
        return super().get_prep_value(value.value if isinstance(value, Tone) else value)


TYPES_DJANGO_TO_SCHEMA[ToneField] = Tone


class Attachment(JsonApiMixin):
    """A file of a memo, or a link to it (`url`: a URL of http, https, ftp or ftps)."""

    name = models.CharField('Name', max_length=255)
    url = models.URLField('URL', blank=True)


class Category(JsonApiMixin):
    """Reference data named in every language of the project."""

    name = TranslatedFieldWithFallback(
        models.CharField(_('Name'), max_length=100),
        languages=['en', 'ru'],
    )
    scope = TranslatedField(
        models.CharField(max_length=10, choices=MemoStatus, blank=True, default=''),
        languages=['en', 'ru'],
    )

    def __str__(self):
        return self.name


class Memo(UniqNumberMixin, JsonApiMixin):
    """A memo numbered in the order of its creation (`number`)."""

    title = models.CharField('Title', max_length=255)
    body = models.TextField('Body', blank=True, default='')
    code = models.CharField('Code', max_length=20, blank=True, default='')
    status = models.CharField('Status', max_length=10, choices=MemoStatus, default=MemoStatus.DRAFT)
    # callable and grouped choices, the value is optional
    kind = models.CharField('Kind', max_length=10, choices=memo_kinds, null=True, blank=True)
    # integer choices, null but not blank
    mood = models.IntegerField('Mood', choices=[(1, 'Bad'), (2, 'Good')], null=True)
    # choices of a field whose schema type makes an object of the code
    tone = ToneField('Tone', null=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='memos'
    )
    attachment = models.ForeignKey(
        Attachment, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    cover = models.OneToOneField(
        Attachment, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    extras = models.ManyToManyField(Attachment, blank=True, related_name='+')

    @calc_property([FieldDynamic(source='cards', func='Count', alias='cards_count')])
    def cards_count(self) -> int:
        return self.cards_count

    # a callable: its expression needs `Card`, which is declared below
    @calc_property(
        [
            lambda: FieldAnnotate(
                source='first_card',
                query=Subquery(Card.objects.filter(memo=OuterRef('pk')).values('name')[:1]),
            )
        ]
    )
    def first_card(self) -> str | None:
        return self.first_card

    # nothing to fetch: computed from the fields of the item
    @calc_property([])
    def headline(self) -> str:
        return f'{self.title} ({self.code})' if self.code else self.title


class Card(JsonApiMixin):
    """A model with a default ordering, counted by the memos."""

    name = models.CharField('Name', max_length=255)
    memo = models.ForeignKey(
        Memo, null=True, blank=True, on_delete=models.CASCADE, related_name='cards'
    )
    attachment = models.ForeignKey(
        Attachment, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        ordering = ['name']


class Step(JsonApiMixin):
    """
    The recipe of the guide for an invariant under concurrent requests: no more than
    MAX_PER_MEMO steps per memo, numbered in the memo, under the lock of the memo, with a
    unique constraint as the barrier.
    """

    MAX_PER_MEMO = 3
    lock_on_write = ('memo',)

    memo = models.ForeignKey(Memo, on_delete=models.CASCADE, related_name='steps')
    number = models.PositiveIntegerField('Number', editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['memo', 'number'], name='catalog_step_number_uniq')
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.number:
            # the number is taken before the write: under the lock lock_on_write takes
            # later, taken here already
            Memo.objects.select_for_update(no_key=True).get(pk=self.memo_id)
            last = self.memo.steps.aggregate(m=Max('number'))['m'] or 0
            self.number = last + 1
        super().save(*args, **kwargs)

    def validate_item(self, changes):
        if changes.is_new:
            # under the lock of the memo (lock_on_write); the item is in the database
            # already: it is counted
            if self.memo.steps.count() > self.MAX_PER_MEMO:
                raise ValidationError({'memo': 'No more steps in this memo'})


class Reader(JsonApiMixin):
    """
    The recipe of the guide for a limit counted in `validate_item` under the lock of the
    parent: no more than MAX_PER_MEMO readers per memo, each e-mail once per memo (a unique
    constraint). The memo is locked before every write of a reader (`lock_on_write`), so a
    create runs in the order of the action that locks the memo first and then adds a
    reader (`MemoRouteSet.action_subscribe`): no deadlock between them.
    """

    MAX_PER_MEMO = 3
    lock_on_write = ('memo',)

    memo = models.ForeignKey(Memo, on_delete=models.CASCADE, related_name='readers')
    email = models.CharField('E-mail', max_length=254)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['memo', 'email'], name='catalog_reader_email_uniq')
        ]

    def validate_item(self, changes):
        if changes.is_new or 'memo' in changes.fields:
            # under the lock of the memo (lock_on_write); the item is in the database
            # already: it is counted
            if Reader.objects.filter(memo=self.memo_id).count() > self.MAX_PER_MEMO:
                raise ValidationError({'memo': 'No more readers of this memo'})


class BusyMemo(Memo):
    """The memos with cards: a report, a proxy model with a route of its own."""

    class Meta:
        proxy = True


class Upload(JsonApiMixin):
    """A file of a form: its route set uploads and shows a file, it has no list."""

    name = models.CharField('Name', max_length=255)


class Form(JsonApiMixin):
    """A form with an uploaded file: a relation to a model whose route set has no list."""

    title = models.CharField('Title', max_length=255)
    upload = models.ForeignKey(
        Upload, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
