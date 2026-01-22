from __future__ import annotations

from django.db.models import ForeignKey, ManyToManyField, Model, OneToOneField, QuerySet

from fastapi import Depends, Query

from bazis.core.routes_abstract.initial import inject_make
from bazis.core.schemas.enums import CrudApiAction
from bazis.core.services.route_ctx import get_route_ctx


class ServiceSparseFieldsets:
    """Service for handling JSON:API sparse fieldsets (fields[type] parameters)."""

    def __init__(
        self,
        route_ctx=Depends(get_route_ctx),
    ):
        self.route_ctx = route_ctx
        self.route_cls = route_ctx.route_cls
        self.fields = None

    @classmethod
    def get_fields_for_queryset(cls, queryset: QuerySet, inject) -> tuple:
        """Get field lists of different types for a model."""
        model_label = queryset.model.get_resource_label()

        k = f'fields_{model_label.replace(".", "_")}'
        v = getattr(inject, k, None)

        if v and isinstance(v, str):
            return cls.get_fields_for_inject_attribute_value(k, v, queryset, inject)
        return None, None, None

    @staticmethod
    def get_fields_for_inject_attribute_value(k: str, v: str, queryset: QuerySet, inject) -> tuple:
        """Parse field string into categorized field lists."""
        simple_fields_names = []
        calc_fields_names = []
        relation_fields_names = []

        v_splitted = [field.strip() for field in v.split(',')]
        setattr(inject, k, v_splitted)

        for field in v_splitted:
            if not hasattr(getattr(queryset.model, field), 'fields_calc'):
                if not isinstance(getattr(queryset.model, field), property):
                    simple_fields_names.append(field)
                    if hasattr(getattr(queryset.model, field), 'rel'):
                        relation_fields_names.append(field)
            else:
                calc_fields_names.append(field)
        return simple_fields_names, calc_fields_names, relation_fields_names

    @classmethod
    def _get_allowed_resource_types(cls, route_cls) -> tuple:
        """Get all allowed resource types by analyzing model relationships."""
        main_type = route_cls.model.get_resource_label()
        include_types = set()

        related_models = cls._get_related_models(route_cls.model)

        for related_model in related_models:
            if hasattr(related_model, 'get_resource_label'):
                related_type = related_model.get_resource_label()
                include_types.add(related_type)

        return main_type, sorted(include_types)

    @staticmethod
    def _get_related_models(model_class: type[Model]) -> set[type[Model]]:
        """Find all models related to the given model."""
        related_models = set()

        # Iterate through all model fields
        for field in model_class._meta.get_fields():
            # Direct relationships (ForeignKey, OneToOne)
            if isinstance(field, (ForeignKey, OneToOneField)):
                if field.related_model and field.related_model != model_class:
                    related_models.add(field.related_model)

            # Many-to-many relationships
            elif isinstance(field, ManyToManyField):
                if field.related_model and field.related_model != model_class:
                    related_models.add(field.related_model)

            # Reverse relationships (related_name)
            elif field.auto_created and not field.concrete:
                if field.related_model and field.related_model != model_class:
                    related_models.add(field.related_model)

        return related_models

    @staticmethod
    def create_inject_class(route_cls) -> tuple:
        """Factory method to create dynamic Inject class for sparse fieldsets."""
        main_type, include_types = ServiceSparseFieldsets._get_allowed_resource_types(route_cls)

        # 1. Class for LIST action (only main model)
        class_attrs_main = {
            '_inject_tags': {CrudApiAction.LIST},
            '__annotations__': {},
        }

        field_name_main = f'fields_{main_type}'.replace('.', '_')
        model_class_main = ServiceSparseFieldsets._get_model_for_type(
            main_type, route_cls, route_cls.model
        )

        if model_class_main:
            available_fields_main = ServiceSparseFieldsets._get_model_fields(model_class_main)
            query_param_main = Query(
                default=None,
                alias=f'fields[{main_type}]',
                description=f'Available fields: {", ".join(available_fields_main)}',
            )
            class_attrs_main['__annotations__'][field_name_main] = str | None
            class_attrs_main[field_name_main] = query_param_main

        OnlyFieldsListClass = type('OnlyFieldsList', (), class_attrs_main)  # noqa: N806

        # 2. Class for RETRIEVE action (all types: main + included)
        class_attrs_retrieve = {
            '_inject_tags': {CrudApiAction.RETRIEVE},
            '__annotations__': {},
        }

        all_types = [main_type] + include_types

        for resource_type in all_types:
            field_name = f'fields_{resource_type}'.replace('.', '_')
            model_class = ServiceSparseFieldsets._get_model_for_type(
                resource_type, route_cls, route_cls.model
            )

            if model_class:
                available_fields = ServiceSparseFieldsets._get_model_fields(model_class)
                query_param = Query(
                    default=None,
                    alias=f'fields[{resource_type}]',
                    description=f'Available fields: {", ".join(available_fields)}',
                )
                class_attrs_retrieve['__annotations__'][field_name] = str | None
                class_attrs_retrieve[field_name] = query_param

        OnlyFieldsRetrieveClass = type('OnlyFieldsRetrieve', (), class_attrs_retrieve)  # noqa: N806

        # 3. Apply inject_make decorator
        return (
            inject_make(CrudApiAction.LIST)(OnlyFieldsListClass),
            inject_make(CrudApiAction.RETRIEVE)(OnlyFieldsRetrieveClass),
        )

    @staticmethod
    def _get_model_for_type(
        resource_type: str, route_cls, main_model: type[Model]
    ) -> type[Model] | None:
        """Find model class for a resource type by analyzing all related models."""

        # Check main model
        if resource_type == main_model.get_resource_label():
            return main_model

        # Search among related models
        related_models = ServiceSparseFieldsets._get_related_models(main_model)

        for related_model in related_models:
            if hasattr(related_model, 'get_resource_label'):
                if resource_type == related_model.get_resource_label():
                    return related_model

        return None

    @classmethod
    def _get_model_fields(cls, model_class: type[Model]) -> list[str]:
        """Get all field names from a model (excluding relationships and id)."""
        fields = []
        # Regular model fields
        for field in model_class._meta.get_fields():
            if field.name != 'id':
                fields.append(field.name)
        # Calculated fields
        calc_fields = [
            name for name in dir(model_class) if hasattr(getattr(model_class, name), 'fields_calc')
        ]
        fields.extend(calc_fields)
        # Property fields
        property_fields = cls.get_properties(model_class)
        fields.extend(property_fields)
        return sorted(fields)

    @staticmethod
    def get_properties(model_cls: type[Model]) -> list[str]:
        """Get all property names from a model class and its ancestors."""
        props = {}
        for cls in model_cls.mro():
            for name, attr in vars(cls).items():
                if name != 'pk' and isinstance(attr, property):
                    props[name] = attr
        return list(props)
