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
            },
        ),
    }
