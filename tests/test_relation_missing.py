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
A relationship to an object that does not exist, of a model whose route does not restrict
its objects (`visibility.Folder`, `entity.ChildEntity`) or that has no route
(`visibility.Label`), is 422 `ERR_VALIDATE` at its identifier (bazis 2.16): it was an
`IntegrityError` of the foreign key at the commit, a 500. A model whose route restricts its
objects (`visibility.Tag`) keeps 403 `ERR_RELATION_ACCESS`: the existence of its objects is
not told.
"""

import uuid
from types import SimpleNamespace
from urllib.parse import urlencode

from django.db import models

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Attachment, Memo
from entity.models import ChildEntity, DependentEntity, ParentEntity
from visibility.models import Folder, Label, Note

from tests.test_relation_visibility import NOTES, note_payload, rel, relationships_request, rels


PARENTS = '/api/v1/entity/parent_entity/'
MEMOS = '/api/v1/catalog/memo/'
MISSING = str(uuid.uuid4())


def missing(type_):
    return {'data': {'id': MISSING, 'type': type_}}


def assert_missing(response, pointer: str):
    assert response.status_code == 422, response.text
    errors = response.json()['errors']
    assert [(it['code'], it['source']) for it in errors] == [('ERR_VALIDATE', {'pointer': pointer})]


def parent_payload(**relationships) -> dict:
    data = {
        'type': 'entity.parent_entity',
        'bs:action': 'add',
        'attributes': {
            'name': 'Parent',
            'description': 'Parent',
            'is_active': True,
            'price': '1.00',
            'dt_approved': '2024-01-12T16:54:12Z',
        },
    }
    if relationships:
        data['relationships'] = relationships
    return {'data': data}


def children(*ids) -> dict:
    return {'data': [{'id': str(it), 'type': 'entity.child_entity'} for it in ids]}


@pytest.mark.django_db(transaction=True)
def test_create_with_a_missing_target(sample_app):
    """To-one (a model with an unrestricted route, a model without a route) and to-many."""
    client = get_api_client(sample_app)

    response = client.post(NOTES, json_data=note_payload(folder=missing('visibility.folder')))
    assert_missing(response, '/data/relationships/folder/data/id')
    response = client.post(NOTES, json_data=note_payload(label=missing('visibility.label')))
    assert_missing(response, '/data/relationships/label/data/id')
    assert not Note.objects.exists()

    child = ChildEntity.objects.create(child_name='Child')
    response = client.post(
        PARENTS, json_data=parent_payload(child_entities=children(child.id, MISSING))
    )
    assert_missing(response, '/data/relationships/child_entities/data/1/id')
    assert not ParentEntity.objects.exists()

    # the objects that exist are linked
    folder = Folder.objects.create(name='folder')
    label = Label.objects.create(name='label')
    response = client.post(
        NOTES, json_data=note_payload(folder=rel('folder', folder), label=rel('label', label))
    )
    assert response.status_code == 201, response.text
    assert (Note.objects.get().folder, Note.objects.get().label) == (folder, label)
    response = client.post(PARENTS, json_data=parent_payload(child_entities=children(child.id)))
    assert response.status_code == 201, response.text
    assert list(ParentEntity.objects.get().child_entities.all()) == [child]


@pytest.mark.django_db(transaction=True)
def test_update_with_a_missing_target(sample_app):
    """An update: a to-one and a reverse to-many relationship; the value kept is not checked."""
    folder = Folder.objects.create(name='folder')
    note = Note.objects.create(name='note', folder=folder)
    client = get_api_client(sample_app)

    response = client.patch(
        f'{NOTES}{note.id}/', json_data=note_payload(note, folder=missing('visibility.folder'))
    )
    assert_missing(response, '/data/relationships/folder/data/id')
    note.refresh_from_db()
    assert note.folder == folder

    parent = ParentEntity.objects.create(name='Parent')
    dependent = DependentEntity.objects.create(dependent_name='Dependent', parent_entity=parent)
    response = client.patch(
        f'{PARENTS}{parent.id}/',
        json_data={
            'data': {
                'id': str(parent.id),
                'type': 'entity.parent_entity',
                'bs:action': 'change',
                'relationships': {
                    'dependent_entities': {
                        'data': [
                            {'id': str(dependent.id), 'type': 'entity.dependent_entity'},
                            {'id': MISSING, 'type': 'entity.dependent_entity'},
                        ]
                    }
                },
            }
        },
    )
    assert_missing(response, '/data/relationships/dependent_entities/data/1/id')

    response = client.patch(
        f'{NOTES}{note.id}/', json_data=note_payload(note, folder=rel('folder', folder))
    )
    assert response.status_code == 200, response.text


@pytest.mark.django_db(transaction=True)
def test_relationships_endpoints_with_a_missing_target(sample_app):
    """The relationships endpoints point into their body, the `data` of the relationship."""
    note = Note.objects.create(name='note')
    parent = ParentEntity.objects.create(name='Parent')
    child = ChildEntity.objects.create(child_name='Child')
    client = get_api_client(sample_app)

    response = relationships_request(client, 'PATCH', note, 'folder', missing('visibility.folder'))
    assert_missing(response, '/data/id')

    def parent_children(method, *ids):
        return client.client.request(
            method,
            f'{PARENTS}{parent.id}/relationships/child_entities',
            headers=client.headers,
            json=children(*ids),
        )

    assert_missing(parent_children('POST', child.id, MISSING), '/data/1/id')
    assert_missing(parent_children('PATCH', MISSING), '/data/0/id')
    assert not parent.child_entities.exists()

    response = parent_children('POST', child.id)
    assert response.status_code < 300, response.text
    assert list(parent.child_entities.all()) == [child]


@pytest.mark.django_db(transaction=True)
def test_included_item_with_a_missing_target(sample_app):
    """An included item: the pointer is in its place in `included`."""
    payload = parent_payload()
    payload['included'] = [
        {
            'type': 'entity.dependent_entity',
            'bs:action': 'add',
            'attributes': {'dependent_name': 'Dependent'},
            'relationships': {'parent_entity': missing('entity.parent_entity')},
        }
    ]
    query = urlencode({'include': 'dependent_entities'})
    response = get_api_client(sample_app).post(f'{PARENTS}?{query}', json_data=payload)
    assert_missing(response, '/included/0/relationships/parent_entity/data/id')
    assert not ParentEntity.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_a_restricted_model_does_not_tell_the_existence(sample_app):
    """A missing object of a model whose route restricts its objects: 403, as a hidden one."""
    client = get_api_client(sample_app)
    response = client.post(NOTES, json_data=note_payload(tag=missing('visibility.tag')))
    assert response.status_code == 403, response.text
    assert response.json()['errors'][0]['code'] == 'ERR_RELATION_ACCESS'
    response = client.post(NOTES, json_data=note_payload(tags=rels('tag')))
    assert response.status_code == 201, response.text


@pytest.mark.django_db(transaction=True)
def test_the_lookup_ignores_a_filtering_default_manager(sample_app, monkeypatch):
    """
    The objects are looked up with the base manager of the model, as the foreign key
    references them: a default manager that leaves some of them out (a soft delete) does
    not make an existing object missing.
    """
    folder = Folder.objects.create(name='folder')
    # a default manager that shows no folder
    monkeypatch.setattr(
        Folder, 'objects', SimpleNamespace(filter=lambda **kwargs: Folder._base_manager.none())
    )
    response = get_api_client(sample_app).post(
        NOTES, json_data=note_payload(folder=rel('folder', folder))
    )
    assert response.status_code == 201, response.text
    assert Note.objects.get().folder_id == folder.id


class HiddenManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().none()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('way', ['update', 'PATCH', 'POST'])
def test_every_write_looks_up_with_the_base_manager(sample_app, way, monkeypatch):
    """
    The update and the relationships endpoints look the objects up as the check does: an
    object a filtering default manager hides was left out of the value of an update and
    refused (403) by the relationships endpoints.
    """
    memo = Memo.objects.create(title='Memo')
    attachment = Attachment.objects.create(name='Attachment')
    # a default manager that shows no attachment (a soft delete)
    hidden = HiddenManager()
    hidden.model = Attachment
    monkeypatch.setattr(Attachment, 'objects', hidden)
    client = get_api_client(sample_app)
    value = {'data': [{'id': str(attachment.id), 'type': 'catalog.attachment'}]}

    if way == 'update':
        response = client.patch(
            f'{MEMOS}{memo.id}/',
            json_data={
                'data': {
                    'id': str(memo.id),
                    'type': 'catalog.memo',
                    'bs:action': 'change',
                    'relationships': {'extras': value},
                }
            },
        )
    else:
        response = client.client.request(
            way, f'{MEMOS}{memo.id}/relationships/extras', headers=client.headers, json=value
        )

    assert response.status_code < 300, response.text
    assert list(memo.extras.all()) == [attachment]
