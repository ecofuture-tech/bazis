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
