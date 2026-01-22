from decimal import Decimal

from django.db.utils import IntegrityError

import pytest
from entity.models import ChildEntity, DependentEntity, ExtendedEntity

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_models():
    # parent_entity
    parent_entity = factories.ParentEntityFactory()
    assert parent_entity.price is not None and isinstance(parent_entity.price, Decimal)
    assert parent_entity.dt_created is not None
    assert parent_entity.dt_updated is not None
    assert parent_entity.dt_created < parent_entity.dt_updated
    assert str(parent_entity) == parent_entity.name

    # child_entity
    child_entity = factories.ChildEntityFactory()
    assert child_entity.child_price is not None and isinstance(child_entity.child_price, Decimal)
    assert child_entity.dt_created is not None
    assert child_entity.dt_updated is not None
    assert child_entity.dt_created < child_entity.dt_updated
    assert str(child_entity) == child_entity.child_name

    parent_entity.child_entities.add(child_entity)
    assert parent_entity.child_entities.count() == 1
    assert parent_entity.child_entities.first() == child_entity

    parent_entity.child_entities.remove(child_entity)
    assert parent_entity.child_entities.count() == 0

    parent_entity.child_entities.add(child_entity)
    parent_entity.child_entities.clear()
    assert parent_entity.child_entities.count() == 0

    parent_entity.child_entities.add(child_entity)
    parent_entity.child_entities.set([])
    assert parent_entity.child_entities.count() == 0

    # dependent_entity
    assert parent_entity.dependent_entities.count() == 1
    dependent_entity_1 = parent_entity.dependent_entities.first()

    with pytest.raises(IntegrityError):
        factories.DependentEntityFactory()

    dependent_entity_2 = factories.DependentEntityFactory(parent_entity=parent_entity)
    assert dependent_entity_2.dependent_price is not None and isinstance(
        dependent_entity_2.dependent_price, Decimal
    )
    assert dependent_entity_2.dt_created is not None
    assert dependent_entity_2.dt_updated is not None
    assert dependent_entity_2.dt_created < dependent_entity_2.dt_updated
    assert str(dependent_entity_2) == dependent_entity_2.dependent_name

    assert parent_entity.dependent_entities.count() == 2

    dependent_entity_2.delete()
    assert parent_entity.dependent_entities.count() == 1

    # extended_entity
    assert parent_entity.extended_entity
    extended_entity = parent_entity.extended_entity

    with pytest.raises(IntegrityError):
        factories.ExtendedEntityFactory()

    with pytest.raises(IntegrityError):
        factories.ExtendedEntityFactory(parent_entity=parent_entity)

    assert parent_entity.extended_entity.extended_price is not None and isinstance(
        parent_entity.extended_entity.extended_price, Decimal
    )

    assert parent_entity.extended_entity.dt_created is not None
    assert parent_entity.extended_entity.dt_updated is not None
    assert parent_entity.extended_entity.dt_created < parent_entity.extended_entity.dt_updated

    assert parent_entity.extended_entity

    parent_entity.delete()

    assert ChildEntity.objects.filter(id=child_entity.id).exists()
    assert not DependentEntity.objects.filter(id=dependent_entity_1.id).exists()
    assert not ExtendedEntity.objects.filter(id=extended_entity.id).exists()
