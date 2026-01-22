from enum import Enum
from typing import Literal
from uuid import UUID

from django.db import models, transaction

from fastapi import HTTPException

from bazis.core.models_abstract import JsonApiMixin
from bazis.core.routes_abstract.jsonapi.schemas import ResourceIdentifier


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
    def _parse_id(raw_id: str, model: type[models.Model]) -> UUID | int | str:
        pk_field = model._meta.pk
        try:
            if isinstance(pk_field, models.UUIDField):
                return UUID(str(raw_id))
            elif isinstance(pk_field, models.IntegerField):
                return int(raw_id)
            return str(raw_id)
        except (ValueError, TypeError):
            raise HTTPException(
                400, f"Invalid id format '{raw_id}' for model '{model.__name__}'"
            ) from None

    @staticmethod
    def parse_ids(rel_field, relationships_data, to_many: bool) -> list:
        data = relationships_data.data
        if to_many:
            if not isinstance(data, list):
                raise HTTPException(400, f"To-Many field '{rel_field.name}' expects an array of objects")
        else:
            if not isinstance(data, (ResourceIdentifier, dict)):
                raise HTTPException(409, f"To-One field '{rel_field.name}' accepts a single object")

        related_model = rel_field.related_model
        ids = []

        if to_many:
            for row in data:
                obj_id = row.id if isinstance(row, ResourceIdentifier) else row['id']
                ids.append(RelationshipsService._parse_id(obj_id, related_model))
        else:
            obj_id = data.id if isinstance(data, ResourceIdentifier) else data['id']
            ids.append(RelationshipsService._parse_id(obj_id, related_model))

        existing_ids = set(related_model.objects.filter(id__in=ids).values_list('id', flat=True))
        missing_ids = set(ids) - existing_ids
        if missing_ids:
            raise HTTPException(
                400,
                f"Objects of model '{related_model.__name__}' with id {list(missing_ids)} not found",
            )
        return list(existing_ids)

    @staticmethod
    def parse_targets(rel_field, relationships_data, to_many: bool):
        ids = RelationshipsService.parse_ids(rel_field, relationships_data, to_many)
        model = rel_field.related_model
        return model.objects.filter(pk__in=ids) if to_many else model.objects.get(pk=ids[0])

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
            if action == 'add':
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
