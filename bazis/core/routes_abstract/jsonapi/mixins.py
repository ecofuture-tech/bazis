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

from collections.abc import Callable

from django.contrib.auth import get_user_model
from django.db.models import Model, QuerySet

from bazis.core.schemas.enums import AccessAction, ApiAction, CrudApiAction
from bazis.core.schemas.fields import SchemaFields

from .route_base import JsonapiRouteBase


User = get_user_model()


class UniqNumberRouteMixin(JsonapiRouteBase):
    """
    A mixin for routes that handle models with unique numbers.
    It maps the 'number' filter to the 'uniq_number' field in the model.

    Tags: RAG, EXPORT
    """

    abstract: bool = True

    fields = {
        None: SchemaFields(
            include={
                'number': None,
            },
            exclude={
                'uniq_number': None,
            },
        ),
    }

    def __init__(self, *args, **kwargs):
        """
        Initializes the UniqNumberRouteMixin class, setting up the filters_aliases to
        map 'number' to 'uniq_number'.
        """
        super().__init__(*args, **kwargs)
        self.filters_aliases.update(
            {
                'number': 'uniq_number',
            }
        )


class DtRouteMixin(JsonapiRouteBase):
    """
    A mixin class for JsonapiRouteBase that excludes 'dt_created' and 'dt_updated'
    fields during CREATE and UPDATE actions.

    Tags: RAG, EXPORT
    """

    abstract: bool = True

    fields: dict[ApiAction, SchemaFields] = {
        CrudApiAction.CREATE: SchemaFields(
            exclude={'dt_created': None, 'dt_updated': None},
        ),
        CrudApiAction.UPDATE: SchemaFields(
            exclude={'dt_created': None, 'dt_updated': None},
        ),
    }


class RestrictedQsRouteMixin(JsonapiRouteBase):
    """
    A mixin class for JsonapiRouteBase that provides a method to restrict the
    queryset based on access action and user.

    `restrict_queryset` of the default route of a model is the visibility of its objects
    for the other routes: a relationship links only the objects it returns (VIEW, CHANGE
    for a reverse relationship) and `included` shows only those objects.

    Tags: RAG, EXPORT
    """

    abstract: bool = True

    @classmethod
    def restrict_queryset(
        cls, qs: QuerySet, access_action: AccessAction, user: User = None, **kwargs
    ) -> QuerySet:
        """
        Restricts the provided queryset based on the specified access action and user.
        This method can be overridden to apply custom restrictions. The core calls it on
        the class with `user`, the user of the calling route (`inject.user`): None if the
        route has no user, or an anonymous user; neither is authenticated. An override
        must not raise for them: it returns what a user without authentication may see
        (e.g. `qs.none()`), or falls back to a request-level user of its package. The
        route of the request is `JsonApiMixin.CTX_ROUTE.get()`. An override should accept
        `**kwargs`.
        """
        return qs


def restrict_queryset_override(route_cls: type | None):
    """
    The `restrict_queryset` the route class overrides (the attribute of the class of its
    MRO that defines it), or None if it does not override the identity of
    `RestrictedQsRouteMixin` (or has none).

    Tags: RAG, INTERNAL
    """
    for klass in getattr(route_cls, '__mro__', ()):
        if 'restrict_queryset' in vars(klass):
            if klass is RestrictedQsRouteMixin:
                return None
            return vars(klass)['restrict_queryset']
    return None


def route_restrict_queryset(model: type[Model]) -> Callable[..., QuerySet] | None:
    """
    The `restrict_queryset` of the default route of the model, or None if the objects of
    the model are not restricted: not a JSON:API model, no route, or the route does not
    override `restrict_queryset`.

    Tags: RAG, INTERNAL
    """
    get_default_route = getattr(model, 'get_default_route', None)
    route_cls = get_default_route() if get_default_route else None
    if restrict_queryset_override(route_cls) is None:
        return None
    return route_cls.restrict_queryset
