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

# ruff: noqa: N806

"""
The module provides basic models.
All project models must inherit from :py:class:`InitialBase`.
"""

import logging
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar

from django.apps import apps
from django.contrib.gis.db import models
from django.core.cache import cache
from django.db.models.base import ModelBase
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pydantic import BaseModel, create_model

import sequences
from model_clone import CloneMixin

from bazis.core.triggers import TriggerSetDtCreate, TriggerSetDtUpdate
from bazis.core.utils import triggers
from bazis.core.utils.django_types import TYPES_DJANGO_TO_SCHEMA_LOOKUP
from bazis.core.utils.functools import camel_2_snake, inheritors, snake_2_camel
from bazis.core.utils.model_meta import FieldsInfo
from bazis.core.utils.orm import (
    CalcFieldsValidator,
    calc_cached_property,
    qs_fields_calc,
    qs_fields_related,
)
from bazis.core.utils.schemas import CommonResourceSchema


if TYPE_CHECKING:
    from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
    from bazis.core.schemas import ApiAction

logger = logging.getLogger()

T = TypeVar('T', bound='InitialBase')


# Add methods to QuerySet class
def calc_fields(self, calc_fields_names: list[str], context: dict) -> models.QuerySet:
    """
    Enrichment for calculated fields.
    1. Checks that the requested calculated fields are declared in the model.
    2. Validates each calculated field using CalcFieldsValidator.
    3. Returns a queryset with calculated fields using the qs_fields_calc function.

    Tags: RAG, EXPORT
    """
    CalcFieldsValidator.check_route_declared_calc_fields(calc_fields_names, self.model)

    for calc_field_name in calc_fields_names:
        CalcFieldsValidator.validate_calc_field(
            calc_field_name=calc_field_name,
            model_calc_fields=getattr(self.model, calc_field_name).fields_calc,
            model=self.model,
            context=context,
        )

    return qs_fields_calc(self, calc_fields_names, context)


def relation_field(self, context: dict, fields_allowed: list | None = None) -> models.QuerySet:
    """
    Enrichment for related fields.
    1. Returns a queryset with related fields using the qs_fields_related function.
    2. If fields_allowed is not provided, an empty list is used.

    Tags: RAG, EXPORT
    """
    return qs_fields_related(self, context, fields_allowed or [])


class InitialMetaclass(ModelBase):
    """
    Metaclass for the InitialBase model, which combines Meta attributes across the
    inheritance hierarchy.

    Tags: RAG, INTERNAL
    """

    def __new__(mcs, name, bases, attrs, **kwargs):
        """
        Creates a new class with combined Meta attributes from the inheritance
        hierarchy.
        """

        def meta_inherit():
            """
            Helper function to inherit Meta attributes from base classes.
            """
            return {cl.Meta: True for cl in bases if hasattr(cl, 'Meta')}.keys()

        try:
            # Get the module of the main class
            module = attrs.get('__module__', mcs.__module__)

            # Create MetaBase with correct attributes
            MetaBase = type(
                'MetaBase',
                tuple(meta_inherit()),
                {'__module__': module, '__qualname__': f'{name}.MetaBase'},
            )
        except TypeError:
            print(f'meta_inherit: {meta_inherit()}')
            raise

        if 'Meta' in attrs:
            # Create Meta with correct attributes
            Meta = type(
                'Meta',
                (attrs['Meta'], MetaBase),
                {'__module__': module, '__qualname__': f'{name}.Meta'},
            )
        else:
            # Create Meta with correct attributes
            Meta = type(
                'Meta',
                (MetaBase,),
                {'abstract': False, '__module__': module, '__qualname__': f'{name}.Meta'},
            )

        attrs['Meta'] = Meta

        new_model = super().__new__(mcs, name, bases, attrs, **kwargs)

        if not new_model._meta.abstract:
            # Try to get the QuerySet class
            try:
                queryset_cls = new_model.objects.get_queryset().__class__
            except Exception:
                pass
            else:
                queryset_cls.calc_fields = calc_fields
                queryset_cls.relation_field = relation_field

        return new_model


class InitialBase(CloneMixin, models.Model, metaclass=InitialMetaclass):
    """
    Base model that inherits a custom manager.

    Tags: RAG, EXPORT
    """

    class Meta:
        """
        Meta class for InitialBase, marked as abstract.
        """

        abstract = True

    @classmethod
    def get_queryset(cls, **kwargs):
        """
        Returns a queryset filtered by the provided keyword arguments.
        """

        return cls.objects.filter(**kwargs)

    @classmethod
    def get_inheritors(cls: type[T]) -> Sequence[type[T]]:
        """
        Returns all descendant models of the current class.
        """
        return inheritors(cls)

    @classmethod
    def get_first_real_inheritor(cls) -> type[T] | None:
        """
        Returns the first non-abstract model in the inheritance hierarchy.
        """
        return ([cl for cl in inheritors(cls) if not cl._meta.abstract] + [None])[0]

    @classmethod
    def get_model_by_label(cls, label: str) -> type[T] | None:
        """
        Finds a model by its label.

                :param str label: The model label returned by the get_resource_label() method.
        """
        try:
            app_label, model_name = label.split('.')
            return apps.get_model(app_label, snake_2_camel(model_name))
        except Exception:
            return None

    @classmethod
    def get_resource_app(cls) -> str:
        """
        Returns the application name part of the model label.
        """
        return cls._meta.app_label

    @classmethod
    def get_resource_name(cls) -> str:
        """
        Returns the name part of the model label.
        """
        return camel_2_snake(cls.__name__)

    @classmethod
    def get_resource_label(cls) -> str:
        """
        Returns the full model label, combining application and model names.
        """
        return f'{cls.get_resource_app()}.{cls.get_resource_name()}'

    @classmethod
    def get_content_type(cls):
        """
        Returns ContentType for the current model.

                :return ContentType
        """
        from django.contrib.contenttypes.models import ContentType

        return ContentType.objects.get_for_model(cls)

    @classmethod
    def get_id_example(cls) -> Any:
        """
        Provides an example of the model's primary key. Used for schema generation.

                :return: Returns an example of the primary key for the current model.
        """
        return '1024'

    @classmethod
    def get_fields_info(cls) -> FieldsInfo:
        """
        Returns the structure of the current model's fields.
        """
        return FieldsInfo.get_fields_info(cls)

    @cached_property
    def dict_data(self) -> dict:
        """
        Returns a dictionary of all simple attributes of the model.
                Can be used for internal project purposes.
                Attention! This attribute does not ensure data hiding based on permissions.
        """
        return {
            f_name: getattr(self, f_name)
            for f_name in self.get_fields_info().attributes_and_pk.keys()
        }

    @classmethod
    def get_with_cache(cls, ttl: int = 60, **kwargs) -> T:
        """
        Retrieve an object with caching.
        If the object has not been retrieved before, it will be saved in the cache.
        If the object has been retrieved before, it will be taken from the cache.
        :param ttl: Cache lifetime in seconds.
        :param kwargs: Filter parameters.
        :return: The cached object or a new object retrieved from the database.

        """

        key = f'bs::items::{cls.__name__}::{str(kwargs)}'

        if item := cache.get(key):
            return item

        for item in cls.get_queryset(**kwargs)[:1]:
            cache.set(key, item, ttl)
            return item

    def save(self, *args, **kwargs):
        """
        Saves the current instance and clears related cache patterns.
        """
        super().save(*args, **kwargs)
        cache.delete_pattern(f'bs::items::{type(self).__name__}::*')


class JsonApiMixin(InitialBase):
    """
    Mixin that adds JSON:API support to the InitialBase model.

    Tags: RAG, EXPORT
    """

    CTX_ROUTE: ContextVar['JsonapiRouteBase'] = ContextVar('CTX_ROUTE', default=None)
    CTX_API_ACTION: ContextVar['ApiAction'] = ContextVar('CTX_API_ACTION', default=None)

    _default_route = None

    class Meta:
        """
        Meta class for JsonApiMixin, marked as abstract.
        """

        abstract = True

    @classmethod
    def get_resource_path(cls) -> str:
        """
        Returns the relative path to the model.
        """
        return f'{cls.get_resource_app()}/{cls.get_resource_name()}'

    @classmethod
    def get_resource_schema(cls) -> type[BaseModel]:
        """
        Returns the schema of the model's id/type resource.
        """
        try:
            id_type = TYPES_DJANGO_TO_SCHEMA_LOOKUP[cls.get_fields_info().pk]
        except KeyError:
            id_type = Any

        return create_model(
            f'{cls.__name__}ResourceSchema',
            __base__=CommonResourceSchema,
            id=(id_type, ...),
            type=(str, cls.get_resource_label()),
        )

    @cached_property
    def resource_id(self) -> BaseModel:
        """
        Returns the resource ID of the current object, obtained by the schema
        :py:meth:`~get_resource_schema`.
        """
        return self.get_resource_schema()(
            id=self.pk,
            type=self.get_resource_label(),
        )

    @cached_property
    def fields_for_included(self) -> dict:
        """
        Collects and caches fields that can be included in the response based on the
        request and schema.
        """
        route = self.CTX_ROUTE.get()
        api_action = self.CTX_API_ACTION.get()
        response = {}

        if route:
            # based on the request and schema - determine which fields can be included
            included_fields = set(getattr(route.inject, 'include', None) or set())

            if api_action and included_fields:
                # get the schema depending on the action
                schema_factory = route.schema_factories.get(api_action)

                inclusions_factory = {
                    k: v
                    for k, v in schema_factory.inclusions_factory_with_default.items()
                    if k in included_fields
                }

                fields_relations = self.get_fields_info().relations

                for inc_key, inc_factory in inclusions_factory.items():
                    if relation := fields_relations.get(inc_key):
                        # if it is a relation, get the queryset associated with the current object
                        # and compute the fields
                        queryset = relation.get_child_queryset(self.pk)
                        k = f'fields_{relation.related_model.get_resource_label().replace(".", "_")}'
                        v = getattr(route.inject, k, None)
                        if v:
                            from bazis.core.services.sparse_fieldsets import ServiceSparseFieldsets

                            simple_fields_names, calc_fields_names, relation_fields_names = (
                                ServiceSparseFieldsets.get_fields_for_inject_attribute_value(
                                    k, v, queryset, route.inject
                                )
                            )
                            queryset = queryset.only(*simple_fields_names)
                        else:
                            calc_fields_names = []
                            relation_fields_names = None
                            for k, _ in inc_factory.fields.items():
                                if type(getattr(queryset.model, k)) is calc_cached_property:
                                    calc_fields_names.append(k)
                        if not hasattr(queryset, 'relation_field'):
                            response[inc_key] = queryset
                        context = route.get_fiter_context(route=route)
                        response[inc_key] = queryset.relation_field(
                            context,
                            inc_factory.fields.keys()
                            if relation_fields_names is None
                            else relation_fields_names,
                        ).calc_fields(calc_fields_names, context)

        return response

    @classmethod
    def get_default_route(cls):
        """
        Returns the default route for the model.
        :return: The default route.

        """
        return cls._default_route

    @classmethod
    def set_jsonapi_type(cls, qs: models.QuerySet, context: dict = None) -> models.QuerySet:
        """
        Adds the _jsonapi_type field to the queryset, which contains the resource type.

        :param qs: The queryset to annotate.
        :param context: Optional context (e.g., view-related data).
        :return: The annotated queryset.

        Example for many-to-many calc fields relationships::

            "relationships": {
                "divisions": {
                    "data": [
                        {
                            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "type": "entity.division"
                        }
                    ]
                }
            }
        """
        return qs.annotate(
            _jsonapi_type=models.Value(cls.get_resource_label(), output_field=models.CharField())
        )


@triggers.register(
    TriggerSetDtCreate(),
    TriggerSetDtUpdate(),
)
class DtMixin(InitialBase):
    """
    Mixin for setting the creation/update date/time of an object.
        To work correctly with objects, we explicitly use auto_now_add and auto_now
        so that these fields are close to the actual creation/update time of the object.
        But when saving the object to the database, these fields will be overwritten
        by triggers to the current time according to the database version.

    Tags: RAG, EXPORT
    """

    dt_created = models.DateTimeField(_('Creation time'), db_index=True, auto_now_add=True)
    dt_updated = models.DateTimeField(_('Update time'), db_index=True, auto_now=True)

    class Meta:
        """
        Meta class for DtMixin, marked as abstract.
        """

        abstract = True


class UuidMixin(InitialBase):
    """
    Mixin for setting UUID as the primary key.

    Tags: RAG, EXPORT
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        """
        Meta class for UuidMixin, marked as abstract.
        """

        abstract = True

    @classmethod
    def get_id_example(cls):
        """
        Returns a string representation of a UUID example for the model's primary key.
        This is useful for schema generation.
        """
        return str(uuid.uuid4())


class UniqNumberMixin(InitialBase):
    """
    Mixin for generating a unique, human-readable object number.
    Adds a real field: `uniq_number`, which is incremented in a transaction. In real work,
    it should not be used directly;
    instead, the computed field `number` should be overridden.
    When overriding the `number` method, you must include the construction `super().number()`,
    as it generates a new value
    and sets it in `uniq_number`.

    Tags: RAG, EXPORT
    """

    #: Unique label for internal work with the counter. If it is required that several models maintain
    #: a joint unique number; or if it is required to implement different counters in several proxy models
    #: counters - then this attribute can be overridden
    NUMBER_LABEL: str = None

    uniq_number = models.IntegerField(
        _('Unique object number'),
        default=0,
        help_text=_(
            'This field is generated at the DB level according to the uniqueness principle specified in the model. '
            'It may not be unique across the entire table, as, for example, '
            'in the case of uniqueness only for a given type. The field should not be used directly, '
            'instead, you should use :py:attr:`~number`'
        ),
    )

    class Meta:
        """
        Meta options for the UniqNumberMixin class, specifying that it is an abstract
        model.
        """

        abstract = True

    @cached_property
    def number(self) -> str:
        """
        Calculated number. To access the number, you need to use this field, not :py:attr:`~uniq_number`.
        To modify the generated number, you can override this attribute in the child class.
        Requires `sequences.apps.SequencesConfig` to be included in `INSTALLED_APPS`.
        """
        seq = sequences.Sequence(self.NUMBER_LABEL or self.get_resource_label())
        if self._state.adding and not self.uniq_number:
            self.uniq_number = next(seq)
        return str(self.uniq_number)

    def save(self, *args, **kwargs):
        """
        When saving, this method initializes a unique number for the object.
        """
        _ = self.number
        super().save(*args, **kwargs)


class ProxyTypeManager(models.Manager):
    """
    Custom manager for handling proxy types in models. It ensures that the queryset
    is filtered by the proxy type if the model is a proxy.

    Tags: RAG, EXPORT
    """

    def get_queryset(self):
        """
        Overrides the default queryset to filter by `proxy_type` if the model is a
        proxy.
        """
        qs = super().get_queryset()
        if self.model._meta.proxy:
            return qs.filter(proxy_type=self.model.get_resource_label())
        return qs


class ProxyTypeAbstract(JsonApiMixin):
    """
    Abstract base class for models that need to support proxy types. It includes a
    `proxy_type` field and logic to set the correct class based on the proxy type.

    Tags: RAG, EXPORT
    """

    proxy_type = models.CharField(
        _('Proxy-type of document'), max_length=100, null=True, blank=True
    )

    def __init__(self, *args, **kwargs):
        """
        Initializes the instance and sets the `proxy_type` if it is not already set. If
        the `proxy_type` is set, it attempts to set the class to the corresponding proxy
        model.
        """
        super().__init__(*args, **kwargs)
        if not self.proxy_type and self._meta.proxy:
            self.proxy_type = self.get_resource_label()

        if self.proxy_type:
            if proxy_model := InitialBase.get_model_by_label(self.proxy_type):
                self.__class__ = proxy_model

    class Meta:
        """
        Meta options for the ProxyTypeAbstract class, specifying that it is an abstract
        model.
        """

        abstract = True

    objects = ProxyTypeManager()

    @classmethod
    def set_jsonapi_type(cls, qs: models.QuerySet, context: dict = None) -> models.QuerySet:
        """
        Annotates the queryset with the `_jsonapi_type` field, which contains the
        resource type based on the `proxy_type` field.
        """
        return qs.annotate(_jsonapi_type=models.F('proxy_type'))
