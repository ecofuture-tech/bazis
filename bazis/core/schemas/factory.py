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

import dataclasses
from collections.abc import Callable
from copy import deepcopy
from typing import Optional

from django.contrib.postgres import fields as postgres_fields
from django.db import models as django_models
from django.utils.functional import cached_property
from django.utils.timezone import now

from pydantic import BaseModel

from pydantic_core import PydanticUndefined
from translated_fields import TranslatedField

from bazis.core.models_abstract import InitialBase, JsonApiMixin
from bazis.core.utils.functools import get_attr
from bazis.core.utils.model_meta import (
    FieldsInfo,
    get_attributes_kwargs,
    get_relation_kwargs,
)
from bazis.core.utils.orm import calc_cached_property

from .builders import SchemaBuilder, SchemaResourceBuilder
from .enums import (
    ApiAction,
    CrudAccessAction,
    FieldAvail,
    FieldBlank,
    FieldNull,
    FieldRequired,
)
from .fields import (
    SchemaField,
    SchemaFields,
    SchemaInclusion,
    SchemaInclusions,
    SchemaMetaField,
    SchemaMetaFields,
)


@dataclasses.dataclass
class SchemaFactory:
    """
    Factory class for creating schema instances, including fields, meta fields, and
    inclusions.

    Tags: RAG, INTERNAL
    """

    route_cls: type
    model: type[InitialBase]
    api_action: ApiAction
    fields_struct: SchemaFields = None
    meta_fields_struct: SchemaMetaFields = None
    inclusions_struct: SchemaInclusions = None
    parent: Optional['SchemaFactory'] = None

    @cached_property
    def _fields_info(self):
        """
        Cached property that returns information about the fields of the model
        associated with the SchemaFactory.
        """
        return FieldsInfo.get_fields_info(self.model)

    @cached_property
    def schema_name(self):
        """
        Cached property that returns the name of the schema based on the model and API
        action.
        """
        name = (
            f'{self.model.get_resource_label().replace(".", "__")}__schema_{self.api_action.value}'
        )
        if self.parent:
            name = f'{self.parent.schema_name}__{name}'
        return name

    @cached_property
    def pk_field(self) -> SchemaField:
        """
        Cached property that returns the primary key field for the schema.
        """
        return SchemaField(name='id', primary_key=True, field_db_attr=self._fields_info.pk)

    @cached_property
    def fields(self) -> dict[str, SchemaField]:  # noqa: C901
        """
        Cached property that returns a dictionary of schema fields, taking into account
        various attributes and relationships.
        """
        fields_info = self._fields_info

        # original dictionary of fields
        if self.fields_struct and self.fields_struct.origin:
            fields_map = dict(self.fields_struct.origin)
        else:
            # TODO: add retrieval of method attributes from the model

            # handle TranslatedField fields separately
            attributes = {
                f_name: f
                for f_name, f in fields_info.attributes.items()
                if not hasattr(f, '_translated_field_language_code')
            }
            # Iterate over all model attributes
            for attr_name in dir(self.model):
                try:
                    attr = getattr(self.model, attr_name)
                    # Check whether the attribute is a TranslatedField
                    if isinstance(attr, TranslatedField):
                        attributes[attr_name] = attr
                except AttributeError:
                    continue

            fields = list(attributes) + list(fields_info.forward_relations)
            fields_map = {f_name: None for f_name in fields}

        # add the extending dictionary
        if self.fields_struct:
            fields_map.update(self.fields_struct.include)

        # excluded fields
        fields_exclude = set(self.fields_struct.exclude) if self.fields_struct else set()

        def gen():  # noqa: C901
            """
            Generator function that yields schema fields based on the model's attributes and
            relationships.
            """
            for f_name, field in fields_map.items():
                # create a field object or its copy
                if field is None:
                    field = SchemaField(name=f_name)
                else:
                    field = deepcopy(dataclasses.replace(field, name=f_name))

                # if the source is not explicitly specified, use the field name
                if not field.source:
                    field.source = field.name
                # # if the field is serialized as a dependency - the source must be equal to this field
                # if field.name in fields_info.relations:
                #     field.source = field.name

                # this is either a real callable object, or a string/link to an attribute/method of the model
                if field.source in fields_info.fields:
                    pass
                elif isinstance(field.source, Callable):
                    field.read_only = True
                    field.required = False
                elif method := getattr(self.model, field.source, None):
                    field.required = False
                    if not getattr(method, 'fset', None):
                        field.read_only = True
                else:
                    continue

                # if this is a DB field - get the information object
                if field.source in fields_info.relations:
                    field.field_db_rel = fields_info.relations[field.source]
                    field.can_filter = True
                    field.can_order = True
                elif field.source in fields_info.attributes:
                    field.field_db_attr = fields_info.attributes[field.source]
                    field.can_filter = True
                    field.can_order = True
                else:
                    field_model = getattr(self.model, field.source)
                    if isinstance(field_model, calc_cached_property) and field_model.as_filter:
                        field.can_filter = True

                # trying to find auto-assembled field parameters
                field_db = None
                field_params = {}
                field_params_base_field = {}
                if field.field_db_rel:
                    field_params = get_relation_kwargs(field.source, field.field_db_rel)
                    field_db = field.field_db_rel.model_field
                elif field.field_db_attr:
                    field_params = get_attributes_kwargs(field.source, field.field_db_attr)
                    if isinstance(field_params.get('model_field'), postgres_fields.ArrayField):
                        field_params_base_field = get_attributes_kwargs(
                            field.source, field_params['model_field'].base_field
                        )
                    field_db = field.field_db_attr

                choices = field_params_base_field.get('choices') or field_params.get('choices')

                # if the source does not match the field name - the alias is read-only
                if field.source != field.name:
                    field.read_only = True

                # fill in the fields with default values of the db field if necessary
                if field_params:
                    if field.required is None:
                        field.required = field_params.get('required') is not False
                        if field.field_db_rel and field.field_db_rel.reverse:
                            field.required = False
                    if field.read_only is None:
                        field.read_only = field_params.get('read_only') is True
                    if field.write_only is None:
                        field.write_only = field_params.get('write_only') is True
                    if field.nullable is None:
                        if 'allow_null' in field_params:
                            field.nullable = field_params.get('allow_null') is True
                        elif field.field_db_rel and field.field_db_rel.reverse:
                            field.nullable = True
                        else:
                            field.nullable = False
                    if field.blank is None and 'allow_blank' in field_params:
                        field.blank = field_params['allow_blank']

                # trying to find the default value if it is not explicitly set
                if field.default == PydanticUndefined:
                    if getattr(field_db, 'auto_now_add', None):
                        field.default = now()
                    elif getattr(field_db, 'auto_now', None):
                        field.default = now()
                    elif getattr(field_db, 'has_default', None) and field_db.has_default():
                        field.default = field_db.get_default()
                    # if the field is optional - trying to find the default value
                    elif field.required is False:
                        # if the field is optional and can be null - set the default value
                        if field.nullable:
                            field.default = None
                        # if the field is optional and can be empty - set the default value
                        elif field.blank:
                            field.default = ''

                # if a default value is defined - remove the requirement
                if field.default != PydanticUndefined:
                    field.required = False

                # if the field is read-only, then the requirement does not make sense
                if field_db and not field_db.editable:
                    field.required = False

                # perform validation of the consistency of settings
                if field.required:
                    field.read_only = None
                    field.schema_out = None

                # # if the field is read-only, and the schema does not support this - exclude the field
                # if field.read_only and not self.api_action.for_read_only:
                #     fields_exclude.add(field.name)
                # if the field is write-only, and the schema does not support this - exclude the field
                if field.write_only and not self.api_action.for_write_only:
                    fields_exclude.add(field.name)

                # the field can be excluded if it is optional, or if it contains a default value
                if field.name in fields_exclude:
                    continue

                field.title = (
                    field.title
                    or field_params.get('label')
                    or get_attr(field_db, 'verbose_name')
                    or field.name
                )
                field.description = field.description or field_params.get('help_text')
                field.enum = field.enum or list(dict(choices).keys()) if choices else None
                field.enum_dict = field.enum_dict or dict(choices) if choices else None

                if not field.enum and not isinstance(
                    field.field_db_attr, django_models.EmailField | django_models.FileField
                ):
                    field.min_length = (
                        field.min_length
                        or
                        # field_params_base_field.get('min_length') or
                        field_params.get('min_length')
                    )
                    field.max_length = (
                        field.max_length
                        or
                        # field_params_base_field.get('max_length') or
                        field_params.get('max_length')
                    )

                yield field

        return {f.name: f for f in gen()}

    def fields_patch(self, fields_restricts: dict[str, set[str]]) -> list[SchemaField]:  # noqa: C901
        """
        The method creates duplicates of fields and patches them based on the
        restrictions from fields_restricts.
        """
        is_view_op = self.api_action.access_action == CrudAccessAction.VIEW

        def restricts_clean(_restricts: set[str]) -> set[str]:
            # for read operations, remove the restrictions "required", "null", "empty"
            if is_view_op:
                _restricts -= {it.name for it in FieldRequired}
                _restricts -= {it.name for it in FieldNull}
                _restricts -= {it.name for it in FieldBlank}

            # check disabling restrictions
            if FieldRequired.optional.name in _restricts:
                _restricts.discard(FieldRequired.required.name)

            if FieldAvail.enable.name in _restricts:
                _restricts.discard(FieldAvail.readonly.name)
                _restricts.discard(FieldAvail.writeonly.name)
                _restricts.discard(FieldAvail.disable.name)
            if FieldAvail.readonly.name in _restricts:
                _restricts.discard(FieldAvail.disable.name)
            if FieldAvail.writeonly.name in _restricts:
                _restricts.discard(FieldAvail.disable.name)

            if FieldNull.nullable.name in _restricts:
                _restricts.discard(FieldNull.notnull.name)

            if FieldBlank.blank.name in _restricts:
                _restricts.discard(FieldBlank.notblank.name)

            return _restricts

        # find and normalize restrictions for the special field __all__
        restricts_for_all = restricts_clean(fields_restricts.get('__all__') or set())

        fields_result = []
        for field in self.fields_list:
            field = deepcopy(field)

            # find and normalize restrictions for the field
            restricts_for_field = restricts_clean(fields_restricts.get(field.source) or set())

            # initially all restrictions for the field are the restrictions for __all__
            restricts = set(restricts_for_all)
            # but if there are field restrictions in any of the rules, then we remove all restrictions for __all__
            for struct in (FieldRequired, FieldNull, FieldBlank, FieldAvail):
                struct_names = {it.name for it in struct}
                if struct_names & restricts_for_field:
                    restricts -= struct_names

            # add restrictions for the field
            restricts |= restricts_for_field

            if FieldRequired.required.name in restricts:
                field.required = True
            if FieldAvail.readonly.name in restricts:
                field.read_only = True
            elif FieldAvail.writeonly.name in restricts:
                field.write_only = True

            if (not field.required or is_view_op) and FieldAvail.disable.name in restricts:
                continue
            # # if the field is read-only, and the schema does not support this - exclude the field
            # if field.read_only and not self.api_action.for_read_only:
            #     continue
            # if the field is write-only, and the schema does not support this - exclude the field
            if field.write_only and not self.api_action.for_write_only:
                continue

            if FieldNull.notnull.name in restricts:
                field.nullable = False

            if FieldBlank.notblank.name in restricts:
                field.blank = False

            field.restrict_filters = []
            for restrict in restricts:
                if restrict.startswith('filter:'):
                    field.restrict_filters.append(restrict.removeprefix('filter:'))

            fields_result.append(field)

        return fields_result

    @cached_property
    def meta_fields(self) -> dict[str, SchemaMetaField]:
        """
        Cached property that returns a dictionary of meta fields for the schema, taking
        into account inclusions and exclusions.
        """
        if self.meta_fields_struct:
            # original dictionary
            meta_map = dict(self.meta_fields_struct.origin)
            # add the expanding dictionary
            meta_map.update(self.meta_fields_struct.include)
            # collect the result taking into account exceptions
            return {
                k: v if v.name else deepcopy(dataclasses.replace(v, name=k))
                for k, v in meta_map.items()
                if k not in set(self.meta_fields_struct.exclude)
            }
        return {}

    @cached_property
    def inclusions_factory(self) -> dict[str, 'SchemaFactory']:
        """
        Cached property that returns a dictionary of SchemaFactory instances for each
        included relation, based on the inclusion structure.
        """
        if self.inclusions_struct:
            # original dictionary of inclusions
            inclusions_map = dict(self.inclusions_struct.origin)
            # add the expanding dictionary
            inclusions_map.update(self.inclusions_struct.include)
            # excluded fields
            inclusions_map = {
                k: v
                for k, v in inclusions_map.items()
                if k not in set(self.inclusions_struct.exclude)
            }

            return {
                f_name: SchemaFactory(
                    route_cls=self.route_cls,
                    model=self.model._meta.get_field(f_name).related_model,
                    api_action=self.api_action,
                    fields_struct=(
                        inclusion.fields_struct if isinstance(inclusion, SchemaInclusion) else None
                    ),
                    meta_fields_struct=(
                        inclusion.meta_fields_struct
                        if isinstance(inclusion, SchemaInclusion)
                        else None
                    ),
                    parent=self,
                )
                for f_name, inclusion in inclusions_map.items()
                if f_name in self.fields
            }
        else:
            return {}
            # TODO: the approach with outputting all relations as inclusions is too resource-intensive
            # return {f_name: SchemaFactory(
            #     route_cls=self.route_cls,
            #     model=rel.related_model,
            #     api_action=self.api_action,
            #     parent=self
            # ) for f_name, rel in self._fields_info.relations.items() if issubclass(rel.related_model, InitialBase)}

    @cached_property
    def inclusions_default(self) -> dict[str, 'SchemaFactory']:
        """
        Cached property that returns a dictionary of default SchemaFactory instances for
        each included relation, based on the model's relations.
        """
        inclusions = {}
        for f_name, rel in self._fields_info.relations.items():
            model = rel.related_model
            fields_struct = None

            route_cls = None
            if issubclass(model, JsonApiMixin):
                if route_cls := model.get_default_route():
                    fields_struct = route_cls.build_schema_attrs(
                        self.api_action, 'fields', SchemaFields
                    )
            elif not issubclass(model, InitialBase):
                continue

            inclusions[f_name] = SchemaFactory(
                route_cls=route_cls or self.route_cls,
                model=model,
                fields_struct=fields_struct,
                api_action=self.api_action,
                parent=self,
            )
        return inclusions
        # return {f_name: SchemaFactory(
        #     route_cls=self.route_cls,
        #     model=rel.related_model,
        #     api_action=self.api_action,
        #     parent=self
        # ) for f_name, rel in self._fields_info.relations.items() if issubclass(rel.related_model, InitialBase)}

    @cached_property
    def inclusions_factory_with_default(self) -> dict[str, 'SchemaFactory']:
        """
        Cached property that combines the default inclusions with the factory-defined
        inclusions, returning a comprehensive dictionary of SchemaFactory instances.
        """
        inclusions = {}
        if not self.inclusions_struct or not self.inclusions_struct.origin:
            inclusions = self.inclusions_default
        return inclusions | self.inclusions_factory

    @property
    def fields_list(self) -> list[SchemaField]:
        """
        Property that returns a list of SchemaField instances representing the fields of
        the schema.
        """
        return list(self.fields.values())

    @property
    def inclusions_list(self) -> list[type[BaseModel]]:
        """
        Property that returns a list of built schemas for each inclusion, using the
        SchemaResourceBuilder.
        """
        return [
            SchemaResourceBuilder(it, pk_field=it.pk_field, fields=it.fields_list).build(
                is_response_schema=True
            )
            for it in self.inclusions_factory.values()
        ]

    @property
    def meta_fields_list(self) -> list['SchemaMetaField']:
        """
        Property that returns a list of SchemaMetaField instances representing the meta
        fields of the schema.
        """
        return list(self.meta_fields.values())

    @cached_property
    def resource_schema_default(self) -> type[BaseModel]:
        """
        Cached property that returns the default resource schema built using the
        SchemaResourceBuilder.
        """
        return self.build_resource_schema()

    def build_resource_schema(self, **kwargs):
        """
        Method to build a resource schema with optional overrides for specific
        attributes.
        """
        return SchemaResourceBuilder(self).build(**kwargs)

    @cached_property
    def resource_schema_default_response(self) -> type[BaseModel]:
        """
        Cached property that returns the response resource schema built using the
        SchemaResourceBuilder.
        """
        return self.build_resource_schema_response()

    def build_resource_schema_response(self, **kwargs):
        """
        Method to build a resource schema with optional overrides for specific
        attributes.
        """
        return SchemaResourceBuilder(self).build(is_response_schema=True, **kwargs)

    def build_schema(
        self,
        inclusions: list[type[BaseModel]] = None,
        meta_fields: list[SchemaMetaField] = None,
        schema_resource: type[BaseModel] = None,
        is_response_schema: bool = False,
    ):
        """
        Method to build the final schema, combining resource schema, inclusions, and
        meta fields.
        """
        return SchemaBuilder(
            self,
            inclusions=inclusions,  # or self.inclusions_list,
            meta_fields=meta_fields or self.meta_fields_list,
        ).build(
            schema_resource=schema_resource or self.resource_schema_default
            if not is_response_schema
            else self.resource_schema_default_response,
            is_response_schema=is_response_schema,
        )
