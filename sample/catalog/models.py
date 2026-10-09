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

from django.db import models
from django.utils.translation import gettext_lazy as _

from translated_fields import TranslatedFieldWithFallback

from bazis.core.models_abstract import JsonApiMixin, UniqNumberMixin
from bazis.core.utils.orm import FieldDynamic, calc_property


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


class BusyMemo(Memo):
    """The memos with cards: a report, a proxy model with a route of its own."""

    class Meta:
        proxy = True
