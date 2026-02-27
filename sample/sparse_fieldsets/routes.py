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
from bazis.core.schemas.fields import SchemaField, SchemaFields


class PeopleRouteSet(JsonapiRouteBase):
    model = apps.get_model('sparse_fieldsets.People')

    fields = {
        None: SchemaFields(
            include={
                'articles': None,
            },
        ),
    }


class CategoryRouteSet(JsonapiRouteBase):
    model = apps.get_model('sparse_fieldsets.Category')


class ArticleRouteSet(JsonapiRouteBase):
    model = apps.get_model('sparse_fieldsets.Article')

    fields: dict[str, SchemaField] = {
        None: SchemaFields(
            include={
                'author_detail': SchemaField(source='author_detail', required=False),
                'author_count': SchemaField(source='author_count', required=False),
                'some_count_property': SchemaField(source='some_count_property'),
                'some_cached_property': SchemaField(source='some_cached_property'),
            },
        ),
    }
