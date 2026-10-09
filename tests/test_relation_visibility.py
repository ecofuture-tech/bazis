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
A relationship can link only the objects the route of the related model shows
(`restrict_queryset` of its default route), and `included` shows only those objects.
The route of `visibility.Tag` hides the hidden tags and does not let change the locked ones.
"""

from django.contrib.auth.models import AnonymousUser, User

import pytest
from bazis_test_utils.utils import get_api_client
from visibility.models import Folder, Label, Note, Tag
from visibility.routes import NoteRouteSet, TagRouteSet

from bazis.core.schemas.enums import CrudAccessAction

from tests.utils.assert_sql import normalize_sql


NOTES = '/api/v1/visibility/note/'


def rel(type_, obj):
    return {'data': {'id': str(obj.id), 'type': f'visibility.{type_}'}}


def rels(type_, *objs):
    return {'data': [{'id': str(obj.id), 'type': f'visibility.{type_}'} for obj in objs]}


def note_payload(note=None, **relationships):
    data = {'type': 'visibility.note', 'relationships': relationships}
    if note is None:
        data['attributes'] = {'name': 'note'}
    else:
        data['id'] = str(note.id)
    return {'data': data}


def assert_relation_denied(response, field, pointer=None):
    """
    The pointer of a create or an update is the relationship in the document; the
    relationships endpoints point into their body, the `data` of the relationship (`pointer`).
    """
    assert response.status_code == 403, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_RELATION_ACCESS'
    assert error['source'] == {'pointer': pointer or f'/data/relationships/{field}'}


def relationships_request(client, method, note, field, payload):
    return client.client.request(
        method,
        f'{NOTES}{note.id}/relationships/{field}',
        headers=client.headers,
        json=payload,
    )


def pk_in_queries(table):
    """The `pk IN (...)` queries of the request to the table (the checks of the targets)."""
    with open('sql.log') as f:
        queries = [normalize_sql(line) for line in f]
    prefix = f'select "{table}"."id" as "pk" from "{table}" where'
    return [q for q in queries if prefix in q and f'"{table}"."id" in (' in q]


@pytest.fixture
def tags(db):
    return {
        'visible': Tag.objects.create(name='visible'),
        'visible2': Tag.objects.create(name='visible2'),
        'hidden': Tag.objects.create(name='hidden', is_hidden=True),
        'locked': Tag.objects.create(name='locked', is_locked=True),
    }


@pytest.mark.django_db(transaction=True)
def test_create_with_invisible_target(sample_app, tags):
    client = get_api_client(sample_app)

    response = client.post(NOTES, json_data=note_payload(tag=rel('tag', tags['hidden'])))
    assert_relation_denied(response, 'tag')

    response = client.post(
        NOTES, json_data=note_payload(tags=rels('tag', tags['visible'], tags['hidden']))
    )
    assert_relation_denied(response, 'tags')
    assert not Note.objects.exists()

    response = client.post(
        NOTES,
        json_data=note_payload(
            tag=rel('tag', tags['visible']), tags=rels('tag', tags['visible'], tags['visible2'])
        ),
    )
    assert response.status_code == 201, response.text
    note = Note.objects.get()
    assert note.tag == tags['visible']
    assert set(note.tags.all()) == {tags['visible'], tags['visible2']}


@pytest.mark.django_db(transaction=True)
def test_update_with_invisible_target(sample_app, tags):
    note = Note.objects.create(name='note', tag=tags['visible'])
    note.tags.add(tags['visible'])
    client = get_api_client(sample_app)

    response = client.patch(
        f'{NOTES}{note.id}/', json_data=note_payload(note, tag=rel('tag', tags['hidden']))
    )
    assert_relation_denied(response, 'tag')

    response = client.patch(
        f'{NOTES}{note.id}/',
        json_data=note_payload(note, tags=rels('tag', tags['visible'], tags['hidden'])),
    )
    assert_relation_denied(response, 'tags')

    note.refresh_from_db()
    assert note.tag == tags['visible']
    assert list(note.tags.all()) == [tags['visible']]


@pytest.mark.django_db(transaction=True)
def test_update_keeps_and_removes_invisible_links(sample_app, tags):
    """Only the newly linked objects are checked: an invisible linked object can stay or go."""
    note = Note.objects.create(name='note', tag=tags['hidden'])
    note.tags.add(tags['hidden'])
    client = get_api_client(sample_app)

    # unchanged links
    response = client.patch(
        f'{NOTES}{note.id}/',
        json_data=note_payload(
            note,
            tag=rel('tag', tags['hidden']),
            tags=rels('tag', tags['hidden'], tags['visible']),
        ),
    )
    assert response.status_code == 200, response.text
    assert set(note.tags.all()) == {tags['hidden'], tags['visible']}

    # removing the links
    response = client.patch(
        f'{NOTES}{note.id}/', json_data=note_payload(note, tag={'data': None}, tags={'data': []})
    )
    assert response.status_code == 200, response.text
    note.refresh_from_db()
    assert note.tag is None
    assert not note.tags.exists()


@pytest.mark.django_db(transaction=True)
def test_relationships_endpoints_with_invisible_target(sample_app, tags):
    note = Note.objects.create(name='note')
    note.tags.add(tags['visible'])
    client = get_api_client(sample_app)

    for method in ('POST', 'PATCH'):
        response = relationships_request(
            client, method, note, 'tags', rels('tag', tags['visible2'], tags['hidden'])
        )
        # the refused identifier
        assert_relation_denied(response, 'tags', '/data/1')
    assert list(note.tags.all()) == [tags['visible']]

    response = relationships_request(client, 'PATCH', note, 'tag', rel('tag', tags['hidden']))
    assert_relation_denied(response, 'tag', '/data')

    response = relationships_request(client, 'POST', note, 'tags', rels('tag', tags['visible2']))
    assert response.status_code == 204, response.text
    assert set(note.tags.all()) == {tags['visible'], tags['visible2']}


@pytest.mark.django_db(transaction=True)
def test_relationships_endpoints_remove_invisible_link(sample_app, tags):
    note = Note.objects.create(name='note', tag=tags['hidden'])
    note.tags.add(tags['hidden'], tags['visible'])
    client = get_api_client(sample_app)

    response = relationships_request(client, 'DELETE', note, 'tags', rels('tag', tags['hidden']))
    assert response.status_code == 204, response.text
    assert list(note.tags.all()) == [tags['visible']]

    response = relationships_request(client, 'PATCH', note, 'tag', {'data': None})
    assert response.status_code == 204, response.text
    note.refresh_from_db()
    assert note.tag is None


@pytest.mark.django_db(transaction=True)
def test_reverse_relation_requires_change(sample_app, tags):
    """A reverse relationship changes the foreign key of the targets: they must be changeable."""
    note = Note.objects.create(name='note')
    tags['visible'].note = note
    tags['visible'].save()
    client = get_api_client(sample_app)

    # linking a locked (visible, not changeable) tag
    response = relationships_request(
        client, 'POST', note, 'attached_tags', rels('tag', tags['locked'])
    )
    assert_relation_denied(response, 'attached_tags', '/data/0')
    response = client.patch(
        f'{NOTES}{note.id}/',
        json_data=note_payload(
            note, attached_tags=rels('tag', tags['visible'], tags['locked'])
        ),
    )
    assert_relation_denied(response, 'attached_tags')
    tags['locked'].refresh_from_db()
    assert tags['locked'].note is None

    # unlinking a locked tag
    Tag.objects.filter(pk=tags['locked'].pk).update(note=note)
    response = relationships_request(
        client, 'DELETE', note, 'attached_tags', rels('tag', tags['locked'])
    )
    assert_relation_denied(response, 'attached_tags', '/data/0')
    tags['locked'].refresh_from_db()
    assert tags['locked'].note == note

    # replacing the linked tags unlinks the locked one
    for payload in (rels('tag', tags['visible2']), {'data': []}):
        response = relationships_request(client, 'PATCH', note, 'attached_tags', payload)
        # the unlinked tag is not in the body
        assert_relation_denied(response, 'attached_tags', '/data')
    assert set(note.attached_tags.all()) == {tags['visible'], tags['locked']}

    # linking a changeable tag
    response = relationships_request(
        client, 'POST', note, 'attached_tags', rels('tag', tags['visible2'])
    )
    assert response.status_code == 204, response.text
    tags['visible2'].refresh_from_db()
    assert tags['visible2'].note == note


@pytest.mark.django_db(transaction=True)
def test_unrestricted_targets_are_not_queried(sample_app, tags):
    """
    The targets of a model whose route does not restrict its objects (or that has no route)
    are not checked: no extra query.
    """
    folder = Folder.objects.create(name='folder')
    label = Label.objects.create(name='label')
    note = Note.objects.create(name='note')
    client = get_api_client(sample_app)

    response = client.patch(
        f'{NOTES}{note.id}/',
        json_data=note_payload(note, folder=rel('folder', folder), label=rel('label', label)),
    )
    assert response.status_code == 200, response.text
    note.refresh_from_db()
    assert (note.folder, note.label) == (folder, label)
    assert pk_in_queries('visibility_folder') == []
    assert pk_in_queries('visibility_label') == []

    # the restricted targets are checked with one query per relationship
    response = client.patch(
        f'{NOTES}{note.id}/',
        json_data=note_payload(note, tags=rels('tag', tags['visible'], tags['visible2'])),
    )
    assert response.status_code == 200, response.text
    assert len(pk_in_queries('visibility_tag')) == 1


@pytest.mark.django_db(transaction=True)
def test_check_ignores_permit_flag(sample_app, tags, monkeypatch):
    """
    bazis-permit (2.4.1) declares `relations_view_check = None` on its route base: it does
    not turn off the check of the core.
    """
    monkeypatch.setattr(NoteRouteSet, 'relations_view_check', None, raising=False)
    response = get_api_client(sample_app).post(
        NOTES, json_data=note_payload(tag=rel('tag', tags['hidden']))
    )
    assert_relation_denied(response, 'tag')


@pytest.mark.django_db(transaction=True)
def test_check_can_be_turned_off_per_route(sample_app, tags, monkeypatch):
    monkeypatch.setattr(NoteRouteSet, 'relation_targets_check', False)
    response = get_api_client(sample_app).post(
        NOTES, json_data=note_payload(tag=rel('tag', tags['hidden']))
    )
    assert response.status_code == 201, response.text


@pytest.mark.django_db(transaction=True)
def test_included_omits_invisible_objects(sample_app, tags):
    note = Note.objects.create(name='note', tag=tags['hidden'])
    note.tags.add(tags['visible'], tags['hidden'])

    response = get_api_client(sample_app).get(f'{NOTES}{note.id}/?include=tag,tags')
    assert response.status_code == 200, response.text
    data = response.json()

    # the identifiers stay in the relationships
    relationships = data['data']['relationships']
    assert relationships['tag']['data']['id'] == str(tags['hidden'].id)
    assert {it['id'] for it in relationships['tags']['data']} == {
        str(tags['visible'].id),
        str(tags['hidden'].id),
    }
    # only the visible objects are included
    assert [(it['type'], it['id']) for it in data['included']] == [
        ('visibility.tag', str(tags['visible'].id))
    ]


@pytest.mark.django_db(transaction=True)
def test_included_of_unrestricted_models(sample_app):
    folder = Folder.objects.create(name='folder')
    label = Label.objects.create(name='label')
    note = Note.objects.create(name='note', folder=folder, label=label)

    response = get_api_client(sample_app).get(f'{NOTES}{note.id}/?include=folder,label')
    assert response.status_code == 200, response.text
    assert {(it['type'], it['id']) for it in response.json()['included']} == {
        ('visibility.folder', str(folder.id)),
        ('visibility.label', str(label.id)),
    }


@pytest.mark.django_db(transaction=True)
def test_included_of_update_response_omits_invisible_objects(sample_app, tags):
    """The responses of create and update include the same way (a list has no `included`)."""
    note = Note.objects.create(name='note')
    note.tags.add(tags['hidden'])

    response = get_api_client(sample_app).patch(
        f'{NOTES}{note.id}/?include=tags',
        json_data=note_payload(note, tags=rels('tag', tags['hidden'], tags['visible'])),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data['data']['relationships']['tags']['data']) == 2
    assert [it['id'] for it in data['included']] == [str(tags['visible'].id)]


@pytest.fixture
def restrict_users(monkeypatch):
    """The `user` the core passes to the restrict_queryset of the route of tags."""
    users = []
    restrict = TagRouteSet.restrict_queryset.__func__

    def spy(cls, qs, access_action, user=None, **kwargs):
        users.append(user)
        return restrict(cls, qs, access_action, user=user, **kwargs)

    monkeypatch.setattr(TagRouteSet, 'restrict_queryset', classmethod(spy))
    return users


@pytest.mark.django_db(transaction=True)
def test_include_without_user(sample_app, tags, restrict_users):
    """A request without a user includes what a user without authentication may see."""
    note = Note.objects.create(name='note')
    note.tags.add(tags['visible'], tags['hidden'])

    response = get_api_client(sample_app).get(f'{NOTES}{note.id}/?include=tags')
    assert response.status_code == 200, response.text
    assert [it['id'] for it in response.json()['included']] == [str(tags['visible'].id)]
    assert restrict_users == [None]


@pytest.mark.django_db(transaction=True)
def test_route_without_user_links_restricted_target(sample_app, tags, restrict_users):
    """The route of notes has no `inject.user`: the targets are checked for `user=None`."""
    response = get_api_client(sample_app).post(
        NOTES, json_data=note_payload(tags=rels('tag', tags['hidden']))
    )
    assert_relation_denied(response, 'tags')
    assert restrict_users == [None]


def test_restrict_queryset_without_authentication(tags):
    qs = Tag.objects.all()
    visible = {tags['visible'], tags['visible2'], tags['locked']}
    for user in (None, AnonymousUser()):
        assert set(TagRouteSet.restrict_queryset(qs, CrudAccessAction.VIEW, user=user)) == visible
    staff = User(username='staff', is_staff=True)
    assert set(TagRouteSet.restrict_queryset(qs, CrudAccessAction.VIEW, user=staff)) == set(
        tags.values()
    )
