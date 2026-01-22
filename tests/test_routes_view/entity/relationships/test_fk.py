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
For FK relations, POST, PATCH, DELETE are tested both from the parent side and from the dependent side
"""

import json

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_post_relationships_fk_parent(sample_app):
    """
    We check setting the relation from the parent side.
    We add two new items to one existing related item
    """
    parent = factories.ParentEntityFactory.create()
    depend_null_1 = factories.DependentEntityNullFactory.create(parent_entity=parent)
    depend_null_2 = factories.DependentEntityNullFactory.create(parent_entity=None)
    depend_null_3 = factories.DependentEntityNullFactory.create(parent_entity=None)
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity is None
    assert depend_null_3.parent_entity is None

    payload = {
        'data': [
            {'type': 'entity.dependent_entity_null', 'id': str(depend_null_2.id)},
            {'type': 'entity.dependent_entity_null', 'id': str(depend_null_3.id)},
        ]
    }
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/dependent_entities_null'
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null_1.refresh_from_db()
    depend_null_2.refresh_from_db()
    depend_null_3.refresh_from_db()
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity == parent
    assert depend_null_3.parent_entity == parent

    # we check passing an empty list. nothing changes.
    payload = {'data': []}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null_1.refresh_from_db()
    depend_null_2.refresh_from_db()
    depend_null_3.refresh_from_db()
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity == parent
    assert depend_null_3.parent_entity == parent


@pytest.mark.django_db(transaction=True)
def test_post_relationships_fk_dependent_entity_null(sample_app):
    """
    We check setting the relation from the dependent side.
    We add a relation to a new item
    """
    parent = factories.ParentEntityFactory.create()
    depend_null = factories.DependentEntityNullFactory.create(parent_entity=None)
    assert depend_null.parent_entity is None

    payload = {'data': {'type': 'entity.parent_entity', 'id': str(parent.id)}}
    url = f'/api/v1/entity/dependent_entity_null/{depend_null.id}/relationships/parent_entity'
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null.refresh_from_db()
    assert depend_null.parent_entity == parent

    # we check passing null. nothing changes.
    payload = {'data': None}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null.refresh_from_db()
    assert depend_null.parent_entity == parent


@pytest.mark.django_db(transaction=True)
def test_patch_relationships_fk_parent(sample_app):
    """
    We check replacing the relation from the parent side.
    We replace one old related item with two new ones
    """
    parent = factories.ParentEntityFactory.create()
    depend_null_1 = factories.DependentEntityNullFactory.create(parent_entity=parent)
    depend_null_2 = factories.DependentEntityNullFactory.create(parent_entity=None)
    depend_null_3 = factories.DependentEntityNullFactory.create(parent_entity=None)
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity is None
    assert depend_null_3.parent_entity is None

    payload = {
        'data': [
            {'type': 'entity.dependent_entity_null', 'id': str(depend_null_2.id)},
            {'type': 'entity.dependent_entity_null', 'id': str(depend_null_3.id)},
        ]
    }
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/dependent_entities_null'
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null_1.refresh_from_db()
    depend_null_2.refresh_from_db()
    depend_null_3.refresh_from_db()
    assert depend_null_1.parent_entity is None
    assert depend_null_2.parent_entity == parent
    assert depend_null_3.parent_entity == parent

    # we check passing an empty list. all relations are cleared.
    payload = {'data': []}
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null_1.refresh_from_db()
    depend_null_2.refresh_from_db()
    depend_null_3.refresh_from_db()
    assert depend_null_1.parent_entity is None
    assert depend_null_2.parent_entity is None
    assert depend_null_3.parent_entity is None


@pytest.mark.django_db(transaction=True)
def test_patch_relationships_fk_dependent_entity_null(sample_app):
    """
    We check replacing the relation from the dependent side.
    """
    parent_1 = factories.ParentEntityFactory.create()
    parent_2 = factories.ParentEntityFactory.create()
    depend_null = factories.DependentEntityNullFactory.create(parent_entity=parent_1)
    assert depend_null.parent_entity == parent_1

    payload = {'data': {'type': 'entity.parent_entity', 'id': str(parent_2.id)}}
    url = f'/api/v1/entity/dependent_entity_null/{depend_null.id}/relationships/parent_entity'
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null.refresh_from_db()
    assert depend_null.parent_entity == parent_2

    # we check passing null. nothing changes.
    payload = {'data': None}
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    depend_null.refresh_from_db()
    assert depend_null.parent_entity is None


@pytest.mark.django_db(transaction=True)
def test_delete_relationships_fk_parent(sample_app):
    """
    We check deleting the relation from the parent side.
    """
    parent = factories.ParentEntityFactory.create()
    depend_null_1 = factories.DependentEntityNullFactory.create(parent_entity=parent)
    depend_null_2 = factories.DependentEntityNullFactory.create(parent_entity=parent)
    depend_null_3 = factories.DependentEntityNullFactory.create(parent_entity=parent)
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity == parent
    assert depend_null_3.parent_entity == parent

    payload = {
        'data': [
            {'type': 'entity.dependent_entity_null', 'id': str(depend_null_2.id)},
            {'type': 'entity.dependent_entity_null', 'id': str(depend_null_3.id)},
        ]
    }
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/dependent_entities_null'
    client = get_api_client(sample_app)

    # we add the request method directly to the instance
    def request(method, url, **kwargs):
        headers = client.headers | kwargs.pop('headers', {})
        return client.client.request(method, url, headers=headers, **kwargs)

    client.request = request
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    depend_null_1.refresh_from_db()
    depend_null_2.refresh_from_db()
    depend_null_3.refresh_from_db()
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity is None
    assert depend_null_3.parent_entity is None

    # we check passing an empty list. nothing changes.
    payload = {'data': []}
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    depend_null_1.refresh_from_db()
    depend_null_2.refresh_from_db()
    depend_null_3.refresh_from_db()
    assert depend_null_1.parent_entity == parent
    assert depend_null_2.parent_entity is None
    assert depend_null_3.parent_entity is None


@pytest.mark.django_db(transaction=True)
def test_delete_relationships_fk_dependent_entity_null(sample_app):
    """
    We check deleting the relation from the dependent side.
    """
    parent = factories.ParentEntityFactory.create()
    depend = factories.DependentEntityNullFactory.create(parent_entity=parent)
    assert depend.parent_entity == parent

    payload = {'data': {'type': 'entity.parent_entity', 'id': str(parent.id)}}
    url = f'/api/v1/entity/dependent_entity_null/{depend.id}/relationships/parent_entity'
    client = get_api_client(sample_app)

    # we add the request method directly to the instance
    def request(method, url, **kwargs):
        headers = client.headers | kwargs.pop('headers', {})
        return client.client.request(method, url, headers=headers, **kwargs)

    client.request = request
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    depend.refresh_from_db()
    assert depend.parent_entity is None

    # we check passing null. nothing changes.
    payload = {'data': None}
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    depend.refresh_from_db()
    assert depend.parent_entity is None
