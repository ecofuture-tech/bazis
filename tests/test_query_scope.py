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
schema of the route, and through a relation of the schema only
the objects the default route of the related model shows, with the fields of its schema.
`visibility.note_brief` is a route of the notes without their name and label; the route of
`visibility.Tag` hides the hidden tags.
"""

from django.db import models
from django.db.models import F, Subquery
from django.test.utils import isolate_apps

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.routes import AttachmentRouteSet, MemoRouteSet
from entity.models import ExtendedEntity, ParentEntity
from entity.routes import ParentEntityRouteSet
from visibility.models import Folder, Label, Note, Tag
from visibility.routes import FolderRouteSet, NoteBriefRouteSet, NoteRouteSet, TagRouteSet

from bazis.core.checks import check_filter_keys_ignored, check_search_fields
from bazis.core.utils.query_complex import QueryScope, QueryToOrm, route_search_fields

from tests import factories


NOTES = '/api/v1/visibility/note/'
BRIEF = '/api/v1/visibility/note_brief/'
FOLDERS = '/api/v1/visibility/folder/'
TAGS = '/api/v1/visibility/tag/'


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
def test_search_needs_text_fields(sample_app, data):
    """
    A route without `search_fields` searches the text fields of its LIST schema: the brief
    notes show none (only their relations), so a search there is 400, the same answer as
    with `search_fields = []`.
    """
    assert route_search_fields(NoteBriefRouteSet) == []
    error = assert_bad_request(get(sample_app, BRIEF, search='Secret'), 'search')
    assert error['detail'] == 'The search is not available for visibility.Note'
    assert_bad_request(get(sample_app, BRIEF, filter='$search=Secret'), 'filter')
    # no search, no error
    assert len(ids(sample_app, BRIEF, search=' ')) == 3


@pytest.mark.django_db(transaction=True)
def test_empty_search_fields_turn_the_search_off(sample_app, data, monkeypatch):
    monkeypatch.setattr(NoteRouteSet, 'search_fields', [])
    assert_bad_request(get(sample_app, NOTES, search='Secret'), 'search')
    assert_bad_request(get(sample_app, NOTES, filter='$search=Secret'), 'filter')
    assert_bad_request(get(sample_app, TAGS, filter='note__$search=plain'), 'filter')
    assert len(ids(sample_app, NOTES, search='')) == 3


@pytest.mark.django_db(transaction=True)
def test_search_by_default_searches_the_text_fields_of_the_schema(sample_app, data):
    """
    The folders declare no `search_fields`: `search` and `$search` search their text
    fields (name, code), every word in one of them.
    """
    folder = [str(data['folder'].pk)]
    other = Folder.objects.create(name='archive', code='box-7')
    assert route_search_fields(FolderRouteSet) == ['name', 'code']
    assert ids(sample_app, FOLDERS, search='FOLD') == folder
    assert ids(sample_app, FOLDERS, search='box') == [str(other.pk)]
    assert ids(sample_app, FOLDERS, search=f'arch {other.code}') == [str(other.pk)]
    assert ids(sample_app, FOLDERS, search='folder box') == []
    assert ids(sample_app, FOLDERS, filter='$search=fold') == folder
    assert len(ids(sample_app, FOLDERS, search=' , ')) == 2


@pytest.mark.django_db(transaction=True)
def test_search_by_default_through_a_relation(sample_app, data, monkeypatch):
    """
    `<relation>__$search` searches the search fields of the default route of the related
    model, by default its text fields, in the objects the user can see (the many-to-many
    `tags`: test_search_through_a_relation_reaches_only_visible_objects).
    """
    # the route of the tags declares no search fields: their name
    assert ids(sample_app, NOTES, filter='tag__$search=visib') == [str(data['plain'].pk)]
    # the hidden tag is not visible
    assert ids(sample_app, NOTES, filter='tag__$search=hidden') == []
    # the notes of the tags declare theirs (name, tag__name)
    assert ids(sample_app, TAGS, filter='note__$search=plain') == [str(data['tags']['visible'].pk)]
    monkeypatch.setattr(NoteRouteSet, 'search_fields', None)
    assert route_search_fields(NoteRouteSet) == ['name']
    assert ids(sample_app, TAGS, filter='note__$search=plain') == [str(data['tags']['visible'].pk)]
    assert ids(sample_app, NOTES, search='visible') == []


@pytest.mark.django_db(transaction=True)
def test_search_by_default_leaves_out_a_hidden_field(sample_app, data, monkeypatch):
    """
    A text field that the LIST schema does not show the user (a package narrows it per
    user, as bazis-permit) is not searched: its value finds nothing, and the search of the
    other fields is not an error.
    """
    other = Folder.objects.create(name='archive', code='box-7')
    query_fields = FolderRouteSet.query_fields.__func__

    def without_code(cls, user=None, **kwargs):
        return [it for it in query_fields(cls, user=user, **kwargs) if it.source != 'code']

    monkeypatch.setattr(FolderRouteSet, 'query_fields', classmethod(without_code))
    assert ids(sample_app, FOLDERS, search='box') == []
    assert ids(sample_app, FOLDERS, filter='$search=box') == []
    assert ids(sample_app, FOLDERS, search='arch') == [str(other.pk)]
    # without a text field left, no search
    monkeypatch.setattr(FolderRouteSet, 'query_fields', classmethod(lambda cls, **kw: []))
    assert_bad_request(get(sample_app, FOLDERS, search='arch'), 'search')


def test_default_search_fields_are_the_text_fields():
    """
    The text fields of the LIST schema in its order: not the primary key, the relations,
    the calculated fields, the fields with choices (status, kind), the numbers (mood,
    number), the UUID (ref) and array fields; `URLField` is a text field.
    """
    assert route_search_fields(MemoRouteSet) == ['title', 'body', 'code']
    assert route_search_fields(TagRouteSet) == ['name']
    assert route_search_fields(AttachmentRouteSet) == ['name', 'url']
    assert route_search_fields(ParentEntityRouteSet) == ['name', 'description']
    memo_fields = {it.source for it in MemoRouteSet.query_fields()}
    assert {'status', 'kind', 'mood', 'number', 'category', 'cards_count'} <= memo_fields
    assert 'ref' in {it.source for it in TagRouteSet.query_fields()}
    assert 'field' in {it.source for it in ParentEntityRouteSet.query_fields()}


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
    # the route of the tags declares no search fields: by default their name
    assert ids(sample_app, NOTES, filter='tags__$search=visible') == [str(data['plain'].pk)]
    assert ids(sample_app, NOTES, filter='tags__$search=hidden') == []


@pytest.mark.django_db(transaction=True)
def test_search_of_several_words(sample_app, data):
    """
    The words of `search` (split at spaces and commas) must each be in one of the search
    fields (name, tag__name), not all in the same one: a substring in any case of a field
    of the model, the whole value of a field through a relation.
    """
    plain = [str(data['plain'].pk)]
    assert ids(sample_app, NOTES, search='LAI visible') == plain
    assert ids(sample_app, NOTES, search='lai,visible') == plain
    assert ids(sample_app, NOTES, search='plain other') == []
    assert ids(sample_app, NOTES, search='lai isib') == []
    assert ids(sample_app, NOTES, search='secret topic') == [str(data['secret'].pk)]


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
    # not declared: the text fields of the LIST schema
    monkeypatch.setattr(NoteRouteSet, 'search_fields', None)
    assert route_search_fields(NoteRouteSet) == ['name']
    monkeypatch.setattr(NoteRouteSet, 'search_fields', [])
    assert route_search_fields(NoteRouteSet) == []


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


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_str, expected',
    [
        # the key alone, whatever its lookup and value
        ('dt_deleted=null', ['secret', 'plain', 'with_hidden']),
        ('dt_deleted__gt=2020-01-01', ['secret', 'plain', 'with_hidden']),
        ('dt_deleted__isnull=true', ['secret', 'plain', 'with_hidden']),
        ('dt_deleted__in=a,b', ['secret', 'plain', 'with_hidden']),
        ('dt_deleted__x__y=1', ['secret', 'plain', 'with_hidden']),
        # negated
        ('~dt_deleted=null', ['secret', 'plain', 'with_hidden']),
        ('~(dt_deleted__lt=2020-01-01)', ['secret', 'plain', 'with_hidden']),
        # with the other keys, which filter as without it
        ('folder={folder}&dt_deleted=null', ['secret']),
        ('dt_deleted=null&name=plain', ['plain']),
        ('~dt_deleted=null&name=plain', ['plain']),
        ('folder={folder}&dt_deleted__gte=2020-01-01&~name=plain', ['secret']),
        # left out of an `or` as well: not a condition that every object meets
        ('(name=plain|dt_deleted=null)', ['plain']),
    ],
)
def test_filter_keys_ignored(sample_app, data, filter_str, expected):
    """
    `filter_keys_ignored` of the route of the notes (`dt_deleted`, which the notes do not
    have): the filter of a request leaves the key out.
    """
    filter_str = filter_str.format(folder=data['folder'].pk)
    assert sorted(ids(sample_app, NOTES, filter=filter_str)) == sorted(
        str(data[it].pk) for it in expected
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'url, filter_str',
    [
        # after a relation into the notes, whose route leaves it out
        (TAGS, 'note__dt_deleted=null'),
        (TAGS, '~note__dt_deleted__gt=2020-01-01'),
        # another route of the notes
        (BRIEF, 'dt_deleted=null'),
        # a key that only starts the same
        (NOTES, 'dt_deleted_at=null'),
    ],
)
def test_filter_keys_ignored_only_of_the_route(sample_app, data, url, filter_str):
    assert_bad_request(get(sample_app, url, filter=filter_str), 'filter')


def test_filter_keys_ignored_only_in_the_filter_of_a_request():
    """The conditions of the code (no scope) and the other scopes do not leave it out."""
    with pytest.raises(ValueError, match="Unknown filter field 'dt_deleted'"):
        QueryToOrm('dt_deleted=null', Note)
    with pytest.raises(ValueError, match="Unknown filter field 'dt_deleted'"):
        QueryToOrm('dt_deleted=null', Note, scope=QueryScope(['name']))
    assert QueryScope.for_route(NoteRouteSet).filter_keys_ignored == {'dt_deleted'}


@pytest.mark.django_db(transaction=True)
def test_filter_keys_ignored_are_not_filter_fields(sample_app):
    response = get(sample_app, f'{NOTES}route_filter_fields/')
    assert response.status_code == 200, response.text
    names = {it['name'] for it in response.json()['fields']}
    assert 'name' in names
    assert 'dt_deleted' not in names


@pytest.mark.django_db(transaction=True)
def test_filter_keys_ignored_check(sample_app, monkeypatch):
    """A key of `filter_keys_ignored` that is a filter key of the route is bazis.E002."""
    assert check_filter_keys_ignored(None) == []
    monkeypatch.setattr(NoteRouteSet, 'filters_aliases', {'kind': 'folder__name'})
    monkeypatch.setattr(
        NoteRouteSet, 'filter_keys_ignored', frozenset({'dt_deleted', 'name', 'pk', 'kind'})
    )
    errors = check_filter_keys_ignored(None)
    assert {it.id for it in errors} == {'bazis.E002'}
    assert {it.obj for it in errors} == {'visibility.routes.NoteRouteSet'}
    assert [it.msg.split("'")[1] for it in errors] == ['kind', 'name', 'pk']
