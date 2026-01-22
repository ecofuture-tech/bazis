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

import sys
from collections.abc import Callable
from itertools import groupby
from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from pydantic import (
    BaseModel,
    Field,
    create_model,
    field_validator,
    model_validator,
)

from pydantic_core import PydanticUndefined

from bazis.core.models_abstract import InitialBase, ProxyTypeAbstract
from bazis.core.utils.functools import get_attr, uniq_id

from .cache import get_schema_from_cache, set_schema_to_cache
from .enums import CrudApiAction
from .fields import SchemaField, SchemaMetaField
from .schemas import (
    JsonApiDataSchema,
    JsonApiTopIncludedObjectSchema,
    JsonApiTopListSchema,
    JsonApiTopObjectSchema,
)
from .validators import (
    field_validate,
    not_blank_validator,
    not_null_validator,
    readonly_validator,
)


if TYPE_CHECKING:
    from .factory import SchemaFactory


def schema_create(__model_name, **kwargs):
    """
    Create a Pydantic model schema dynamically with the given model name and
    attributes.
    """
    schema = create_model(__model_name, __module__=__name__, **kwargs)
    setattr(sys.modules[__name__], __model_name, schema)
    schema.schema_name = __model_name
    schema.schema_hash = uniq_id(__model_name)
    return schema


class SchemaBuilder:
    """
    Class responsible for building the final schema, including resource schema,
    inclusions, and meta fields.

    Tags: RAG, INTERNAL
    """

    def __init__(
        self,
        factory,
        *,
        inclusions: list[type[BaseModel]] = None,
        meta_fields: list[SchemaMetaField] = None,
    ):
        """
        Constructor for SchemaBuilder, initializing with factory, inclusions, and meta
        fields.
        """
        self.inclusions = []
        if inclusions:

            def include_cmp(inc_1, inc_2):
                """
                Function to compare two included schemas, checking if they have the same model,
                action, and fields.
                """
                builder_1 = inc_1.builder
                builder_2 = inc_2.builder
                factory_1 = builder_1.factory
                factory_2 = builder_2.factory

                if (
                    factory_1.model == factory_1.model
                    and factory_1.api_action == factory_2.api_action
                    and builder_1.fields == builder_2.fields
                ):
                    return True
                return False

            # if included schemas are passed - remove duplicates and combine schemas with the same fields
            for _key, inc_group in groupby(
                inclusions, lambda inc: inc.model_fields['type'].default
            ):
                inc_group = list(inc_group)
                if len(inc_group) > 1:
                    if all(include_cmp(it, inc_group[0]) for it in inc_group):
                        schema_first = inc_group[0]
                        # create a resource schema
                        schema = schema_create(
                            schema_first.schema_name + '__common',
                            __base__=schema_first,
                            id=(schema_first.__annotations__['id'], Field(...)),
                        )
                        schema.schema_factory = inc_group[0].builder.factory
                        self.inclusions.append(schema)
                    else:
                        self.inclusions.extend(inc_group)
                else:
                    self.inclusions.extend(inc_group)

        self.factory = factory
        self.meta_fields = meta_fields or []

    def _build_meta_schema(self) -> type[BaseModel]:
        """
        Method to build the meta-data schema based on the provided meta fields.
        """
        fields_hash = uniq_id(tuple(f.idx for f in self.meta_fields))
        schema_name = f'_{self.factory.schema_name}__MetaSchema__{fields_hash}'

        if schema := get_schema_from_cache(schema_name):
            return schema

        # any fields that are not links to other resources can be included in attributes
        attributes = {}
        for field in self.meta_fields:
            field_type = Any
            # if there is an extended description of the field, use it
            if field.schema_out:
                field_type = field.schema_out
            else:
                if isinstance(field.source, Callable):
                    field_type = get_type_hints(field.source).get('return')

            # build the field
            attributes[field.name] = (
                field_type | None,
                Field(
                    None,
                    title=field.title and str(field.title),
                    description=field.description and str(field.description),
                ),
            )
        schema = schema_create(schema_name, **attributes)
        set_schema_to_cache(schema_name, schema)
        return schema

    def build(self, schema_resource: type[BaseModel], is_response_schema=None) -> type[BaseModel]:
        """
        Method to build the final schema, combining resource schema, inclusions, and
        meta fields.
        """
        schema_meta = self._build_meta_schema()

        # find the common name of the schema
        if hasattr(schema_resource, '__constraints__'):
            schema_resources = schema_resource.__constraints__
        elif hasattr(schema_resource, '__args__'):
            schema_resources = schema_resource.__args__
        else:
            schema_resources = [schema_resource]
        schema_resources_hash = '__'.join(sorted([str(it.schema_hash) for it in schema_resources]))

        # calculate the schema name taking into account all nested structures
        if is_response_schema:
            schema_name = f'{self.factory.schema_name}_response_schema__{schema_resources_hash}'
        else:
            schema_name = f'{self.factory.schema_name}__{schema_resources_hash}'
        if inclusions_hash := sorted([inc.schema_hash for inc in self.inclusions]):
            schema_name += f'__Inclusions__{inclusions_hash}'

        if schema := get_schema_from_cache(schema_name):
            return schema

        if self.factory.api_action == CrudApiAction.LIST:
            schema = schema_create(
                schema_name,
                __base__=JsonApiTopListSchema[schema_resource, schema_meta],
            )
        elif self.inclusions:
            if len(self.inclusions) == 1:
                IncludedT = self.inclusions[0]  # noqa: N806
            else:
                IncludedT = TypeVar('IncludedT', *self.inclusions)  # noqa

            schema = schema_create(
                schema_name,
                __base__=JsonApiTopIncludedObjectSchema[schema_resource, IncludedT, schema_meta],
            )
        else:
            schema = schema_create(
                schema_name,
                __base__=JsonApiTopObjectSchema[schema_resource, schema_meta],
            )

        schema.schema_factory = self.factory
        set_schema_to_cache(schema_name, schema)

        return schema


class SchemaResourceBuilder:
    """
    Class responsible for building the resource schema, including attributes and
    relationships.
    """

    def __init__(
        self,
        factory: type['SchemaFactory'],
        *,
        pk_field: SchemaField = None,
        fields: list[SchemaField] = None,
    ):
        """
        Constructor for SchemaResourceBuilder, initializing with factory, primary key
        field, and fields.
        """
        self.factory = factory
        self.pk_field = pk_field or factory.pk_field
        self.fields = fields or factory.fields_list

    def build(
        self, _schema_key=None, is_response_schema: bool = False, **defaults
    ) -> type[BaseModel]:
        """
        Method to build the resource schema, including attributes and relationships.
        """
        fields_hash = uniq_id(tuple(f.idx for f in self.fields))

        if is_response_schema:
            schema_name = (
                f'_{self.factory.schema_name}__ResourceSchema_response_schema__{fields_hash}'
            )
        else:
            schema_name = f'_{self.factory.schema_name}__ResourceSchema__{fields_hash}'
        if _schema_key is not None:
            schema_name += f'__{_schema_key}'
        elif defaults:
            schema_name += '__' + '__'.join(
                [f'{k}_{uniq_id(v)}' for k, v in sorted(defaults.items())]
            )

        if schema := get_schema_from_cache(schema_name):
            return schema

        # explicit flag to reset field requirement - set if this is an update
        is_required = (
            False
            if (self.factory.api_action == CrudApiAction.UPDATE or is_response_schema)
            else None
        )

        def data_validator(cls: type[BaseModel], data: Any) -> Any:
            """
            Validator method to transform an InitialBase instance into a dictionary suitable
            for the schema.
            """
            if isinstance(data, InitialBase):
                data = {
                    'id': str(data.id),
                    'type': data.get_resource_label(),
                    'bs:action': self.factory.api_action.access_action.value,
                    'attributes': field_validate(cls, 'attributes', data),
                    'relationships': field_validate(cls, 'relationships', data),
                }
            elif isinstance(data, dict):
                data.setdefault('attributes', {})
                data.setdefault('relationships', {})
            return data

        pk_type = self.pk_field.py_type

        # internal schemas
        attributes_schema = self._build_attributes_schema(
            schema_name, is_required=is_required, defaults=defaults
        )
        relationships_schema = self._build_relationships_schema(
            schema_name, is_required=is_required, defaults=defaults
        )

        # create the resource schema
        schema = schema_create(
            schema_name,
            id=(
                pk_type | None if self.factory.api_action == CrudApiAction.CREATE else pk_type,
                (
                    Field(defaults.pop('id'))
                    if 'id' in defaults
                    else Field(
                        None if self.factory.api_action == CrudApiAction.CREATE else ...,
                    )
                ),
            ),
            type=(str, Field(self.factory.model.get_resource_label())),
            action=(str, Field(self.factory.api_action.access_action.value, alias='bs:action')),
            attributes=(attributes_schema, Field(..., title='Attributes')),
            relationships=(relationships_schema, Field(..., title='Relationships')),
            __validators__={
                'data_validator': model_validator(mode='before')(data_validator),
            },
            __base__=JsonApiDataSchema,
        )
        schema.schema_factory = self.factory
        schema.builder = self
        schema.schema_key = _schema_key
        set_schema_to_cache(schema_name, schema)
        return schema

    def _build_resource_identifier_schema(
        self, model: type[InitialBase], default_id: Any
    ) -> type[BaseModel]:
        """
        Method to build a schema for resource identifiers, including id and type fields.
        """
        schema_name = (
            f'_{self.factory.schema_name}'
            f'__ResourceIdentifierSchema'
            f'__{model.get_resource_label().replace(".", "__")}'
        )
        if schema := get_schema_from_cache(schema_name):
            return schema
        schema = schema_create(
            schema_name,
            id=(str, Field(default_id, json_schema_extra={'example': model.get_id_example()})),
            type=(str, Field(model.get_resource_label())),
        )
        set_schema_to_cache(schema_name, schema)
        return schema

    def _build_attributes_schema(  # noqa: C901
        self, schema_name: str, is_required=None, defaults=None
    ) -> type[BaseModel]:
        """
        Method to build the attributes schema, including validators for null, blank, and
        read-only constraints.
        """
        schema_name = f'_{schema_name}_{is_required}__Attributes'
        if schema := get_schema_from_cache(schema_name):
            return schema

        # dictionary of methods called related to the route
        route_calls = {}
        # any fields that are not links to other resources can be included in attributes
        attributes = {}
        attributes_fields = []
        for field in [field for field in self.fields if not field.field_db_rel or field.schema_out]:
            # if there is an explicit field in the model, get default information from it
            field_type = field.py_type

            # if there is an extended description of the field, use it
            if field.schema_out:
                field_type = field.schema_out
            elif field_type == Any:
                if isinstance(field.source, Callable):
                    field_type = get_type_hints(field.source).get('return')
                    route_calls[field.name] = field.source
                else:
                    field_model = getattr(self.factory.model, field.source)

                    # try to define the model parameter as a method
                    prop_func = None
                    if callable(field_model):
                        prop_func = field_model
                    elif hasattr(field_model, 'fget'):
                        prop_func = field_model.fget
                    elif hasattr(field_model, 'func'):
                        prop_func = field_model.func

                    if prop_func:
                        field_type = get_type_hints(prop_func).get('return')
                    elif not field.field_db_attr:
                        field_type = type(field_model)

            # build the field
            attributes[field.name] = self._field_factory(
                field,
                field_type,
                is_required if is_required is not None else field.required,
                defaults.get(field.name, field.default),
            )
            attributes_fields.append(field)

        def data_validator(cls: type[BaseModel], data: Any) -> Any:
            """
            Validator method to transform an InitialBase instance into a dictionary of
            attributes.
            """
            if isinstance(data, InitialBase):
                model = type(data)

                fields_data = {}

                for field in attributes_fields:
                    if (
                        hasattr(data, 'only_fields')
                        and data.only_fields
                        and field.name not in data.only_fields
                    ):
                        continue
                    if field.name in route_calls:
                        fields_data[field.name] = route_calls[field.name](
                            self.factory.route_cls, data
                        )
                    # check for the presence of a method in the model, not an attribute,
                    # because in case of AttributeError, property will return false
                    elif hasattr(model, field.source):
                        field_item = getattr(data, field.source)

                        if isinstance(field_item, Callable):
                            fields_data[field.name] = field_item()
                        else:
                            fields_data[field.name] = field_item

                data = fields_data
            return data

        # create the attributes schema
        schema = schema_create(
            f'_{schema_name}__Attributes',
            __validators__={
                'not_null_validator': field_validator('*')(not_null_validator),
                'not_blank_validator': field_validator('*')(not_blank_validator),
                'readonly_validator': model_validator(mode='before')(readonly_validator),
                'data_validator': model_validator(mode='before')(data_validator),
            },
            **attributes,
        )
        schema.schema_factory = self.factory

        set_schema_to_cache(schema_name, schema)
        return schema

    def _build_relationships_schema(
        self, schema_name, is_required=None, defaults=None
    ) -> type[BaseModel]:
        """
        Method to build the relationships schema, including validators for null, blank,
        and read-only constraints.
        """
        schema_name = f'_{schema_name}_{is_required}__Relationships'
        if schema := get_schema_from_cache(schema_name):
            return schema

        relationships = {}
        relationships_fields = []
        for field in [
            field for field in self.fields if field.field_db_rel and not field.schema_out
        ]:
            # skip the dependency if it does not belong to project models
            if not issubclass(field.field_db_rel.related_model, InitialBase):
                continue

            # resource identifier schema
            schema_resource_identifier = self._build_resource_identifier_schema(
                field.field_db_rel.related_model,
                field.default,
            )

            schema_data = schema_create(
                f'_{schema_name}__Relationships__Data__{field.name}',
                __validators__={
                    'not_null_validator': field_validator('*')(not_null_validator),
                    'not_blank_validator': field_validator('*')(not_blank_validator),
                },
                data=(
                    (
                        list[schema_resource_identifier]
                        if field.field_db_rel.to_many
                        else schema_resource_identifier
                    )
                    | None,
                    Field(
                        None,
                        title='Data',
                        json_schema_extra={'nullable': field.nullable, 'blank': field.blank},
                    ),
                ),
            )

            # build the field
            relationships[field.name] = self._field_factory(
                field,
                schema_data,
                is_required if is_required is not None else field.required,
                defaults.get(field.name, field.default or None),
            )
            relationships_fields.append(field)

        def data_validator(cls: type[BaseModel], data: Any) -> Any:
            """
            Validator method to transform an InitialBase instance into a dictionary of
            relationships.
            """
            if isinstance(data, InitialBase):
                fields_data = {}
                for field in relationships_fields:
                    if (
                        hasattr(data, 'only_fields')
                        and data.only_fields
                        and field.name not in data.only_fields
                    ):
                        continue
                    if field.field_db_rel.to_many:
                        ids = getattr(data, f'{field.source}__ids', None)

                        if ids is not None:
                            resource_data = [
                                {
                                    'id': str(it['id']),
                                    'type': it['_jsonapi_type'],
                                }
                                for it in sorted(ids, key=lambda it: it['id'])
                            ]
                        else:
                            qs = getattr(data, field.source)
                            qs = (
                                qs.model.set_jsonapi_type(qs, {})
                                .values('id', '_jsonapi_type')
                                .order_by('pk')
                            )
                            resource_data = [
                                {
                                    'id': str(it['id']),
                                    'type': it['_jsonapi_type'],
                                }
                                for it in qs
                            ]
                    else:
                        is_proxy_type = issubclass(
                            field.field_db_rel.related_model, ProxyTypeAbstract
                        )

                        if is_proxy_type:
                            resource_label = get_attr(data, f'{field.source}.proxy_type')
                        else:
                            resource_label = field.field_db_rel.related_model.get_resource_label()

                        if field.field_db_rel.reverse:
                            id_val = get_attr(data, f'{field.source}.id')
                        else:
                            id_val = getattr(data, f'{field.source}_id')

                        if id_val is not None:
                            resource_data = {
                                'id': str(id_val),
                                'type': resource_label,
                            }
                        else:
                            resource_data = None

                    fields_data[field.name] = {'data': resource_data}
                data = fields_data
            return data

        schema = schema_create(
            schema_name,
            __validators__={
                'not_null_validator': field_validator('*')(not_null_validator),
                'not_blank_validator': field_validator('*')(not_blank_validator),
                # disabled because there are operations like transitions that require mandatory fields which may well be read-only
                'readonly_validator': model_validator(mode='before')(readonly_validator),
                'data_validator': model_validator(mode='before')(data_validator),
            },
            **relationships,
        )
        schema.schema_factory = self.factory

        set_schema_to_cache(schema_name, schema)
        return schema

    def _field_factory(
        self, field: SchemaField, field_type: type, required: bool, default: Any
    ) -> tuple[Any, Field]:
        """
        Factory method to create a field with the appropriate type, default value, and
        constraints.
        """
        if (default == Ellipsis or default == PydanticUndefined) and required is False:
            if field.blank is True:
                default = ''
            else:
                default = None
        elif required:
            default = Ellipsis

        field_params = {}
        if field.nullable is not None:
            field_params['nullable'] = field.nullable
        if field.blank is not None:
            field_params['blank'] = field.blank
        if field.read_only:
            field_params['readOnly'] = field.read_only
        if field.write_only:
            field_params['writeOnly'] = field.write_only
        if field.enum:
            field_params['enum'] = field.enum
        if field.enum_dict:
            field_params['enumDict'] = field.enum_dict
        if field.can_filter:
            field_params['filterLabel'] = field.source
        if field.can_order:
            field_params['orderLabel'] = field.source
        if field.restrict_filters:
            field_params['restricts'] = field.restrict_filters

        return (
            # Optional[field_type] if field.nullable else field_type,
            field_type | None if not required and field.nullable else field_type,
            Field(
                default,
                title=field.title and str(field.title),
                description=field.description and str(field.description),
                min_length=field.min_length,
                max_length=field.max_length,
                json_schema_extra=field_params,
            ),
        )


def jsonapi_schema_build(schema_name, id_type, **kwargs):
    """
    Build a JSON:API schema dynamically, utilizing a cache to avoid redundant schema
    creation.
    """
    schema = get_schema_from_cache(schema_name)
    if schema:
        return schema

    schema = create_model(
        schema_name,
        **{
            'id': (id_type, ...),
            'type': (str, ...),
            'attributes': (create_model(f'{schema_name}__attributes', **kwargs), None),
        },
    )
    set_schema_to_cache(schema_name, schema)
    return schema
