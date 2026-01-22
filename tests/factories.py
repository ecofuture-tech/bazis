import random

import factory
from bazis_test_utils import factories_abstract
from entity.models import (
    ChildEntity,
    DependentEntity,
    DependentEntityNull,
    ExtendedEntity,
    ExtendedEntityNull,
    ParentEntity,
    ParentEntityField,
    ParentEntityState,
    WithProtectedEntity,
    WithProtectedEntitySystem,
)
from factory import fuzzy


class ChildEntityFactory(factories_abstract.ChildEntityFactoryAbstract):
    class Meta:
        model = ChildEntity


class DependentEntityFactory(factories_abstract.DependentEntityFactoryAbstract):
    class Meta:
        model = DependentEntity


class DependentEntityNullFactory(factories_abstract.DependentEntityFactoryAbstract):
    class Meta:
        model = DependentEntityNull


class ExtendedEntityFactory(factories_abstract.ExtendedEntityFactoryAbstract):
    class Meta:
        model = ExtendedEntity


class ExtendedEntityNullFactory(factories_abstract.ExtendedEntityFactoryAbstract):
    class Meta:
        model = ExtendedEntityNull


class ParentEntityFactory(factories_abstract.ParentEntityFactoryAbstract):
    state = fuzzy.FuzzyChoice(ParentEntityState)
    field = factory.List(
        random.sample(
            [
                ParentEntityField.FIRST_FIELD.value,
                ParentEntityField.SECOND_FIELD.value,
                ParentEntityField.THIRD_FIELD.value,
            ],
            2,
        )
    )

    class Meta:
        model = ParentEntity


class WithProtectedEntityFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f'Child {n}')

    class Meta:
        model = WithProtectedEntity


class WithProtectedEntitySystemFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f'Child {n}')

    class Meta:
        model = WithProtectedEntitySystem
