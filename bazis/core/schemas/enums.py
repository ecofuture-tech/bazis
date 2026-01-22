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

import enum

from django.db.models import TextChoices
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _


class FieldRequired(TextChoices):
    """
    Enumeration for field requirement status, indicating whether a field is optional
    or required.

    Tags: RAG, EXPORT
    """

    optional = 'optional', _('Optional')
    required = 'required', _('Required')


class FieldAvail(TextChoices):
    """
    Enumeration for field availability status, indicating whether a field is
    enabled, read-only, write-only, or disabled.

    Tags: RAG, EXPORT
    """

    enable = 'enable', _('Enabled')
    readonly = 'readonly', _('Read-only')
    writeonly = 'writeonly', _('Write-only')
    disable = 'disable', _('Disabled')


class FieldNull(TextChoices):
    """
    Enumeration for field nullability status, indicating whether a field is nullable
    or not.

    Tags: RAG, EXPORT
    """

    nullable = 'nullable', 'Null'
    notnull = 'notnull', _('Not null')


class FieldBlank(TextChoices):
    """
    Enumeration for field blank status, indicating whether a field can be blank or
    not.

    Tags: RAG, EXPORT
    """

    blank = 'blank', _('Blank')
    notblank = 'notblank', _('Not blank')


@enum.unique
class AccessAction(enum.Enum):
    """
    Base enumeration for defining access actions.

    Tags: RAG, EXPORT
    """

    ...


class CrudAccessAction(AccessAction):
    """
    Enumeration for CRUD access actions, including view, change, add, and delete.

    Tags: RAG, EXPORT
    """

    VIEW = 'view'
    CHANGE = 'change'
    ADD = 'add'
    DELETE = 'delete'
    CHECK = 'check'


@enum.unique
class ApiAction(enum.Enum):
    """
    Base enumeration for defining API actions with cached properties for access
    action, read-only, and write-only status.

    Tags: RAG, EXPORT
    """

    @cached_property
    def access_action(self):
        """
        Cached property to determine the access action associated with the API action.
        Must be implemented by subclasses.
        """
        raise NotImplementedError()

    @cached_property
    def for_read_only(self):
        """
        Cached property to determine if the API action is for read-only operations.
        """
        return False

    @cached_property
    def for_write_only(self):
        """
        Cached property to determine if the API action is for write-only operations.
        """
        return False


class CrudApiAction(ApiAction):
    """
    Enumeration for CRUD API actions, including list, retrieve, create, update, and
    destroy.

    Tags: RAG, EXPORT
    """

    LIST = 'list'
    RETRIEVE = 'retrieve'
    CREATE = 'create'
    UPDATE = 'update'
    DESTROY = 'destroy'

    @cached_property
    def access_action(self):
        """
        Cached property to map CRUD API actions to their corresponding access actions.
        """
        return {
            CrudApiAction.LIST: CrudAccessAction.VIEW,
            CrudApiAction.RETRIEVE: CrudAccessAction.VIEW,
            CrudApiAction.UPDATE: CrudAccessAction.CHANGE,
            CrudApiAction.CREATE: CrudAccessAction.ADD,
            CrudApiAction.DESTROY: CrudAccessAction.DELETE,
        }[self]

    @cached_property
    def for_read_only(self):
        """
        Cached property to determine if the CRUD API action is for read-only operations.
        """
        if self.access_action in (CrudAccessAction.VIEW,):
            return True
        return False

    @cached_property
    def for_write_only(self):
        """
        Cached property to determine if the CRUD API action is for write-only
        operations.
        """
        if self.access_action in (
            CrudAccessAction.CHANGE,
            CrudAccessAction.ADD,
        ):
            return True
        return False


class HttpMethod(str, enum.Enum):
    GET = 'get'
    POST = 'post'
    PUT = 'put'
    PATCH = 'patch'
    DELETE = 'delete'
    OPTIONS = 'options'
    HEAD = 'head'
    TRACE = 'trace'
    INTERNAL = 'internal'
