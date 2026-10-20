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

from pydantic import BaseModel

from bazis.core.routes_abstract.initial import http_post
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
        CrudApiAction.UPDATE: SchemaFields(
            include={'name_en': None, 'name_ru': None, 'scope_en': None, 'scope_ru': None}
        ),
    }


class SubscribeRequest(BaseModel):
    email: str


class SubscribeResponse(BaseModel):
    id: int


class MemoRouteSet(JsonapiRouteBase):
    """
    The code of a memo is set when it is created; the body is read-only on an update. A
    guest subscribes to a memo by an action.
    """

    model = apps.get_model('catalog.Memo')

    fields = {
        None: SchemaFields(
            include={
                'cards': None,
                'cards_count': None,
                'headline': None,
                'number': None,
            },
        ),
        CrudApiAction.UPDATE: SchemaFields(
            exclude={'code': None},
            include={'body': SchemaField(source='body', read_only=True)},
        ),
    }

    @http_post('/{item_id}/subscribe/', response_model=SubscribeResponse, public=True)
    def action_subscribe(self, item_id: str, data: SubscribeRequest, **kwargs):
        """
        A guest subscribes to a memo: the memo is locked first (as an action that checks
        its item), then the reader is created.
        """
        memo = self.set_item(item_id, with_lock=True)
        reader = apps.get_model('catalog.Reader').objects.create(memo=memo, email=data.email)
        return SubscribeResponse(id=reader.pk)

    @http_post('/{item_id}/normalize/', response_model=SubscribeResponse)
    def action_normalize(self, item_id: str, **kwargs):
        """
        The e-mails of the readers of a memo in lower case: the memo is locked, then each
        reader is saved (a write of the parent, then of its children).
        """
        memo = self.set_item(item_id, with_lock=True)
        for reader in memo.readers.order_by('pk'):
            reader.email = reader.email.lower()
            reader.save()
        return SubscribeResponse(id=memo.pk)


class CardRouteSet(JsonapiRouteBase):
    model = apps.get_model('catalog.Card')


class StepRouteSet(JsonapiRouteBase):
    model = apps.get_model('catalog.Step')


class ReaderRouteSet(JsonapiRouteBase):
    model = apps.get_model('catalog.Reader')

    @http_post('/{item_id}/rename/', response_model=SubscribeResponse)
    def action_rename(self, item_id: str, data: SubscribeRequest, **kwargs):
        """
        A new e-mail of a reader: an action of the item, which takes it locked (as the
        actions bazis-permit checks); its memo is locked first (lock_on_write).
        """
        reader = self.set_item(item_id, with_lock=True)
        reader.email = data.email
        reader.save()
        return SubscribeResponse(id=reader.pk)


class BusyMemoRouteSet(JsonapiRouteBase):
    """
    A report of the memos with cards: the list and the items of a route are its
    `get_queryset`, the route of a proxy model narrows them there.
    """

    model = apps.get_model('catalog.BusyMemo')
    actions = ['action_list', 'action_retrieve', 'action_schema_list', 'action_schema_retrieve']

    fields = {
        None: SchemaFields(origin={'title': None, 'cards_count': None, 'first_card': None}),
    }

    def get_queryset(self):
        return super().get_queryset().filter(cards__isnull=False).distinct()
