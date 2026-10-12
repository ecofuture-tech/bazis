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
A to-many relationship is written by one rule, whatever writes it: an update of the item,
the relationships endpoints (`PATCH` sets, `POST` adds, `DELETE` removes). An object a
reverse foreign key unlinks is deleted if its foreign key cannot be null
(`entity.DependentEntity`), else its foreign key is cleared (`entity.DependentEntityNull`);
deleting it needs the `delete` access of the default route of its model (bazis 2.16: only
an update deleted it, `PATCH` of the relationships endpoints left it, `DELETE` failed with
500, and no access was asked for).
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import ChildEntity, DependentEntity, DependentEntityNull, ParentEntity
from entity.routes import (
    DependentEntityNullRouteSet,
    DependentEntityRouteSet,
    ParentEntityRouteSet,
)
from validation.models import Equipment, Room

from bazis.core.schemas.enums import CrudAccessAction
from bazis.core.utils.orm import relation_write


PARENTS = '/api/v1/entity/parent_entity/'
CHILDREN = '/api/v1/entity/child_entity/'


def identifiers(type_, *objs) -> dict:
    return {'data': [{'id': str(it.id), 'type': type_} for it in objs]}


def update(client, parent, field, type_, *objs):
    return client.patch(
        f'{PARENTS}{parent.id}/',
        json_data={
            'data': {
                'id': str(parent.id),
                'type': 'entity.parent_entity',
                'bs:action': 'change',
                'relationships': {field: identifiers(type_, *objs)},
            }
        },
    )


def relationships(client, method, parent, field, type_, *objs):
    return client.client.request(
        method,
        f'{PARENTS}{parent.id}/relationships/{field}',
        headers=client.headers,
        json=identifiers(type_, *objs),
    )


def write(client, way, parent, field, type_, *objs):
    if way == 'update':
        return update(client, parent, field, type_, *objs)
    return relationships(client, way, parent, field, type_, *objs)


def dependent(parent, name='Dependent'):
    return DependentEntity.objects.create(dependent_name=name, parent_entity=parent)


def dependent_null(parent, name='Dependent'):
    return DependentEntityNull.objects.create(dependent_name=name, parent_entity=parent)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('way', ['update', 'PATCH'])
def test_set_deletes_the_unlinked_objects_of_a_required_foreign_key(sample_app, way):
    parent, other = ParentEntity.objects.create(name='A'), ParentEntity.objects.create(name='B')
    kept, unlinked, moved = dependent(parent), dependent(parent), dependent(other)

    response = write(
        get_api_client(sample_app),
        way,
        parent,
        'dependent_entities',
        'entity.dependent_entity',
        kept,
        moved,
    )

    assert response.status_code < 300, response.text
    assert set(parent.dependent_entities.all()) == {kept, moved}
    assert not DependentEntity.objects.filter(pk=unlinked.pk).exists()
    assert not other.dependent_entities.exists()


@pytest.mark.django_db(transaction=True)
def test_remove_deletes_the_objects_of_a_required_foreign_key(sample_app):
    parent = ParentEntity.objects.create(name='A')
    kept, removed = dependent(parent), dependent(parent)

    response = relationships(
        get_api_client(sample_app),
        'DELETE',
        parent,
        'dependent_entities',
        'entity.dependent_entity',
        removed,
    )

    assert response.status_code == 204, response.text
    assert list(parent.dependent_entities.all()) == [kept]
    assert not DependentEntity.objects.filter(pk=removed.pk).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('way', ['update', 'PATCH'])
def test_set_unlinks_the_objects_of_a_nullable_foreign_key(sample_app, way):
    parent = ParentEntity.objects.create(name='A')
    kept, unlinked = dependent_null(parent), dependent_null(parent)

    response = write(
        get_api_client(sample_app),
        way,
        parent,
        'dependent_entities_null',
        'entity.dependent_entity_null',
        kept,
    )

    assert response.status_code < 300, response.text
    assert list(parent.dependent_entities_null.all()) == [kept]
    unlinked.refresh_from_db()
    assert unlinked.parent_entity is None


@pytest.fixture
def no_delete_access(monkeypatch):
    """The dependent objects (both models) can be changed, not deleted."""

    def restrict_queryset(cls, qs, access_action, user=None, **kwargs):
        return qs.none() if access_action == CrudAccessAction.DELETE else qs

    for route in (DependentEntityRouteSet, DependentEntityNullRouteSet):
        monkeypatch.setattr(
            route, 'restrict_queryset', classmethod(restrict_queryset), raising=False
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('way', ['update', 'PATCH', 'DELETE'])
def test_deleting_an_unlinked_object_needs_the_delete_access(sample_app, no_delete_access, way):
    parent = ParentEntity.objects.create(name='A')
    kept, unlinked = dependent(parent), dependent(parent)
    objs = [unlinked] if way == 'DELETE' else [kept]

    response = write(
        get_api_client(sample_app),
        way,
        parent,
        'dependent_entities',
        'entity.dependent_entity',
        *objs,
    )

    assert response.status_code == 403, response.text
    assert response.json()['errors'][0]['code'] == 'ERR_RELATION_ACCESS'
    assert set(parent.dependent_entities.all()) == {kept, unlinked}


@pytest.mark.django_db(transaction=True)
def test_unlinking_a_nullable_foreign_key_needs_no_delete_access(sample_app, no_delete_access):
    parent = ParentEntity.objects.create(name='A')
    unlinked = dependent_null(parent)

    response = relationships(
        get_api_client(sample_app),
        'DELETE',
        parent,
        'dependent_entities_null',
        'entity.dependent_entity_null',
        unlinked,
    )

    assert response.status_code == 204, response.text
    unlinked.refresh_from_db()
    assert unlinked.parent_entity is None


@pytest.fixture
def no_parent_delete_access(monkeypatch):
    """The parents can be changed, not deleted."""

    def restrict_queryset(cls, qs, access_action, user=None, **kwargs):
        return qs.none() if access_action == CrudAccessAction.DELETE else qs

    monkeypatch.setattr(
        ParentEntityRouteSet, 'restrict_queryset', classmethod(restrict_queryset), raising=False
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('way', ['update', 'PATCH', 'DELETE'])
def test_unlinking_a_reverse_many_to_many_needs_no_delete_access(
    sample_app, no_parent_delete_access, way
):
    """A many-to-many relation only unlinks: the change access is enough."""
    child = ChildEntity.objects.create(child_name='Child')
    kept, unlinked = ParentEntity.objects.create(name='A'), ParentEntity.objects.create(name='B')
    child.parent_entities.set([kept, unlinked])
    client = get_api_client(sample_app)
    value = identifiers('entity.parent_entity', unlinked if way == 'DELETE' else kept)

    if way == 'update':
        response = client.patch(
            f'{CHILDREN}{child.id}/',
            json_data={
                'data': {
                    'id': str(child.id),
                    'type': 'entity.child_entity',
                    'bs:action': 'change',
                    'relationships': {'parent_entities': value},
                }
            },
        )
    else:
        response = client.client.request(
            way,
            f'{CHILDREN}{child.id}/relationships/parent_entities',
            headers=client.headers,
            json=value,
        )

    assert response.status_code < 300, response.text
    assert list(child.parent_entities.all()) == [kept]
    assert ParentEntity.objects.filter(pk=unlinked.pk).exists()


@pytest.mark.django_db
def test_set_writes_only_the_changed_links_of_a_required_foreign_key():
    """
    `set` of a reverse foreign key that cannot be null, of a model that validates its
    items (saved one by one): the objects linked already are not saved again.
    """
    room, other = Room.objects.create(name='Blue'), Room.objects.create(name='Green')
    linked = [Equipment.objects.create(name=f'E{i}', room=room) for i in range(5)]
    moved = Equipment.objects.create(name='Moved', room=other)
    Equipment.calls.clear()

    with CaptureQueriesContext(connection) as queries:
        relation_write(room.equipment, 'set', linked)
    assert Equipment.calls == []
    assert not [it for it in queries if it['sql'].startswith(('UPDATE', 'DELETE'))]

    relation_write(room.equipment, 'set', linked[1:] + [moved])
    assert [pk for pk, _ in Equipment.calls] == [moved.pk]
    assert set(room.equipment.all()) == set(linked[1:] + [moved])
    assert not Equipment.objects.filter(pk=linked[0].pk).exists()
    Equipment.calls.clear()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('way', ['update', 'PATCH', 'DELETE'])
def test_an_unlinked_object_of_a_model_without_a_route_is_not_deleted(sample_app, monkeypatch, way):
    """No route tells whether the user may delete it: 403, nothing is written."""
    monkeypatch.setattr(DependentEntity, '_default_route', None)
    parent = ParentEntity.objects.create(name='A')
    kept, unlinked = dependent(parent), dependent(parent)
    objs = [unlinked] if way == 'DELETE' else [kept]

    response = write(
        get_api_client(sample_app),
        way,
        parent,
        'dependent_entities',
        'entity.dependent_entity',
        *objs,
    )

    assert response.status_code == 403, response.text
    assert response.json()['errors'][0]['code'] == 'ERR_RELATION_ACCESS'
    assert set(parent.dependent_entities.all()) == {kept, unlinked}

    # linking needs no route (the object is only looked up)
    response = write(
        get_api_client(sample_app),
        'POST' if way != 'update' else 'update',
        parent,
        'dependent_entities',
        'entity.dependent_entity',
        *([kept, unlinked] if way == 'update' else [kept]),
    )
    assert response.status_code < 300, response.text
