"""
For M2M relations, POST, PATCH, DELETE are tested both from the parent side and from the child side
"""

import json

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_post_relationships_m2m_parent(sample_app):
    """
    We check setting up the relation from the parent side.
    We extend the relation with one existing record by adding two new ones
    """
    parent = factories.ParentEntityFactory.create(child_entities=False)
    child1 = factories.ChildEntityFactory.create()
    child2 = factories.ChildEntityFactory.create()
    child3 = factories.ChildEntityFactory.create()
    parent.child_entities.add(child1)

    payload = {
        'data': [
            {'type': 'entity.child_entity', 'id': str(child2.id)},
            {'type': 'entity.child_entity', 'id': str(child3.id)},
        ]
    }
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/child_entities'
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    parent.refresh_from_db()
    assert parent.child_entities.count() == 3
    assert parent.child_entities.filter(id=child1.id).exists()
    assert parent.child_entities.filter(id=child2.id).exists()
    assert parent.child_entities.filter(id=child3.id).exists()

    # we check passing an empty list. nothing changes.
    payload = {'data': []}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    parent.refresh_from_db()
    assert parent.child_entities.count() == 3


@pytest.mark.django_db(transaction=True)
def test_post_relationships_m2m_child(sample_app):
    """
    We check setting up the relation from the child side.
    We extend the relation with one existing record by adding two new ones
    """
    child = factories.ChildEntityFactory.create()
    parent1 = factories.ParentEntityFactory.create(child_entities=False)
    parent2 = factories.ParentEntityFactory.create(child_entities=False)
    parent3 = factories.ParentEntityFactory.create(child_entities=False)
    child.parent_entities.add(parent1)

    payload = {
        'data': [
            {'type': 'entity.parent_entity', 'id': str(parent2.id)},
            {'type': 'entity.parent_entity', 'id': str(parent3.id)},
        ]
    }
    url = f'/api/v1/entity/child_entity/{child.id}/relationships/parent_entities'
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    child.refresh_from_db()
    assert child.parent_entities.count() == 3
    assert child.parent_entities.filter(id=parent1.id).exists()
    assert child.parent_entities.filter(id=parent2.id).exists()
    assert child.parent_entities.filter(id=parent3.id).exists()

    # we check passing an empty list. nothing changes.
    payload = {'data': []}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    child.refresh_from_db()
    assert child.parent_entities.count() == 3


@pytest.mark.django_db(transaction=True)
def test_patch_relationships_m2m_parent(sample_app):
    """
    We check replacing the relation from the parent side.
    We replace the relation with one existing record with a relation to two new ones
    """
    parent = factories.ParentEntityFactory.create(child_entities=False)
    child1 = factories.ChildEntityFactory.create()
    child2 = factories.ChildEntityFactory.create()
    child3 = factories.ChildEntityFactory.create()
    parent.child_entities.add(child1)

    payload = {
        'data': [
            {'type': 'entity.child_entity', 'id': str(child2.id)},
            {'type': 'entity.child_entity', 'id': str(child3.id)},
        ]
    }
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/child_entities'
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    parent.refresh_from_db()
    assert parent.child_entities.count() == 2
    assert parent.child_entities.filter(id=child2.id).exists()
    assert parent.child_entities.filter(id=child3.id).exists()

    # we check passing an empty list. relations are cleared.
    payload = {'data': []}
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    parent.refresh_from_db()
    assert parent.child_entities.count() == 0


@pytest.mark.django_db(transaction=True)
def test_patch_relationships_m2m_child(sample_app):
    """
    We check replacing the relation from the child side.
    We replace the relation with one existing record with a relation to two new ones
    """
    child = factories.ChildEntityFactory.create()
    parent1 = factories.ParentEntityFactory.create()
    parent2 = factories.ParentEntityFactory.create()
    parent3 = factories.ParentEntityFactory.create()
    child.parent_entities.add(parent1)

    payload = {
        'data': [
            {'type': 'entity.parent_entity', 'id': str(parent2.id)},
            {'type': 'entity.parent_entity', 'id': str(parent3.id)},
        ]
    }
    url = f'/api/v1/entity/child_entity/{child.id}/relationships/parent_entities'
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    child.refresh_from_db()
    assert child.parent_entities.count() == 2
    assert child.parent_entities.filter(id=parent2.id).exists()
    assert child.parent_entities.filter(id=parent3.id).exists()

    # we check passing an empty list. relations are cleared.
    payload = {'data': []}
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    child.refresh_from_db()
    assert child.parent_entities.count() == 0


@pytest.mark.django_db(transaction=True)
def test_delete_relationships_m2m_parent(sample_app):
    """
    We check deleting the relation from the parent side.
    From two existing records we delete the one old record and keep the other
    """
    parent = factories.ParentEntityFactory.create(child_entities=False)
    child1 = factories.ChildEntityFactory.create()
    child2 = factories.ChildEntityFactory.create()
    parent.child_entities.add(child1, child2)

    payload = {'data': [{'type': 'entity.child_entity', 'id': str(child1.id)}]}
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/child_entities'
    client = get_api_client(sample_app)

    # add the request method directly to the instance
    def request(method, url, **kwargs):
        headers = client.headers | kwargs.pop('headers', {})
        return client.client.request(method, url, headers=headers, **kwargs)

    client.request = request
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    parent.refresh_from_db()
    assert parent.child_entities.count() == 1
    assert parent.child_entities.filter(id=child2.id).exists()

    # we check passing an empty list. nothing changes.
    payload = {'data': []}
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    parent.refresh_from_db()
    assert parent.child_entities.count() == 1


@pytest.mark.django_db(transaction=True)
def test_delete_relationships_m2m_child(sample_app):
    """
    We check deleting the relation from the child side.
    From two existing records we delete the one old record and keep the other
    """
    child = factories.ChildEntityFactory.create()
    parent1 = factories.ParentEntityFactory.create()
    parent2 = factories.ParentEntityFactory.create()
    child.parent_entities.add(parent1, parent2)

    payload = {'data': [{'type': 'entity.parent_entity', 'id': str(parent1.id)}]}
    url = f'/api/v1/entity/child_entity/{child.id}/relationships/parent_entities'
    client = get_api_client(sample_app)

    # add the request method directly to the instance
    def request(method, url, **kwargs):
        headers = client.headers | kwargs.pop('headers', {})
        return client.client.request(method, url, headers=headers, **kwargs)

    client.request = request

    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    child.refresh_from_db()
    assert child.parent_entities.count() == 1
    assert child.parent_entities.filter(id=parent2.id).exists()

    # we check passing an empty list. nothing changes.
    payload = {'data': []}
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    child.refresh_from_db()
    assert child.parent_entities.count() == 1
