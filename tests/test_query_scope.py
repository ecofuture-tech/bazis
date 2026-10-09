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
The filter, the sorting and the search of a request reach only the fields of the LIST
schema of the route (`BAZIS_FILTERS_STRICT`), and through a relation of the schema only
the objects the default route of the related model shows, with the fields of its schema.
`visibility.note_brief` is a route of the notes without their name and label; the route of
`visibility.Tag` hides the hidden tags.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Subquery
from django.test.utils import isolate_apps

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import ExtendedEntity, ParentEntity
from visibility.models import Folder, Label, Note, Tag
from visibility.routes import NoteBriefRouteSet, NoteRouteSet, TagRouteSet

from bazis.core.checks import check_filters_strict, check_search_fields
from bazis.core.utils.query_complex import QueryScope, QueryToOrm, route_search_fields

from tests import factories


NOTES = '/api/v1/visibility/note/'
BRIEF = '/api/v1/visibility/note_brief/'
FOLDERS = '/api/v1/visibility/folder/'


@pytest.fixture
def data(db):
    folder = Folder.objects.create(name='folder')
    label = Label.objects.create(name='label')
    tags = {
        'visible': Tag.objects.create(name='visible'),
        'other': Tag.objects.create(name='other'),
        'hidden': Tag.objects.create(name='hidden', is_hidden=True),
    }
    secret = Note.objects.create(name='Secret topic', folder=folder, label=label)
    plain = Note.objects.create(name='plain', tag=tags['visible'])
    with_hidden = Note.objects.create(name='third', tag=tags['hidden'])
    with_hidden.tags.add(tags['hidden'])
    plain.tags.add(tags['visible'])
    tags['hidden'].note = with_hidden
    tags['hidden'].save()
    tags['visible'].note = plain
    tags['visible'].save()
    return {
        'folder': folder,
        'label': label,
        'tags': tags,
        'secret': secret,
        'plain': plain,
        'with_hidden': with_hidden,
    }


def get(sample_app, url, **params):
    return get_api_client(sample_app).get(url, params=params)


def ids(sample_app, url, **params):
    response = get(sample_app, url, **params)
    assert response.status_code == 200, response.text
    return [it['id'] for it in response.json()['data']]


def assert_bad_request(response, loc):
    assert response.status_code == 400, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_FILTER'
    assert error['source'] == {'pointer': f'/query/{loc}'}
    return error


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_str',
    [
        'name=Secret topic',
        'name__isnull=false',
        'name__$search=Secret',
        '$search=Secret',
        # a relation that is not in the schema of the route
        'label__name=label',
        'label__exists=true',
        'visibility.label={label}',
    ],
)
def test_filter_out_of_the_schema(sample_app, data, filter_str):
    response = get(sample_app, BRIEF, filter=filter_str.format(label=data['label'].pk))
    assert_bad_request(response, 'filter')


@pytest.mark.django_db(transaction=True)
def test_hidden_field_is_answered_as_unknown(sample_app, data):
    """The answer does not tell a hidden field from a field that does not exist."""
    hidden = assert_bad_request(get(sample_app, BRIEF, filter='name=x'), 'filter')
    unknown = assert_bad_request(get(sample_app, BRIEF, filter='nonexistent=x'), 'filter')
    assert hidden['detail'] == unknown['detail'].replace('nonexistent', 'name')


@pytest.mark.django_db(transaction=True)
def test_search_needs_search_fields(sample_app, data):
    assert_bad_request(get(sample_app, BRIEF, search='Secret'), 'search')
    # no search, no error
    assert len(ids(sample_app, BRIEF, search=' ')) == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('sort', ['name', '-name', 'label', 'label__name', 'dt_created', 'tags'])
def test_sort_out_of_the_schema(sample_app, data, sort):
    assert_bad_request(get(sample_app, BRIEF, sort=sort), 'sort')


@pytest.mark.django_db(transaction=True)
def test_fields_of_the_schema(sample_app, data):
    assert ids(sample_app, BRIEF, filter='tag__name=visible') == [str(data['plain'].pk)]
    assert ids(sample_app, BRIEF, filter='folder__name=folder') == [str(data['secret'].pk)]
    assert ids(sample_app, BRIEF, filter=f'id={data["plain"].pk}') == [str(data['plain'].pk)]
    # the items of a resource by their primary keys (bazis-front)
    assert ids(sample_app, BRIEF, filter=f'pk={data["plain"].pk}', sort='-pk') == [
        str(data['plain'].pk)
    ]
    assert ids(sample_app, BRIEF, filter=f'folder__pk={data["folder"].pk}') == [
        str(data['secret'].pk)
    ]
    assert len(ids(sample_app, BRIEF, sort='-tag')) == 3


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_str',
    [
        'tags__name=hidden',
        'tags__is_hidden=true',
        'tag__name=hidden',
        'attached_tags__name=hidden',
        'tags__name__$search=hidden',
        'visibility.tag={hidden}',
    ],
)
def test_relation_reaches_only_visible_objects(sample_app, data, filter_str):
    filter_str = filter_str.format(hidden=data['tags']['hidden'].pk)
    assert ids(sample_app, NOTES, filter=filter_str) == []
    visible = filter_str.replace('hidden', 'visible').replace('is_visible=true', 'is_hidden=false')
    visible = visible.replace(str(data['tags']['hidden'].pk), str(data['tags']['visible'].pk))
    assert ids(sample_app, NOTES, filter=visible) == [str(data['plain'].pk)]


@pytest.mark.django_db(transaction=True)
def test_relation_exists_counts_only_visible_objects(sample_app, data):
    assert ids(sample_app, NOTES, filter='tags__exists=true') == [str(data['plain'].pk)]
    assert set(ids(sample_app, NOTES, filter='tags__exists=false')) == {
        str(data['secret'].pk),
        str(data['with_hidden'].pk),
    }


@pytest.mark.django_db(transaction=True)
def test_search_through_a_relation_reaches_only_visible_objects(sample_app, data):
    # the search fields of the route: name, tag__name
    assert ids(sample_app, NOTES, search='Secret') == [str(data['secret'].pk)]
    assert ids(sample_app, NOTES, search='visible') == [str(data['plain'].pk)]
    # the tag of the third note is hidden
    assert ids(sample_app, NOTES, search='hidden') == []
    assert ids(sample_app, NOTES, filter='$search=visible') == [str(data['plain'].pk)]
    # the route of the tags has no search fields
    assert_bad_request(get(sample_app, NOTES, filter='tags__$search=visible'), 'filter')


@pytest.mark.django_db(transaction=True)
def test_sort_through_a_relation_hides_invisible_objects(sample_app, data):
    data['plain'].tag = data['tags']['other']
    data['plain'].save()
    visible = Note.objects.create(name='visible tag', tag=data['tags']['visible'])
    # the hidden tag sorts as no tag (nulls last): its name `hidden` would come first
    order = ids(sample_app, NOTES, sort='tag__name')
    assert order[:2] == [str(data['plain'].pk), str(visible.pk)]
    assert set(order[2:]) == {str(data['secret'].pk), str(data['with_hidden'].pk)}
    order = ids(sample_app, NOTES, sort='-tag__name')
    assert order[:2] == [str(visible.pk), str(data['plain'].pk)]


def ordered_ids(qs, key: str, descending: bool) -> list[str]:
    order = F(key).desc(nulls_last=True) if descending else F(key).asc(nulls_last=True)
    return [str(pk) for pk in qs.order_by(order, 'pk').values_list('pk', flat=True)]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('sort', ['tag', '-tag'])
def test_sort_by_a_relation_uses_its_key(sample_app, data, monkeypatch, sort):
    """
    Not by the Meta.ordering of the related model, through a join no restriction applies
    to: it would sort by the names of the hidden tags.
    """
    monkeypatch.setattr(Tag._meta, 'ordering', ['name'])
    Note.objects.create(name='fourth', tag=data['tags']['other'])
    # the names in the reverse order of the keys
    for tag, name in zip(Tag.objects.order_by('pk'), ['c', 'b', 'a'], strict=True):
        Tag.objects.filter(pk=tag.pk).update(name=name)
    expected = ordered_ids(Note.objects.all(), 'tag_id', sort.startswith('-'))
    assert ids(sample_app, NOTES, sort=sort) == expected


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('sort', ['extended_entity', '-extended_entity'])
def test_sort_by_a_reverse_one_to_one_uses_its_key(sample_app, monkeypatch, sort):
    monkeypatch.setattr(ExtendedEntity._meta, 'ordering', ['extended_name'])
    factories.ParentEntityFactory.create_batch(3, child_entities=False)
    for ext, name in zip(ExtendedEntity.objects.order_by('pk'), 'cba', strict=True):
        ExtendedEntity.objects.filter(pk=ext.pk).update(extended_name=name)
    expected = ordered_ids(ParentEntity.objects.all(), 'extended_entity__pk', sort.startswith('-'))
    assert ids(sample_app, '/api/v1/entity/parent_entity/', sort=sort) == expected


@pytest.mark.django_db(transaction=True)
def test_sort_through_an_unrestricted_relation_is_a_join(sample_app, data):
    """A subquery per row only when the related model is restricted."""
    scope = QueryScope.for_route(NoteRouteSet)
    assert scope.order_expression(Note, 'folder__name') == F('folder__name')
    assert isinstance(scope.order_expression(Note, 'tag__name'), Subquery)
    assert ids(sample_app, NOTES, sort='folder__name')[0] == str(data['secret'].pk)
    # the notes without a folder are last in both orders
    assert ids(sample_app, NOTES, sort='-folder__name')[0] == str(data['secret'].pk)


@isolate_apps('visibility')
def test_sort_by_a_key_of_a_child_model_is_a_column():
    """
    The primary key of a child model of a multi-table inheritance links to its parent:
    sorting by it would apply the Meta.ordering of the parent (its secret) through a join.
    """

    class Secret(models.Model):
        secret = models.CharField(max_length=10)

        class Meta:
            app_label = 'visibility'
            ordering = ['secret']

    class Holder(models.Model):
        class Meta:
            app_label = 'visibility'

    class SecretChild(Secret):
        holder = models.OneToOneField(Holder, models.CASCADE, related_name='secret_child')

        class Meta:
            app_label = 'visibility'

    def order_sql(model, scope, path):
        expr = scope.order_expression(model, path)
        sql = str(model.objects.order_by(expr.name).query)
        return sql[sql.index('ORDER BY') :]

    for path in ('pk', 'secret_ptr'):
        assert order_sql(SecretChild, QueryScope(), path) == (
            'ORDER BY "visibility_secretchild"."secret_ptr_id" ASC'
        )
    # a reverse one-to-one into the child model
    assert order_sql(Holder, QueryScope(order_fields={'secret_child'}), 'secret_child') == (
        'ORDER BY "visibility_secretchild"."secret_ptr_id" ASC'
    )


@pytest.mark.django_db(transaction=True)
def test_reverse_relation_out_of_the_schema(sample_app, data):
    """A reverse relation is not in the schema by default: no way to the notes of a folder."""
    assert_bad_request(get(sample_app, FOLDERS, filter='notes__name=Secret topic'), 'filter')
    assert_bad_request(get(sample_app, FOLDERS, sort='notes__name'), 'sort')


@pytest.mark.django_db(transaction=True)
def test_search_field_out_of_the_schema_is_left_out(sample_app, data, monkeypatch):
    monkeypatch.setattr(NoteBriefRouteSet, 'search_fields', ['name'])
    assert_bad_request(get(sample_app, BRIEF, search='Secret'), 'search')
    warnings = [it for it in check_search_fields(None) if it.id == 'bazis.W007']
    assert [it.obj for it in warnings] == ['visibility.routes.NoteBriefRouteSet']


@pytest.mark.django_db(transaction=True)
def test_search_field_through_a_relation_is_checked_to_the_end(sample_app, monkeypatch):
    assert [it for it in check_search_fields(None) if it.id == 'bazis.W007'] == []
    monkeypatch.setattr(NoteRouteSet, 'search_fields', ['name', 'tag__nonexistent'])
    warnings = [it for it in check_search_fields(None) if it.id == 'bazis.W007']
    assert [it.obj for it in warnings] == ['visibility.routes.NoteRouteSet']
    assert "'tag__nonexistent'" in warnings[0].msg


def test_route_search_fields(monkeypatch):
    """
    The search fields a route searches (the ones W007 does not report), as declared: with
    their lookup prefix, through a relation only into the LIST schema of the default route
    of the related model.
    """
    assert route_search_fields(NoteRouteSet) == ['name', 'tag__name']
    monkeypatch.setattr(
        NoteRouteSet, 'search_fields', ['^name', 'folder__name', 'tag__nonexistent', 'missing']
    )
    assert route_search_fields(NoteRouteSet) == ['^name', 'folder__name']
    monkeypatch.setattr(NoteBriefRouteSet, 'search_fields', ['name'])
    assert route_search_fields(NoteBriefRouteSet) == []
    monkeypatch.setattr(NoteBriefRouteSet, 'search_fields', [])
    assert route_search_fields(NoteBriefRouteSet) == []


@pytest.mark.django_db(transaction=True)
def test_search_fields_check_uses_the_schemas_of_the_routes(
    sample_app, monkeypatch, django_assert_num_queries
):
    """
    Not the fields a package gives per user (bazis-permit: by the roles of the anonymous
    user, from the database): the check runs no queries and does not depend on them.
    """

    def no_fields(cls, user=None, **kwargs):
        return []

    monkeypatch.setattr(TagRouteSet, 'query_fields', classmethod(no_fields))
    monkeypatch.setattr(NoteRouteSet, 'query_fields', classmethod(no_fields))
    # the search fields of the notes: name, tag__name
    with django_assert_num_queries(0):
        assert [it for it in check_search_fields(None) if it.id == 'bazis.W007'] == []


@pytest.mark.django_db(transaction=True)
def test_strict_off_restores_the_unrestricted_query(sample_app, data, monkeypatch):
    assert check_filters_strict(None) == []
    monkeypatch.setattr(settings, 'BAZIS_FILTERS_STRICT', False)
    assert [it.id for it in check_filters_strict(None)] == ['bazis.W006']

    secret = [str(data['secret'].pk)]
    assert ids(sample_app, BRIEF, filter='name=Secret topic') == secret
    assert ids(sample_app, BRIEF, search='Secret') == secret
    assert ids(sample_app, BRIEF, filter='label__name=label') == secret
    assert ids(sample_app, NOTES, filter='tags__name=hidden') == [str(data['with_hidden'].pk)]
    assert ids(sample_app, NOTES, search='hidden') == [str(data['with_hidden'].pk)]
    assert len(ids(sample_app, BRIEF, sort='name')) == 3


@pytest.mark.django_db(transaction=True)
def test_query_without_a_scope_traverses_relations_unrestricted(data):
    """
    The default contract of QueryToOrm (no scope) for the conditions of the code: the
    permissions of bazis-permit (selectors through m2m and reverse relations) reach the
    related objects whatever the default route of the related model shows.
    """
    with_hidden = [data['with_hidden']]
    for cond in ('tags__name=hidden', 'attached_tags__is_hidden=true', 'tag__name=hidden'):
        assert list(QueryToOrm.qs_apply(Note.objects.all(), cond)) == with_hidden
    by_type = f'visibility.tag={data["tags"]["hidden"].pk}'
    assert list(QueryToOrm.qs_apply(Note.objects.all(), by_type)) == with_hidden
    # the same conditions with the scope of a request see only the visible tags
    scope = QueryScope.for_route(NoteRouteSet)
    assert not QueryToOrm.qs_apply(Note.objects.all(), 'tags__name=hidden', scope=scope).exists()


def test_query_without_a_scope_is_not_restricted():
    """The conditions of the code (permissions, `filter:` restrictions) use any field."""
    assert QueryToOrm('name=x&child_entities__child_name=y', ParentEntity).q
    with pytest.raises(ValueError, match="Unknown filter field 'name'"):
        QueryToOrm('name=x', ParentEntity, scope=QueryScope())


def test_filters_aliases_are_not_scoped():
    """An alias of the route is its own filter; the relation it leads to stays scoped."""
    aliases = {'title': 'name', 'kids': 'child_entities'}
    scope = QueryScope()
    assert QueryToOrm('title=x', ParentEntity, aliases, scope=scope).q
    assert QueryToOrm('kids__exists=true', ParentEntity, aliases, scope=scope).q
    # the fields of the default route of the child entities
    assert QueryToOrm('kids__child_name=x', ParentEntity, aliases, scope=scope).q
    with pytest.raises(ValueError, match="Unknown filter field 'nonexistent'"):
        QueryToOrm('kids__nonexistent=x', ParentEntity, aliases, scope=scope)
