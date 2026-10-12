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

from enum import Enum
from typing import Literal

from django.db import models, transaction

from fastapi import HTTPException

from bazis.core.item_validation import reverse_items_link, saves_items
from bazis.core.models_abstract import JsonApiMixin
from bazis.core.routes_abstract.jsonapi.schemas import ResourceIdentifier
from bazis.core.utils.orm import relation_targets


class RelationType(Enum):
    M2M = 'm2m'
    O2M = 'o2m'
    M2O = 'm2o'
    O2O = 'o2o'


class RelationshipsService:
    """
    Service for managing JSON:API relationships.

    Tags: RAG, INTERNAL
    """

    @staticmethod
    def get_relation_type(rel_field) -> RelationType:
        if getattr(rel_field, 'many_to_many', False):
            return RelationType.M2M
        if getattr(rel_field, 'one_to_many', False):
            return RelationType.O2M
        if getattr(rel_field, 'many_to_one', False):
            return RelationType.M2O
        if getattr(rel_field, 'one_to_one', False) or isinstance(rel_field, models.OneToOneRel):
            return RelationType.O2O
        raise HTTPException(status_code=400, detail='Unknown relation type')

    @staticmethod
    def get_relationships_managment_set(
        model: type[JsonApiMixin], item_id: str, related_field_name: str
    ) -> tuple:
        item = model.objects.get(pk=item_id)
        rel_field = model._meta.get_field(related_field_name)
        manager = getattr(item, related_field_name, None)
        return item, rel_field, manager

    @staticmethod
    def parse_ids(rel_field, relationships_data, to_many: bool) -> list:
        """
        The primary keys of the identifiers of the relationship value (validated by the
        update schema of the route: a list for a to-many relationship); an object that
        does not exist is 400.
        """
        data = relationships_data.data
        rows = data if to_many else [data]
        related_model = rel_field.related_model
        ids = {
            related_model._meta.pk.to_python(
                row.id if isinstance(row, ResourceIdentifier) else row['id']
            )
            for row in rows
        }
        existing_ids = set(relation_targets(related_model, ids).values_list('pk', flat=True))
        if missing_ids := ids - existing_ids:
            raise HTTPException(
                400,
                f"Objects of model '{related_model.__name__}' with id {list(missing_ids)} not found",
            )
        return list(existing_ids)

    @staticmethod
    def parse_targets(rel_field, relationships_data, to_many: bool):
        ids = RelationshipsService.parse_ids(rel_field, relationships_data, to_many)
        targets = relation_targets(rel_field.related_model, ids)
        return targets if to_many else targets.get()

    @staticmethod
    @transaction.atomic
    def update_o2o(item, rel_field, new_item, action: str):
        """
        Safely updates a OneToOne relationship.

        Args:
            item: Main object
            rel_field: Relation field
            new_item: New related object (None for remove)
            action: Action ("set", "add", "remove")
        """
        if action == 'remove':
            # Clear the relation
            if isinstance(rel_field, models.OneToOneRel):
                # Reverse relation - find and clear the related object
                related_name = rel_field.field.name
                current_related = getattr(item, rel_field.get_accessor_name(), None)
                if current_related:
                    setattr(current_related, related_name, None)
                    current_related.save(update_fields=[related_name])
            else:
                # Direct relation - clear it on the main object
                setattr(item, rel_field.name, None)
                item.save(update_fields=[rel_field.name])
            return

        # Set a new relation
        related_model = rel_field.related_model

        # Type check for the new object
        if new_item and not isinstance(new_item, related_model):
            raise HTTPException(
                400,
                f"Cannot assign an object of type '{type(new_item).__name__}' to field '{rel_field.name}': "
                f'expected an instance of {related_model.__name__}.',
            )

        if isinstance(rel_field, models.OneToOneRel):
            related_name = rel_field.field.name

            # Remove the current relation from the new object (if any)
            if hasattr(new_item, related_name) and getattr(new_item, related_name):
                current_owner = getattr(new_item, related_name)
                if current_owner != item:
                    setattr(new_item, related_name, None)
                    new_item.save(update_fields=[related_name])

            # Remove the current relation from the main object
            try:
                current_related = getattr(item, rel_field.get_accessor_name(), None)
                if current_related and current_related != new_item:
                    setattr(current_related, related_name, None)
                    current_related.save(update_fields=[related_name])
            except related_model.DoesNotExist:
                pass  # There was no relation - do nothing

            # Set a new relation
            setattr(new_item, related_name, item)
            new_item.save(update_fields=[related_name])

        else:
            # Direct relation
            related_name = rel_field.name

            # Remove the current relation from the new object (if any)
            if hasattr(new_item, related_name) and getattr(new_item, related_name):
                current_owner = getattr(new_item, related_name)
                if current_owner != item:
                    setattr(new_item, related_name, None)
                    new_item.save(update_fields=[related_name])

            # Set a new relation
            setattr(item, related_name, new_item)
            item.save(update_fields=[related_name])

    # Universal method
    @staticmethod
    def apply_relationship_action(
        action: Literal['add', 'set', 'remove'],
        model: type[JsonApiMixin],
        item_id: str,
        related_field_name: str,
        relationships_data,
    ) -> None:
        item, rel_field, manager = RelationshipsService.get_relationships_managment_set(
            model, item_id, related_field_name
        )
        relation_type = RelationshipsService.get_relation_type(rel_field)

        if relation_type in (RelationType.M2M, RelationType.O2M):
            targets = RelationshipsService.parse_targets(
                rel_field, relationships_data, to_many=True
            )
            if relation_type is RelationType.O2M and saves_items(rel_field.related_model):
                # the linked items are saved one by one (their foreign key), to validate them
                # and to lock their parents first (lock_on_write)
                reverse_items_link(manager, action, targets)
            elif action == 'add':
                manager.add(*targets)
            elif action == 'remove':
                manager.remove(*targets)
            elif action == 'set':
                manager.set(targets)

        elif relation_type in (RelationType.O2O, RelationType.M2O):
            target = (
                RelationshipsService.parse_targets(rel_field, relationships_data, to_many=False)
                if relationships_data.data and action != 'remove'
                else None
            )
            RelationshipsService.update_o2o(item, rel_field, target, action)
