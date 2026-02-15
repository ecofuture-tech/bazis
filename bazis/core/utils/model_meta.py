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
Django model field introspection utilities for Bazis framework.

Provides comprehensive field metadata extraction including:
- Forward/reverse relationships
- Many-to-many relationships
- Field attributes and validation rules
- ORM path traversal

Usage: FieldsInfo.get_fields_info(model) returns complete field metadata
"""

import logging
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any

from django.core import validators
from django.db import models
from django.db.models import Exists, Field, ForeignKey, OuterRef
from django.db.models.constants import LOOKUP_SEP
from django.utils.functional import cached_property
from django.utils.text import capfirst


logger = logging.getLogger(__name__)


@dataclass
class RelationInfo:
    """
    Metadata container for Django model relationships.

    Describes relationship properties including:
    - Direction (forward/reverse)
    - Cardinality (one-to-many, many-to-many)
    - Through model presence (for M2M)

    Used for schema generation and query building.

    Tags: RAG, EXPORT
    """

    name: str
    model_field: Any
    related_field: Any
    related_model: Any
    to_many: bool
    has_custom_through_model: bool
    reverse: bool
    is_m2m: bool
    through_model: Any = None

    @cached_property
    def m2m_field_rel(self):
        """
        Returns through model field name pointing to related model.
        Used for M2M queryset construction.
        """
        if self.is_m2m:
            if self.reverse:
                path_infos = self.related_field.reverse_path_infos
            else:
                path_infos = self.model_field.path_infos

            for path_info in path_infos:
                if isinstance(path_info.join_field, ForeignKey):
                    return path_info.join_field.name

    @cached_property
    def m2m_field_self(self):
        """
        Returns through model field name pointing to source model.
        Used for M2M queryset construction.
        """
        if self.is_m2m:
            if self.reverse:
                path_infos = self.related_field.path_infos
            else:
                path_infos = self.model_field.reverse_path_infos

            for path_info in path_infos:
                if isinstance(path_info.join_field, ForeignKey):
                    return path_info.join_field.name

    def get_subqueryset(self):
        """
        Generates subquery for related objects in parent context.
        Uses OuterRef for parent-child filtering.

        Returns:
            Queryset annotated for subquery usage
        """
        if self.is_m2m:
            qs = self.related_model.objects.annotate(
                _parent=OuterRef('pk'),
                _is_exist=Exists(
                    self.through_model.objects.filter(
                        **{
                            self.m2m_field_rel: OuterRef('pk'),
                            self.m2m_field_self: OuterRef('_parent'),
                        }
                    )
                ),
            ).filter(_is_exist=True)
        else:
            if self.reverse:
                qs = self.related_model.objects.filter(**{self.related_field.name: OuterRef('pk')})
            else:
                qs = self.related_model.objects.filter(**{'pk': OuterRef(self.name)})
        return qs

    def get_child_queryset(self, parent_pk, child_pk=None):
        """
        Generates queryset for related objects filtered by parent PK.

        Args:
            parent_pk: Parent model primary key
            child_pk: Optional child PK for direct lookup

        Returns:
            Filtered queryset of related objects
        """
        if self.is_m2m:
            qs = self.related_model.objects.annotate(
                _is_exist=Exists(
                    self.through_model.objects.filter(
                        **{self.m2m_field_rel: OuterRef('pk'), self.m2m_field_self: parent_pk}
                    )
                )
            ).filter(_is_exist=True)
        else:
            if self.reverse:
                qs = self.related_model.objects.filter(**{self.related_field.name: parent_pk})
            else:
                if child_pk:
                    qs = self.related_model.objects.filter(**{'pk': child_pk})
                else:
                    qs = self.related_model.objects.filter(**{self.related_field.name: parent_pk})
        return qs


@dataclass
class FieldsInfo:
    """
    Complete field metadata for Django model.

    Provides categorized access to:
    - pk: Primary key field
    - attributes: Non-relational fields
    - forward_relations: ForeignKey and M2M fields
    - reverse_relations: Related objects from other models
    - attributes_and_pk: Combined attributes + PK
    - relations: All relationships (forward + reverse)
    - fields: All fields (attributes + relations)

    Usage:
        info = FieldsInfo.get_fields_info(MyModel)
        field = info.get_field_by_path('user__profile__name')

    Tags: RAG, EXPORT
    """

    pk: Field
    attributes: dict[str, Field]
    forward_relations: dict[str, RelationInfo]
    reverse_relations: dict[str, RelationInfo]
    attributes_and_pk: dict[str, Field]
    relations: dict[str, RelationInfo]
    relations_by_model: dict[Any, list[RelationInfo]]
    fields: dict[str, RelationInfo | Field]

    _cache = {}

    @classmethod
    def get_fields_info(cls, model) -> 'FieldsInfo':
        """
        Factory method: extracts and caches complete field metadata for model.

        Args:
            model: Django model class

        Returns:
            FieldsInfo instance with categorized field data

        RAG keywords: get fields info, model introspection, field discovery
        """
        opts = model._meta.concrete_model._meta

        pk = cls._get_pk(opts)
        attributes = cls._get_attributes(opts)
        forward_relations = cls._get_forward_relationships(opts)
        reverse_relations = cls._get_reverse_relationships(opts)
        attributes_and_pk = cls._merge_attributes_and_pk(pk, attributes)
        relationships = cls._merge_relationships(forward_relations, reverse_relations)

        relations_by_model = defaultdict(list)
        for rel in relationships.values():
            relations_by_model[rel.related_model].append(rel)

        info = FieldsInfo(
            pk,
            attributes,
            forward_relations,
            reverse_relations,
            attributes_and_pk,
            relationships,
            relations_by_model,
            {**attributes_and_pk, **relationships},
        )

        cls._cache[model] = info

        return info

    def get_field_by_path(self, path: str) -> RelationInfo | Field | None:
        """
        Traverses ORM path (e.g., 'user__profile__name') to find final field.

        Args:
            path: Django ORM lookup path with __ separators

        Returns:
            Final field/relation object or None if not found

        Example:
            field = info.get_field_by_path('author__profile__bio')

        RAG keywords: field path, orm path, field lookup, nested field, traverse path
        """
        fields_info = self
        field_info = None
        parts = path.split(LOOKUP_SEP)
        parts_num = len(parts)

        for i, part in enumerate(parts, 1):
            field_info = fields_info.fields.get(part)

            if i < parts_num and isinstance(field_info, RelationInfo):
                fields_info = self.get_fields_info(field_info.related_model)
        return field_info

    @classmethod
    def _get_pk(cls, opts):
        """
        Extracts primary key field, handling multi-table inheritance.
        Traverses parent links to find ultimate PK.

        RAG keywords: primary key, pk field, multi-table inheritance
        """
        pk = opts.pk
        rel = getattr(pk, 'remote_field', None)

        while rel and rel.parent_link:
            # Multi-table inheritance: use parent's PK
            pk = pk.remote_field.model._meta.pk
            rel = pk.remote_field

        return pk

    @classmethod
    def _get_attributes(cls, opts):
        """
        Extracts non-relational serializable fields.
        Excludes ForeignKey, M2M, and non-serializable fields.

        RAG keywords: model attributes, non-relational fields, serializable fields
        """
        attributes = OrderedDict()
        for field in [field for field in opts.fields if field.serialize and not field.remote_field]:
            attributes[field.name] = field

        return attributes

    @classmethod
    def _get_forward_relationships(cls, opts):
        """
        Extracts forward relationships (ForeignKey and M2M fields).

        Returns:
            OrderedDict of field name -> RelationInfo

        RAG keywords: forward relations, foreign key, many to many, forward fields
        """
        forward_relations = OrderedDict()

        # ForeignKey relationships
        for field in [field for field in opts.fields if field.serialize and field.remote_field]:
            forward_relations[field.name] = RelationInfo(
                name=field.name,
                model_field=field,
                related_field=field.remote_field,
                related_model=field.remote_field.model,
                to_many=False,
                has_custom_through_model=False,
                reverse=False,
                is_m2m=False,
            )

        # ManyToMany relationships
        for field in [field for field in opts.many_to_many if field.serialize]:
            forward_relations[field.name] = RelationInfo(
                name=field.name,
                model_field=field,
                related_field=field.remote_field,
                related_model=field.remote_field.model,
                to_many=True,
                has_custom_through_model=(
                    field.remote_field.through and not field.remote_field.through._meta.auto_created
                ),
                reverse=False,
                is_m2m=True,
                through_model=field.remote_field.through,
            )

        return forward_relations

    @classmethod
    def _get_reverse_relationships(cls, opts):
        """
        Extracts reverse relationships (related_name accessors).

        Returns:
            OrderedDict of accessor name -> RelationInfo

        RAG keywords: reverse relations, related name, reverse foreign key, reverse m2m
        """
        reverse_relations = OrderedDict()

        # Reverse ForeignKey relationships
        all_related_objects = [r for r in opts.related_objects if not r.field.many_to_many]
        for relation in all_related_objects:
            accessor_name = relation.get_accessor_name()
            reverse_relations[accessor_name] = RelationInfo(
                name=relation.name,
                model_field=relation,
                related_field=relation.remote_field,
                related_model=relation.related_model,
                to_many=relation.field.remote_field.multiple,
                has_custom_through_model=False,
                reverse=True,
                is_m2m=False,
            )

        # Reverse ManyToMany relationships
        all_related_many_to_many_objects = [r for r in opts.related_objects if r.field.many_to_many]
        for relation in all_related_many_to_many_objects:
            accessor_name = relation.get_accessor_name()
            reverse_relations[accessor_name] = RelationInfo(
                name=relation.name,
                model_field=relation,
                related_field=relation.remote_field,
                related_model=relation.related_model,
                to_many=True,
                has_custom_through_model=(
                    (getattr(relation, 'through', None) is not None)
                    and not relation.through._meta.auto_created
                ),
                reverse=True,
                is_m2m=True,
                through_model=getattr(relation, 'through', None)
            )

        return reverse_relations

    @classmethod
    def _merge_attributes_and_pk(cls, pk, attributes):
        """
        Combines PK and attributes into single dict with 'pk' alias.

        RAG keywords: merge fields, pk and attributes
        """
        attributes_and_pk = OrderedDict()
        attributes_and_pk['pk'] = pk
        if pk:
            attributes_and_pk[pk.name] = pk
        attributes_and_pk.update(attributes)

        return attributes_and_pk

    @classmethod
    def _merge_relationships(cls, forward_relations, reverse_relations):
        """
        Combines forward and reverse relationships.

        RAG keywords: merge relationships, all relations
        """
        return OrderedDict(list(forward_relations.items()) + list(reverse_relations.items()))


# Numeric field types for validation extraction
NUMERIC_FIELD_TYPES = (
    models.IntegerField,
    models.FloatField,
    models.DecimalField,
    models.DurationField,
)


def _needs_label(model_field, field_name):
    """
    Checks if field's verbose_name differs from default capitalized field name.
    Used to determine if explicit label needed in schema.

    RAG keywords: field label, verbose name, needs label
    """
    default_label = field_name.replace('_', ' ').capitalize()
    return capfirst(model_field.verbose_name) != default_label


def _get_detail_view_name(model):
    """
    Generates RESTful detail view name for model.
    Convention: '{modelname}-detail'

    Example: User model -> 'user-detail'

    RAG keywords: view name, detail view, rest view name
    """
    return f'{model._meta.object_name.lower()}-detail'


def get_attributes_kwargs(field_name, model_field):  # noqa: C901
    """
    Extracts Pydantic/serializer field kwargs from Django model field.

    Extracts:
    - Validation rules (max_length, max_value, min_value, etc.)
    - Display metadata (label, help_text)
    - Required/nullable settings
    - Field-specific options (choices, decimal_places, etc.)

    Args:
        field_name: Field name
        model_field: Django Field instance

    Returns:
        Dict of kwargs for schema field definition

    RAG keywords: field kwargs, validation extraction, field attributes,
                  schema generation, django to pydantic
    """
    kwargs = {}
    validator_kwarg = list(model_field.validators)

    # Temporary kwarg for ModelField classes
    kwargs['model_field'] = model_field

    if model_field.verbose_name and _needs_label(model_field, field_name):
        kwargs['label'] = capfirst(model_field.verbose_name)

    if model_field.help_text:
        kwargs['help_text'] = model_field.help_text

    max_digits = getattr(model_field, 'max_digits', None)
    if max_digits is not None:
        kwargs['max_digits'] = max_digits

    decimal_places = getattr(model_field, 'decimal_places', None)
    if decimal_places is not None:
        kwargs['decimal_places'] = decimal_places

    if isinstance(model_field, models.SlugField):
        kwargs['allow_unicode'] = model_field.allow_unicode

    if isinstance(model_field, models.AutoField) or not model_field.editable:
        # Read-only field: return early
        kwargs['read_only'] = True

    if model_field.has_default() or model_field.blank or model_field.null:
        kwargs['required'] = False

    if model_field.null:
        kwargs['allow_null'] = True

    if model_field.blank:
        kwargs['allow_blank'] = True

    if isinstance(model_field, models.FilePathField):
        kwargs['path'] = model_field.path

        if model_field.match is not None:
            kwargs['match'] = model_field.match

        if model_field.recursive is not False:
            kwargs['recursive'] = model_field.recursive

        if model_field.allow_files is not True:
            kwargs['allow_files'] = model_field.allow_files

        if model_field.allow_folders is not False:
            kwargs['allow_folders'] = model_field.allow_folders

    if model_field.choices:
        kwargs['choices'] = model_field.choices
    else:
        # Extract max_value from validators
        max_value = next(
            (
                validator.limit_value
                for validator in validator_kwarg
                if isinstance(validator, validators.MaxValueValidator)
            ),
            None,
        )
        if max_value is not None and isinstance(model_field, NUMERIC_FIELD_TYPES):
            kwargs['max_value'] = max_value
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if not isinstance(validator, validators.MaxValueValidator)
            ]

        # Extract min_value from validators
        min_value = next(
            (
                validator.limit_value
                for validator in validator_kwarg
                if isinstance(validator, validators.MinValueValidator)
            ),
            None,
        )
        if min_value is not None and isinstance(model_field, NUMERIC_FIELD_TYPES):
            kwargs['min_value'] = min_value
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if not isinstance(validator, validators.MinValueValidator)
            ]

        # Remove redundant validators handled by field types
        if isinstance(model_field, models.URLField):
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if not isinstance(validator, validators.URLValidator)
            ]

        if isinstance(model_field, models.EmailField):
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if validator is not validators.validate_email
            ]

        if isinstance(model_field, models.SlugField):
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if validator is not validators.validate_slug
            ]

        if isinstance(model_field, models.GenericIPAddressField):
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if validator is not validators.validate_ipv46_address
            ]

        if isinstance(model_field, models.DecimalField):
            validator_kwarg = [
                validator
                for validator in validator_kwarg
                if not isinstance(validator, validators.DecimalValidator)
            ]

    # Extract max_length
    max_length = getattr(model_field, 'max_length', None)
    if max_length is not None and (
        isinstance(model_field, models.CharField | models.TextField | models.FileField)
    ):
        kwargs['max_length'] = max_length
        validator_kwarg = [
            validator
            for validator in validator_kwarg
            if not isinstance(validator, validators.MaxLengthValidator)
        ]

    # Extract min_length
    min_length = next(
        (
            validator.limit_value
            for validator in validator_kwarg
            if isinstance(validator, validators.MinLengthValidator)
        ),
        None,
    )
    if min_length is not None and isinstance(model_field, models.CharField):
        kwargs['min_length'] = min_length
        validator_kwarg = [
            validator
            for validator in validator_kwarg
            if not isinstance(validator, validators.MinLengthValidator)
        ]

    # Unique constraint error message
    if getattr(model_field, 'unique', False):
        unique_error_message = model_field.error_messages.get('unique', None)
        if unique_error_message:
            unique_error_message = unique_error_message % {
                'model_name': model_field.model._meta.verbose_name,
                'field_label': model_field.verbose_name,
            }

    if validator_kwarg:
        kwargs['validators'] = validator_kwarg

    return kwargs


def get_relation_kwargs(field_name, rel: RelationInfo):  # noqa: C901
    """
    Extracts schema kwargs for relational fields (ForeignKey, M2M).

    Args:
        field_name: Field name
        rel: RelationInfo instance

    Returns:
        Dict of kwargs for relational field schema

    RAG keywords: relation kwargs, foreign key kwargs, m2m kwargs,
                  relationship schema, relational field
    """

    if not hasattr(rel.related_model, '_default_manager'):
        logger.warning('rel.related_model:', rel.related_model)

    kwargs = {
        'queryset': rel.related_model._default_manager,
        'view_name': _get_detail_view_name(rel.related_model),
    }

    if rel.to_many:
        kwargs['many'] = True

    # Apply limit_choices_to filter
    limit_choices_to = rel.reverse is False and rel.model_field.get_limit_choices_to()
    if limit_choices_to:
        if not isinstance(limit_choices_to, models.Q):
            limit_choices_to = models.Q(**limit_choices_to)
        kwargs['queryset'] = kwargs['queryset'].filter(limit_choices_to)

    # M2M with through model is read-only
    if rel.has_custom_through_model:
        kwargs['read_only'] = True
        kwargs.pop('queryset', None)

    # Forward relationship metadata
    if rel.reverse is False:
        if rel.model_field.verbose_name and _needs_label(rel.model_field, field_name):
            kwargs['label'] = capfirst(rel.model_field.verbose_name)
        help_text = rel.model_field.help_text
        if help_text:
            kwargs['help_text'] = help_text
        if not rel.model_field.editable:
            kwargs['read_only'] = True
            kwargs.pop('queryset', None)
        if kwargs.get('read_only', False):
            return kwargs

        if rel.model_field.has_default() or rel.model_field.blank or rel.model_field.null:
            kwargs['required'] = False
        if rel.model_field.null:
            kwargs['allow_null'] = True
        if rel.model_field.validators:
            kwargs['validators'] = rel.model_field.validators
        if rel.to_many and not rel.model_field.blank:
            kwargs['allow_empty'] = False
        if rel.model_field.blank:
            kwargs['allow_blank'] = True

    return kwargs
