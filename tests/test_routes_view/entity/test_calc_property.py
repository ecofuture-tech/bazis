from decimal import Decimal

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_calc_property(sample_app):
    parent_entity = factories.ParentEntityFactory()
    assert not parent_entity.child_entities.exists()

    child_entity1 = factories.ChildEntityFactory(child_is_active=True)
    child_entity2 = factories.ChildEntityFactory(child_is_active=True)
    child_entity3 = factories.ChildEntityFactory(child_is_active=False)
    parent_entity.child_entities.add(child_entity1, child_entity2, child_entity3)

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/parent_entity/{str(parent_entity.id)}?sort=id'
    )

    assert response.status_code == 200

    data = response.json()

    assert data['data']['id'] == str(parent_entity.id)

    assert 'extended_entity_price' in data['data']['attributes']
    assert (
        Decimal(data['data']['attributes']['extended_entity_price'])
        == parent_entity.extended_entity.extended_price
    )

    assert 'active_children' in data['data']['attributes']
    assert len(data['data']['attributes']['active_children']) == 2

    child_entities = sorted([child_entity1, child_entity2], key=lambda x: x.id)
    [et.refresh_from_db() for et in child_entities]

    for it in data['data']['attributes']['active_children']:
        assert it['id'] == str(child_entity1.id) or str(child_entity2.id)
        assert it['child_name'] == child_entity1.child_name or child_entity2.child_name
        assert (
            it['child_description'] == child_entity1.child_description
            or child_entity2.child_description
        )
        assert (
            it['child_is_active'] == child_entity1.child_is_active or child_entity2.child_is_active
        )

    assert 'count_active_children' in data['data']['attributes']
    assert data['data']['attributes']['count_active_children'] == 2

    assert 'has_inactive_children' in data['data']['attributes']
    assert data['data']['attributes']['has_inactive_children'] is True
