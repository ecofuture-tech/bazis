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

from django.apps import apps

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas.enums import CrudApiAction
from bazis.core.schemas.fields import SchemaField, SchemaFields


class AttachmentRouteSet(JsonapiRouteBase):
    model = apps.get_model('catalog.Attachment')


class CategoryRouteSet(JsonapiRouteBase):
    """The names are changed by their columns of the languages."""

    model = apps.get_model('catalog.Category')
    search_fields = ['name']

    fields = {
        CrudApiAction.UPDATE: SchemaFields(include={'name_en': None, 'name_ru': None}),
    }


class MemoRouteSet(JsonapiRouteBase):
    """
    The code of a memo is set when it is created; the body is read-only on an update.
    """

    model = apps.get_model('catalog.Memo')

    fields = {
        None: SchemaFields(
            include={
                'cards': None,
                'cards_count': None,
                'number': None,
            },
        ),
        CrudApiAction.UPDATE: SchemaFields(
            exclude={'code': None},
            include={'body': SchemaField(source='body', read_only=True)},
        ),
    }


class CardRouteSet(JsonapiRouteBase):
    model = apps.get_model('catalog.Card')


class BusyMemoRouteSet(JsonapiRouteBase):
    """
    A report of the memos with cards: the list and the items of a route are its
    `get_queryset`, the route of a proxy model narrows them there.
    """

    model = apps.get_model('catalog.BusyMemo')
    actions = ['action_list', 'action_retrieve', 'action_schema_list', 'action_schema_retrieve']

    fields = {
        None: SchemaFields(origin={'title': None, 'cards_count': None}),
    }

    def get_queryset(self):
        return super().get_queryset().filter(cards__isnull=False).distinct()
