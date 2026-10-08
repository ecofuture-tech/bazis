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

from decimal import Decimal

from django.db.utils import IntegrityError
from django.test.utils import isolate_apps

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


@isolate_apps('entity')
def test_fields_info_of_a_symmetrical_relation_to_itself():
    """
    A symmetrical many-to-many relation of a model to itself has no reverse accessor: it is
    not a relation of the model (its name was None and broke sorting them).
    """
    from django.db import models

    from bazis.core.utils.model_meta import FieldsInfo

    class Node(models.Model):
        linked = models.ManyToManyField('self', blank=True)

        class Meta:
            app_label = 'entity'

    info = FieldsInfo.get_fields_info(Node)

    assert list(info.relations) == ['linked']


@isolate_apps('entity')
def test_translated_fields_in_a_language_without_a_column():
    """
    A translated field with fixed languages (bazis-permit, bazis-statusy) is read, and the
    calculated fields select it, in its first language when the current one has no column.
    """
    from django.db import models
    from django.utils import translation

    from translated_fields import TranslatedField

    from bazis.core.utils.orm import translated_column

    class Item(models.Model):
        title = TranslatedField(models.CharField(max_length=10, blank=True), languages=['en', 'ru'])

        class Meta:
            app_label = 'entity'

    item = Item(title_en='Book', title_ru='Книга')
    with translation.override('de'):
        assert translated_column('title', Item.title) == 'title_en'
        assert item.title == 'Book'
    with translation.override('ru'):
        assert translated_column('title', Item.title) == 'title_ru'
    with translation.override('en-us'):
        assert translated_column('title', Item.title) == 'title_en'


@isolate_apps('entity')
def test_names_of_a_generated_model_do_not_depend_on_the_language():
    """
    `AbstractForeignKey` makes a model for each model of its target (the history of the
    statuses of bazis-statusy). Its names were made strings when the model was created, at
    import, in the language active then: the migrations of a project with `LANGUAGE_CODE`
    `ru` had Russian names and changed with the translations. They stay lazy, and the
    migrations get the source texts (`makemigrations` runs without translations).
    """
    import importlib

    from django.db import models
    from django.db.migrations.state import ModelState
    from django.db.migrations.writer import MigrationWriter
    from django.utils import translation
    from django.utils.functional import Promise
    from django.utils.translation import gettext_lazy as _

    from bazis.core.utils.orm import AbstractForeignKey

    module = importlib.import_module('entity.models')

    class Target(models.Model):
        __module__ = module.__name__

        class Meta:
            abstract = True

    item_fk = AbstractForeignKey(Target)

    class Fact(models.Model):
        __module__ = module.__name__
        item = item_fk

        class Meta:
            abstract = True
            verbose_name = _('Required')
            verbose_name_plural = _('Optional')

    try:
        with translation.override('ru'):

            class Item(Target):
                __module__ = module.__name__

                class Meta:
                    app_label = 'entity'
                    verbose_name = _('Creation time')
                    verbose_name_plural = _('Update time')

        generated = module.ItemFact
    finally:
        models.signals.class_prepared.disconnect(item_fk.finalize)
        vars(module).pop('ItemFact', None)

    opts = generated._meta
    assert isinstance(opts.verbose_name, Promise)
    assert isinstance(opts.verbose_name_plural, Promise)
    with translation.override('ru'):
        assert str(opts.verbose_name) == 'Время добавления. Требуется'
    with translation.override('en'):
        assert str(opts.verbose_name_plural) == 'Update time. Optional'

    # as makemigrations writes them
    options = ModelState.from_model(generated).options
    with translation.override(None):
        written = {
            name: MigrationWriter.serialize(options[name])[0]
            for name in ('verbose_name', 'verbose_name_plural')
        }
    assert written == {
        'verbose_name': "'Creation time. Required'",
        'verbose_name_plural': "'Update time. Optional'",
    }
