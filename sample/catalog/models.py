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

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, OuterRef, Subquery
from django.utils.translation import gettext_lazy as _

from translated_fields import TranslatedFieldWithFallback

from bazis.core.models_abstract import JsonApiMixin, UniqNumberMixin
from bazis.core.utils.orm import FieldAnnotate, FieldDynamic, calc_property


class Attachment(JsonApiMixin):
    name = models.CharField('Name', max_length=255)


class Category(JsonApiMixin):
    """Reference data named in every language of the project."""

    name = TranslatedFieldWithFallback(
        models.CharField(_('Name'), max_length=100),
        languages=['en', 'ru'],
    )

    def __str__(self):
        return self.name


class Memo(UniqNumberMixin, JsonApiMixin):
    """A memo numbered in the order of its creation (`number`)."""

    title = models.CharField('Title', max_length=255)
    body = models.TextField('Body', blank=True, default='')
    code = models.CharField('Code', max_length=20, blank=True, default='')
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

    memo = models.ForeignKey(Memo, on_delete=models.CASCADE, related_name='steps')
    number = models.PositiveIntegerField('Number', editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['memo', 'number'], name='catalog_step_number_uniq')
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.number:
            # the number under the lock of the memo (validate_item runs after the save)
            Memo.objects.select_for_update().get(pk=self.memo_id)
            last = self.memo.steps.aggregate(m=Max('number'))['m'] or 0
            self.number = last + 1
        super().save(*args, **kwargs)

    def validate_item(self, changes):
        if changes.is_new:
            Memo.objects.select_for_update().get(pk=self.memo_id)
            # the item is already in the database: it is counted
            if self.memo.steps.count() > self.MAX_PER_MEMO:
                raise ValidationError({'memo': 'No more steps in this memo'})


class BusyMemo(Memo):
    """The memos with cards: a report, a proxy model with a route of its own."""

    class Meta:
        proxy = True
