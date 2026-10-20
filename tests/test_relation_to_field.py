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
The relations by a foreign key with `to_field` (`visibility.Bookmark`): the identifiers of
their relationships are primary keys of the related objects, as of every relationship, so
they match the `id` of the resource in `included` and in its URL; the foreign key stores the
value of the referenced field (`Folder.code`, a string; `Tag.ref`, a UUID of the format of a
primary key). The route of `visibility.Tag` hides the hidden tags: the checks look a tag up
by the identifier, the primary key, though another tag has this value as its `ref`.
"""

import uuid

import pytest
from bazis_test_utils.utils import get_api_client
from visibility.models import Bookmark, Folder, Tag

from tests.test_relation_visibility import assert_relation_denied
from tests.utils.assert_sql import normalize_sql


BOOKMARKS = '/api/v1/visibility/bookmark/'


def ident(type_, value):
    return {'data': {'id': str(value), 'type': f'visibility.{type_}'}}


def bookmark_payload(bookmark=None, **relationships):
    data = {'type': 'visibility.bookmark', 'relationships': relationships}
    if bookmark is None:
        data['attributes'] = {'name': 'bookmark'}
    else:
        data['id'] = str(bookmark.id)
    return {'data': data}


def relationships_request(client, method, bookmark, field, payload):
    return client.client.request(
        method,
        f'{BOOKMARKS}{bookmark.id}/relationships/{field}',
        headers=client.headers,
        json=payload,
    )


@pytest.fixture
def tags(db):
    """
    The `ref` of each tag is the primary key of the other one: a lookup by the `ref`
    inspects the other tag.
    """
    visible_id, hidden_id = uuid.uuid4(), uuid.uuid4()
    return {
        'visible': Tag.objects.create(name='visible', id=visible_id, ref=hidden_id),
        'hidden': Tag.objects.create(name='hidden', id=hidden_id, ref=visible_id, is_hidden=True),
        'locked': Tag.objects.create(name='locked', is_locked=True),
    }


@pytest.mark.django_db(transaction=True)
def test_identifiers_match_the_included_resources(sample_app, tags):
    """A retrieve, a list and the response of a write show the primary key everywhere."""
    folder = Folder.objects.create(name='folder', code='f-1')
    bookmark = Bookmark.objects.create(name='bookmark', tag=tags['visible'], folder=folder)
    client = get_api_client(sample_app)

    def check(data, included=None):
        relationships = data['relationships']
        assert relationships['tag']['data']['id'] == str(tags['visible'].id)
        assert relationships['folder']['data']['id'] == str(folder.id)
        # a list has no `included`
        assert included is None or {(it['type'], it['id']) for it in included} == {
            ('visibility.tag', str(tags['visible'].id)),
            ('visibility.folder', str(folder.id)),
        }

    response = client.get(f'{BOOKMARKS}{bookmark.id}/?include=tag,folder')
    assert response.status_code == 200, response.text
    check(response.json()['data'], response.json()['included'])

    response = client.get(BOOKMARKS, params={'include': 'tag,folder'})
    assert response.status_code == 200, response.text
    check(response.json()['data'][0])

    response = client.patch(
        f'{BOOKMARKS}{bookmark.id}/?include=tag,folder',
        json_data=bookmark_payload(bookmark, tag=ident('tag', tags['visible'].id)),
    )
    assert response.status_code == 200, response.text
    check(response.json()['data'], response.json()['included'])

    # no relation: no identifier
    bookmark.tag = None
    bookmark.save()
    response = client.get(f'{BOOKMARKS}{bookmark.id}/')
    assert response.json()['data']['relationships']['tag']['data'] is None


@pytest.mark.django_db(transaction=True)
def test_create_links_the_object_with_the_primary_key(sample_app, tags):
    client = get_api_client(sample_app)

    # the hidden tag, by its primary key, which is the `ref` of the visible one
    response = client.post(
        BOOKMARKS, json_data=bookmark_payload(tag=ident('tag', tags['hidden'].id))
    )
    assert_relation_denied(response, 'tag')
    assert not Bookmark.objects.exists()

    response = client.post(
        BOOKMARKS, json_data=bookmark_payload(tag=ident('tag', tags['locked'].id))
    )
    assert response.status_code == 422, response.text
    assert response.json()['errors'][0]['code'] == 'ERR_RELATION_LINK'

    response = client.post(
        BOOKMARKS, json_data=bookmark_payload(tag=ident('tag', tags['visible'].id))
    )
    assert response.status_code == 201, response.text
    bookmark = Bookmark.objects.get()
    assert bookmark.tag == tags['visible']
    # the foreign key stores the referenced field
    assert bookmark.tag_id == tags['visible'].ref


@pytest.mark.django_db(transaction=True)
def test_update_links_the_object_with_the_primary_key(sample_app, tags):
    bookmark = Bookmark.objects.create(name='bookmark', tag=tags['locked'])
    client = get_api_client(sample_app)
    url = f'{BOOKMARKS}{bookmark.id}/'

    response = client.patch(
        url, json_data=bookmark_payload(bookmark, tag=ident('tag', tags['hidden'].id))
    )
    assert_relation_denied(response, 'tag')
    bookmark.refresh_from_db()
    assert bookmark.tag == tags['locked']

    # the value that is kept is not checked
    response = client.patch(
        url, json_data=bookmark_payload(bookmark, tag=ident('tag', tags['locked'].id))
    )
    assert response.status_code == 200, response.text

    response = client.patch(
        url, json_data=bookmark_payload(bookmark, tag=ident('tag', tags['visible'].id))
    )
    assert response.status_code == 200, response.text
    bookmark.refresh_from_db()
    assert bookmark.tag == tags['visible']


@pytest.mark.django_db(transaction=True)
def test_relationships_endpoint_links_the_object_with_the_primary_key(sample_app, tags):
    bookmark = Bookmark.objects.create(name='bookmark')
    client = get_api_client(sample_app)

    response = relationships_request(
        client, 'PATCH', bookmark, 'tag', ident('tag', tags['hidden'].id)
    )
    assert_relation_denied(response, 'tag', '/data')
    bookmark.refresh_from_db()
    assert bookmark.tag is None

    response = relationships_request(
        client, 'PATCH', bookmark, 'tag', ident('tag', tags['visible'].id)
    )
    assert response.status_code == 204, response.text
    bookmark.refresh_from_db()
    assert (bookmark.tag, bookmark.tag_id) == (tags['visible'], tags['visible'].ref)

    response = relationships_request(
        client, 'DELETE', bookmark, 'tag', ident('tag', tags['visible'].id)
    )
    assert response.status_code == 204, response.text
    bookmark.refresh_from_db()
    assert bookmark.tag is None

    bookmark.tag = tags['visible']
    bookmark.save()
    response = relationships_request(client, 'PATCH', bookmark, 'tag', {'data': None})
    assert response.status_code == 204, response.text
    bookmark.refresh_from_db()
    assert bookmark.tag is None


@pytest.mark.django_db(transaction=True)
def test_the_value_of_the_field_is_not_an_identifier(sample_app):
    """The code of a folder is not a primary key; a missing object is 422."""
    folder = Folder.objects.create(name='folder', code='f-1')
    client = get_api_client(sample_app)

    response = client.post(
        BOOKMARKS, json_data=bookmark_payload(folder=ident('folder', folder.code))
    )
    assert response.status_code == 422, response.text

    response = client.post(
        BOOKMARKS, json_data=bookmark_payload(folder=ident('folder', uuid.uuid4()))
    )
    assert response.status_code == 422, response.text
    assert [(it['code'], it['source']) for it in response.json()['errors']] == [
        ('ERR_VALIDATE', {'pointer': '/data/relationships/folder/data/id'})
    ]

    response = client.post(
        BOOKMARKS, json_data=bookmark_payload(folder=ident('folder', folder.id))
    )
    assert response.status_code == 201, response.text
    assert Bookmark.objects.get().folder == folder


@pytest.mark.django_db(transaction=True)
def test_included_shows_only_the_visible_objects(sample_app, tags):
    bookmark = Bookmark.objects.create(name='bookmark', tag=tags['hidden'])
    client = get_api_client(sample_app)

    response = client.get(f'{BOOKMARKS}{bookmark.id}/?include=tag')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['data']['relationships']['tag']['data']['id'] == str(tags['hidden'].id)
    assert not data.get('included')


@pytest.mark.django_db(transaction=True)
def test_filter_sort_and_filter_by_id_through_the_relation(sample_app, tags):
    """The filter, the sorting and `filter=<type>=<id>` take the primary key of the object."""
    folder = Folder.objects.create(name='folder', code='f-1')
    other = Bookmark.objects.create(name='other', folder=Folder.objects.create(name='x'))
    visible = Bookmark.objects.create(name='visible', tag=tags['visible'], folder=folder)
    client = get_api_client(sample_app)

    def listed(**params):
        response = client.get(BOOKMARKS, params=params)
        assert response.status_code == 200, response.text
        return [it['id'] for it in response.json()['data']]

    assert listed(filter='tag__name=visible') == [str(visible.id)]
    assert listed(filter='folder__name=folder') == [str(visible.id)]
    assert listed(filter=f'visibility.tag={tags["visible"].id}') == [str(visible.id)]
    assert listed(filter=f'visibility.folder={folder.id}') == [str(visible.id)]
    assert listed(filter=f'tag={tags["visible"].id}') == [str(visible.id)]
    assert listed(filter=f'folder={folder.id}') == [str(visible.id)]
    # by the primary key of the related object, not by the stored `ref`
    assert listed(filter=f'tag={tags["visible"].ref}') == []
    ordered = sorted([visible, other], key=lambda it: str(it.folder.id))
    assert listed(sort='folder') == [str(it.id) for it in ordered]


@pytest.mark.django_db(transaction=True)
def test_aggregates_group_by_the_primary_key(sample_app, tags):
    Bookmark.objects.create(name='one', tag=tags['visible'])
    Bookmark.objects.create(name='two', tag=tags['visible'])
    client = get_api_client(sample_app)

    response = client.get(BOOKMARKS, params={'meta': 'aggregates', 'group': 'tag'})

    assert response.status_code == 200, response.text
    assert response.json()['meta']['aggregates'] == [
        {'group': str(tags['visible'].id), 'values': {'count': 2}}
    ]


@pytest.mark.django_db(transaction=True)
def test_update_shows_the_new_object(sample_app, tags):
    bookmark = Bookmark.objects.create(name='bookmark', tag=tags['locked'])
    client = get_api_client(sample_app)

    response = client.patch(
        f'{BOOKMARKS}{bookmark.id}/?include=tag',
        json_data=bookmark_payload(bookmark, tag=ident('tag', tags['visible'].id)),
    )

    assert response.status_code == 200, response.text
    assert response.json()['data']['relationships']['tag']['data']['id'] == str(tags['visible'].id)
    assert [it['id'] for it in response.json()['included']] == [str(tags['visible'].id)]


@pytest.mark.django_db(transaction=True)
def test_list_takes_the_identifiers_in_one_query(sample_app, tags):
    """The primary keys of the objects the foreign keys link come with the list."""
    for index in range(3):
        Bookmark.objects.create(name=f'b{index}', tag=tags['visible'])
    client = get_api_client(sample_app)

    response = client.get(BOOKMARKS)

    assert response.status_code == 200, response.text
    assert {it['relationships']['tag']['data']['id'] for it in response.json()['data']} == {
        str(tags['visible'].id)
    }
    with open('sql.log') as f:
        queries = [normalize_sql(line) for line in f]
    assert not [q for q in queries if 'from "visibility_tag"' in q]


@pytest.mark.django_db(transaction=True)
def test_reverse_relation_of_the_referenced_object(sample_app):
    """`Folder.bookmarks` compares the foreign key with the `code` of the folder."""
    folder = Folder.objects.create(name='folder', code='f-1')
    other = Folder.objects.create(name='other', code='f-2')
    bookmark = Bookmark.objects.create(name='bookmark', folder=folder)
    client = get_api_client(sample_app)
    url = '/api/v1/visibility/folder/'

    response = client.get(url, params={'filter': 'bookmarks__name=bookmark'})
    assert [it['id'] for it in response.json()['data']] == [str(folder.id)]
    response = client.get(url, params={'filter': 'bookmarks__isnull=true'})
    assert [it['id'] for it in response.json()['data']] == [str(other.id)]

    response = client.get(f'{url}{folder.id}/', params={'include': 'bookmarks'})
    assert response.status_code == 200, response.text
    assert [it['id'] for it in response.json()['included']] == [str(bookmark.id)]
    response = client.get(f'{url}{other.id}/', params={'include': 'bookmarks'})
    assert not response.json().get('included')
