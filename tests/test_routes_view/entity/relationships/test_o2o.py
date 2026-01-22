"""
For O2O relations, POST, PATCH, DELETE are tested both from the parent side and from the extended side
"""

import json

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_post_relationships_o2o_from_parent(sample_app):
    """
    Checking setting up the relation from the parent side.
    """
    parent = factories.ParentEntityFactory.create()
    extended_null = factories.ExtendedEntityNullFactory.create(parent_entity=None)
    # Check that there is no relation
    assert extended_null.parent_entity_id is None

    payload = {'data': {'type': 'entity.extended_entity_null', 'id': str(extended_null.id)}}
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/extended_entity_null'
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204

    # Check that the relation has been established
    extended_null.refresh_from_db()
    assert extended_null.parent_entity_id == parent.id

    # Check sending null. Nothing changes.
    payload = {'data': None}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    extended_null.refresh_from_db()
    assert extended_null.parent_entity_id == parent.id


@pytest.mark.django_db(transaction=True)
def test_post_relationships_o2o_from_extended_entity_null(sample_app):
    """
    Checking setting up the relation from the extended side.
    """
    parent = factories.ParentEntityFactory.create()
    extended_null = factories.ExtendedEntityNullFactory.create(parent_entity=None)
    assert extended_null.parent_entity_id is None

    payload = {'data': {'type': 'entity.parent_entity', 'id': str(parent.id)}}
    url = f'/api/v1/entity/extended_entity_null/{extended_null.id}/relationships/parent_entity'
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    extended_null.refresh_from_db()
    assert extended_null.parent_entity_id == parent.id

    # Check sending null. Nothing changes.
    payload = {'data': None}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    extended_null.refresh_from_db()
    assert extended_null.parent_entity_id == parent.id


@pytest.mark.django_db(transaction=True)
def test_patch_relationships_o2o_from_parent(sample_app):
    """
    Checking replacing the relation from the parent side.
    """
    parent = factories.ParentEntityFactory.create()
    ext_old = factories.ExtendedEntityNullFactory.create(parent_entity=parent)
    ext_new = factories.ExtendedEntityNullFactory.create(parent_entity=None)
    assert ext_old.parent_entity == parent
    assert ext_new.parent_entity is None

    payload = {'data': {'type': 'entity.extended_entity_null', 'id': str(ext_new.id)}}
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/extended_entity_null'
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    parent.refresh_from_db()
    ext_old.refresh_from_db()
    ext_new.refresh_from_db()
    assert ext_old.parent_entity is None
    assert ext_new.parent_entity == parent

    # Check sending null. The relation is reset.
    payload = {'data': None}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    ext_new.refresh_from_db()
    assert ext_new.parent_entity == parent


@pytest.mark.django_db(transaction=True)
def test_patch_relationships_o2o_from_extended_entity_null(sample_app):
    """
    Checking replacing the relation from the extended side.
    """
    parent_old = factories.ParentEntityFactory.create()
    parent_new = factories.ParentEntityFactory.create()
    ext = factories.ExtendedEntityNullFactory.create(parent_entity=parent_old)
    # Check the initial state
    assert getattr(parent_old, 'extended_entity_null', None) == ext
    assert getattr(parent_new, 'extended_entity_null', None) is None

    payload = {'data': {'type': 'entity.parent_entity', 'id': str(parent_new.id)}}
    url = f'/api/v1/entity/extended_entity_null/{ext.id}/relationships/parent_entity'
    response = get_api_client(sample_app).patch(url, data=json.dumps(payload))
    assert response.status_code == 204
    ext.refresh_from_db()
    parent_old.refresh_from_db()
    parent_new.refresh_from_db()
    # Check that the relation has been updated
    assert getattr(parent_old, 'extended_entity_null', None) is None
    assert getattr(parent_new, 'extended_entity_null', None) == ext

    # Check sending null. The relation is reset.
    payload = {'data': None}
    response = get_api_client(sample_app).post(url, data=json.dumps(payload))
    assert response.status_code == 204
    parent_new.refresh_from_db()
    assert getattr(parent_new, 'extended_entity_null', None) == ext


@pytest.mark.django_db(transaction=True)
def test_delete_relationships_o2o_from_parent(sample_app):
    """
    Checking deleting the relation from the parent side.
    """
    parent = factories.ParentEntityFactory.create()
    ext = factories.ExtendedEntityNullFactory.create(parent_entity=parent)
    assert getattr(parent, 'extended_entity_null', None) == ext

    payload = {'data': {'type': 'entity.extended_entity_null', 'id': str(ext.id)}}
    url = f'/api/v1/entity/parent_entity/{parent.id}/relationships/extended_entity_null'
    client = get_api_client(sample_app)

    # Add the request method directly to the instance
    def request(method, url, **kwargs):
        headers = client.headers | kwargs.pop('headers', {})
        return client.client.request(method, url, headers=headers, **kwargs)

    client.request = request
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    parent.refresh_from_db()
    assert getattr(parent, 'extended_entity_null', None) is None

    # Check sending null. Nothing changes.
    payload = {'data': None}
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    parent.refresh_from_db()
    assert getattr(parent, 'extended_entity_null', None) is None


@pytest.mark.django_db(transaction=True)
def test_delete_relationships_o2o_from_extended_entity_null(sample_app):
    """
    Checking deleting the relation from the extended side.
    """
    parent = factories.ParentEntityFactory.create()
    ext = factories.ExtendedEntityNullFactory.create(parent_entity=parent)
    assert ext.parent_entity == parent

    payload = {'data': {'type': 'entity.parent_entity', 'id': str(parent.id)}}
    url = f'/api/v1/entity/extended_entity_null/{ext.id}/relationships/parent_entity'
    client = get_api_client(sample_app)

    # Add the request method directly to the instance
    def request(method, url, **kwargs):
        headers = client.headers | kwargs.pop('headers', {})
        return client.client.request(method, url, headers=headers, **kwargs)

    client.request = request
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    ext.refresh_from_db()
    assert ext.parent_entity is None

    # Check sending null. Nothing changes.
    payload = {'data': None}
    response = client.request('DELETE', url, json=payload)
    assert response.status_code == 204
    ext.refresh_from_db()
    assert ext.parent_entity is None
