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

import re
from collections.abc import Iterable
from itertools import chain
from typing import Any, TypeVar

from django.db.models import Q, QuerySet

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from pydantic_core import PydanticUndefined

from bazis.core.models_abstract import InitialBase, JsonApiMixin
from bazis.core.utils.functools import get_attr
from bazis.core.utils.orm import set_related_with_delete
from bazis.core.utils.query_complex import QueryToOrm

from .enums import CrudAccessAction
from .utils import get_types
from .validators import field_validate, model_validate


JsonApiDataT = TypeVar('JsonApiDataT')
JsonApiIncludedT = TypeVar('JsonApiIncludedT')
JsonApiMetaT = TypeVar('JsonApiMetaT')


class JsonApiDataSchema(BaseModel):
    """
    Tags: RAG, INTERNAL
    """

    def check_restrict_json(self, f_name, value) -> bool:
        if info := self.attributes.model_fields.get(f_name):
            if restricts := info.json_schema_extra.get('restricts'):
                for r in restricts:
                    if r.startswith('^') and r.endswith('$'):
                        if re.match(r, value):
                            return True
                    elif value == r:
                        return True
                return False
        return True

    def check_restrict_m2m(self, f_name: str, f_values, f_model, rel_obj=None) -> QuerySet:
        if info := self.relationships.model_fields.get(f_name):
            rel_instances = f_model.objects.all()
            if restricts := info.json_schema_extra.get('restricts'):
                restricts = '|'.join(restricts)
                restrict_q = QueryToOrm(restricts, f_model).q

                query = Q(pk__in=[it['id'] for it in f_values['data']]) & restrict_q
                if rel_obj:
                    query |= Q(pk__in=rel_obj.values_list('pk', flat=True)) & ~restrict_q

                return rel_instances.filter(query)
            else:
                return rel_instances.filter(id__in=[it['id'] for it in f_values['data']]).all()

    def check_restrict_rel(self, f_name: str, f_pk, f_model, instance=None) -> bool:
        if info := self.relationships.model_fields.get(f_name):
            if restricts := info.json_schema_extra.get('restricts'):
                restricts = '|'.join(restricts)
                restrict_q = QueryToOrm(restricts, f_model).q
                # if a value was previously set in the relation and the user has no access to it,
                # then the action is not allowed
                if instance and (rel_val := getattr(instance, f_name)):
                    if not f_model.objects.filter(restrict_q & Q(pk=rel_val.pk)).exists():
                        return False

                if f_pk:
                    return f_model.objects.filter(restrict_q & Q(pk=f_pk)).exists()
        return True

    def update_for(self, item: InitialBase) -> Any:
        """
        Validator method to transform an InitialBase instance into a dictionary suitable
        for the schema.
        """
        for f_name, val in self.attributes.model_dump(exclude_unset=True).items():
            if self.check_restrict_json(f_name, val):
                setattr(item, f_name, val)
        # dependencies are set depending on their type
        if self.relationships:
            for f_name, val in self.relationships.model_dump(exclude_unset=True).items():
                field_info = item.get_fields_info().relations.get(f_name)

                if field_info.to_many:
                    rel_obj = getattr(item, f_name)
                    rel_instances = self.check_restrict_m2m(f_name, val, rel_obj.model, rel_obj)
                    if field_info.reverse:
                        # installation with possible deletion
                        set_related_with_delete(rel_obj, rel_instances)
                    else:
                        rel_obj.set(rel_instances)
                else:
                    f_pk = (val.get('data') or {}).get('id')
                    f_model = field_info.related_model
                    if self.check_restrict_rel(f_name, f_pk, f_model, instance=item):
                        setattr(item, f'{f_name}_id', f_pk)

        item.save(force_update=True)
        return item

    def build_for(self) -> Any:
        model = JsonApiMixin.get_model_by_label(self.type)

        fields = {}
        if self.attributes:
            for f_name, val in self.attributes.model_dump(exclude_unset=True).items():
                if self.check_restrict_json(f_name, val):
                    fields[f_name] = val
        # add id
        fields['id'] = self.id

        # dependencies are set depending on their type
        if self.relationships:
            factory = self.schema_factory

            for f_name, val in self.relationships.model_dump(exclude_unset=True).items():
                field_info = factory.fields[f_name].field_db_rel
                if not field_info.to_many:
                    f_pk = (val.get('data') or {}).get('id')
                    f_model = field_info.related_model
                    if self.check_restrict_rel(f_name, f_pk, f_model):
                        fields[f'{f_name}_id'] = f_pk

        # create instance
        return model(**fields)

    def create_for(self, item) -> Any:
        m2m = {}
        # dependencies are set depending on their type
        if self.relationships:
            factory = self.schema_factory

            for f_name, val in self.relationships.model_dump(exclude_unset=True).items():
                field_rel = factory.fields[f_name].field_db_rel
                if field_rel.to_many:
                    m2m[f_name] = self.check_restrict_m2m(f_name, val, field_rel.related_model)

        item.save(force_insert=True)

        # add m2m
        for f_name, objs in m2m.items():
            rel_obj = getattr(item, f_name)
            rel_obj.set(objs)
        return item


class JsonApiTopObjectSchema[JsonApiDataT, JsonApiMetaT](BaseModel):
    """
    Base model for JSON:API top-level object schema with data and optional meta
    fields.

    Tags: RAG, INTERNAL
    """

    data: JsonApiDataT = Field(..., title='Data')
    meta: JsonApiMetaT | None = None

    @model_validator(mode='before')
    @classmethod
    def object_validator(cls, data: Any) -> Any:
        """
        Class-level validator to transform data into the appropriate schema format
        before validation.
        """
        if isinstance(data, InitialBase):
            return cls._validate(data)
        elif isinstance(data, dict):
            return cls._validate(**data)
        return data

    @classmethod
    def _validate(cls: type[BaseModel], data: dict | InitialBase, **kwargs):
        """
        Internal method to validate and transform data into the appropriate schema
        format.
        """
        params = {
            'data': field_validate(cls, 'data', data),
        }
        return kwargs | params


class JsonApiTopIncludedObjectSchema[JsonApiDataT, JsonApiIncludedT, JsonApiMetaT](
    BaseModel
):
    """
    Base model for JSON:API top-level object schema with data, included resources,
    and optional meta fields.

    Tags: RAG, INTERNAL
    """

    data: JsonApiDataT = Field(..., title='Data')
    included: list[JsonApiIncludedT] | None = None
    meta: JsonApiMetaT | None = None

    @model_validator(mode='before')
    @classmethod
    def object_validator(cls, data: Any) -> Any:
        """
        Class-level validator to transform data into the appropriate schema format
        before validation.
        """
        if isinstance(data, JsonApiMixin):
            return cls._validate(data, included=chain(*data.fields_for_included.values()))
        elif isinstance(data, dict):
            return cls._validate(**data)
        return data

    @classmethod
    def _validate(
        cls,
        data: dict | InitialBase,
        included: Iterable[dict | InitialBase] = None,
        **kwargs,
    ):
        """
        Internal method to validate and transform data into the appropriate schema
        format, including nested included resources.
        """
        params = {
            'data': field_validate(cls, 'data', data),
        }

        # we do it this way to check the iterator for emptiness
        included = [it for it in list(included or []) if it]

        if included:
            included_types = get_types(cls.model_fields['included'])

            # collect a dictionary of types
            # when unpacking included from Django objects, only use schemas that match the action
            included_type_map = {
                (
                    t.model_fields['action'].default,
                    t.model_fields['type'].default,
                    (
                        str(t.model_fields['id'].default)
                        if t.model_fields['id'].default not in (None, PydanticUndefined)
                        else None
                    ),
                ): t
                for t in included_types
            }

            schema_included = []
            for i, include in enumerate(included):
                access_action = (
                    include['bs:action']
                    if isinstance(include, dict)
                    else CrudAccessAction.VIEW.value
                )
                item_type = (
                    include['type'] if isinstance(include, dict) else include.get_resource_label()
                )
                item_id = str(include.get('id')) if isinstance(include, dict) else str(include.id)

                # look for a specialized schema
                include_schema = included_type_map.get((access_action, item_type, item_id))

                # if no specialized schema is found, look for a general one
                if not include_schema:
                    include_schema = included_type_map.get((access_action, item_type, None))

                # if a schema is found, apply it
                if include_schema:
                    schema_included.append(model_validate(include_schema, include, ('included', i)))

            params['included'] = schema_included

        return kwargs | params


# the format of links is described in the JSONAPI specification, so the schema is defined here
class PaginationLinks(BaseModel):
    """
    Class representing pagination links as described in the JSONAPI specification.
    """

    first: str | None = None
    last: str | None = None
    prev: str | None = None
    next: str | None = None


class JsonApiTopListSchema[JsonApiDataT, JsonApiMetaT](BaseModel):
    """
    Schema for representing a list of JSONAPI data objects along with pagination
    links and optional metadata.

    Tags: RAG, INTERNAL
    """

    data: list[JsonApiDataT] = Field(..., title='List data')
    links: PaginationLinks
    meta: JsonApiMetaT | None = None

    @model_validator(mode='before')
    @classmethod
    def object_validator(cls, data: Any) -> Any:
        """
        Validator method for JsonApiTopListSchema that processes the input data before
        validation.
        """
        if isinstance(data, list | QuerySet):
            return cls._validate(data)
        elif isinstance(data, dict):
            return cls._validate(**data)
        return data

    @classmethod
    def _validate(cls, data: list | QuerySet, links: PaginationLinks = None, meta=None):
        # determine the list of element types
        elem_types = get_types(cls.model_fields['data'])

        types_map = {get_attr(elem_type, 'schema_key'): elem_type for elem_type in elem_types}
        data_list = [types_map[get_attr(item, '_schema_key')].model_validate(item) for item in data]

        return {
            'data': data_list,
            'links': links or PaginationLinks(),
            'meta': meta,
        }
