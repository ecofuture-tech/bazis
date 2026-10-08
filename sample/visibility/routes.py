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

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase, RestrictedQsRouteMixin
from bazis.core.schemas.enums import CrudAccessAction, CrudApiAction
from bazis.core.schemas.fields import SchemaField, SchemaFields


class FolderRouteSet(JsonapiRouteBase):
    model = apps.get_model('visibility.Folder')


class TagRouteSet(RestrictedQsRouteMixin):
    """
    Hidden tags are not visible, locked tags cannot be changed. The relationships of the
    other routes to tags respect it.
    """

    model = apps.get_model('visibility.Tag')
    default_route = True

    @classmethod
    def restrict_queryset(cls, qs, access_action, user=None, **kwargs):
        # user is None (the route has no user) or anonymous without authentication
        if getattr(user, 'is_staff', False):
            return qs
        qs = qs.filter(is_hidden=False)
        if access_action == CrudAccessAction.CHANGE:
            qs = qs.filter(is_locked=False)
        return qs

    def get_queryset(self):
        return self.restrict_queryset(super().get_queryset(), CrudAccessAction.VIEW)


class NoteRouteSet(JsonapiRouteBase):
    model = apps.get_model('visibility.Note')
    default_route = True
    search_fields = ['name', 'tag__name']

    fields = {
        None: SchemaFields(include={'attached_tags': None}),
    }


class NoteFrozenRouteSet(JsonapiRouteBase):
    """
    Another route of notes on which the folder and the tags are read-only in the update
    schema, as the field permissions of bazis-permit (`readonly`) make them.
    """

    model = apps.get_model('visibility.Note')

    fields = {
        CrudApiAction.UPDATE: SchemaFields(
            include={
                'folder': SchemaField(source='folder', read_only=True),
                'tags': SchemaField(source='tags', read_only=True),
            },
        ),
    }

    @classmethod
    def get_url_prefix(cls) -> str:
        return '/visibility/note_frozen'


class NoteBriefRouteSet(JsonapiRouteBase):
    """
    A projection of the notes without their name and label, as a calendar shows the
    occupancy of the rooms without the topics of the bookings of the others: the filter,
    the sorting and the search of its requests do not reach them. Read-only: it has only
    the actions it lists (not `action_dict_data`, which shows all the attributes).
    """

    model = apps.get_model('visibility.Note')
    actions = ['action_list', 'action_retrieve', 'action_schema_list', 'action_schema_retrieve']

    fields = {
        None: SchemaFields(origin={'folder': None, 'tag': None, 'tags': None}),
    }

    @classmethod
    def get_url_prefix(cls) -> str:
        return '/visibility/note_brief'
