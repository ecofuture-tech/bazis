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
The single check of the invariants of an item, `JsonApiMixin.validate_item(changes)`.

Every save of an item whose model overrides `validate_item` (`Model.save()`, also in the
admin, scripts, commands and background tasks) and every change of its many-to-many
relations through a manager validates the item once, after the values are in the
database and before the commit, inside the same transaction: a failure rolls the write
back. A block `defer_validate_item()` collects the writes made inside it and validates
each item once at its end (the routes of the core, the transits of bazis-statusy and
`ValidateItemAdminMixin` use it): with the changes of all the writes of the item.

The models that do not override `validate_item` pay nothing: no snapshot of their
values, no savepoint, no signal receiver.

Not validated (they do not call `save()` or send `m2m_changed`): `QuerySet.update()`,
`bulk_create()`, `bulk_update()`, the reverse foreign key managers with `bulk=True` (their
default), raw SQL, and deletion.

Tags: RAG, EXPORT
"""

from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import m2m_changed

from bazis.core.errors import JsonApiItemInvalidException


@dataclass(frozen=True)
class ItemChanges:
    """
    What a write changed in an item, given to `JsonApiMixin.validate_item`.

    - `fields`: the names of the attributes and foreign keys whose values the write changed
      (all of them for a new item); the timestamps every save sets (`auto_now`) are not
      included;
    - `relations`: the to-many and reverse relations the write set: the relations of the
      request on the API, the many-to-many relations changed through a manager elsewhere;
    - `is_new`: the item was created by the write;
    - `source`: `'create'`, `'update'`, `'relationships'` (the routes of the core),
      `'transit'` (bazis-statusy) or `'save'` (any other save: the admin, scripts,
      commands, background tasks, the side effects of the hooks);
    - `user`: the user of the route (`inject.user`), of the transit or of the admin
      request; None without one (a script, a task).

    Tags: RAG, EXPORT
    """

    fields: frozenset[str]
    relations: frozenset[str]
    is_new: bool
    source: str
    user: Any = None


def validates_items(model) -> bool:
    """
    Whether the items of the model are validated: the model overrides
    `JsonApiMixin.validate_item`.
    """
    has_validate_item = getattr(model, 'has_validate_item', None)
    return bool(has_validate_item and has_validate_item())


# the snapshot of the values of an item loaded from the database, by attname
_SNAPSHOT = '_bazis_validate_snapshot'


def _tracked_fields(model) -> list:
    """
    The fields whose changes `ItemChanges.fields` names: the concrete fields except the
    primary key and the timestamps every save sets (`auto_now`).
    """
    return [
        f
        for f in model._meta.concrete_fields
        if not f.primary_key and not getattr(f, 'auto_now', False)
    ]


def _selected(field, names) -> bool:
    return names is None or field.name in names or field.attname in names


def snapshot_take(item, names: Iterable[str] | None = None):
    """
    Remembers the loaded values of the item (of the fields `names`, all by default) as
    the values in the database, to compare with on the next save.
    """
    names = None if names is None else set(names)
    snapshot = dict(item.__dict__.get(_SNAPSHOT, {}))
    for field in _tracked_fields(type(item)):
        if _selected(field, names) and field.attname in item.__dict__:
            value = item.__dict__[field.attname]
            # the containers of a JSON field can be changed in place
            snapshot[field.attname] = deepcopy(value) if isinstance(value, dict | list) else value
    item.__dict__[_SNAPSHOT] = snapshot


def _same(field, old, new) -> bool:
    try:
        return field.to_python(old) == field.to_python(new)
    except Exception:
        return old == new


def changed_fields(item, is_new: bool, update_fields: Iterable[str] | None) -> set[str]:
    """
    The names of the fields the save writes with a value other than the one in the
    database (all the fields of a new item).
    """
    fields = _tracked_fields(type(item))
    if is_new:
        return {f.name for f in fields}
    names = None if update_fields is None else set(update_fields)
    snapshot = item.__dict__.get(_SNAPSHOT, {})
    return {
        f.name
        for f in fields
        if _selected(f, names)
        and f.attname in item.__dict__
        and (
            f.attname not in snapshot or not _same(f, snapshot[f.attname], item.__dict__[f.attname])
        )
    }


class _Entry:
    __slots__ = ('item', 'fields', 'relations', 'is_new', 'source', 'user')

    def __init__(self, item):
        self.item = item
        self.fields = set()
        self.relations = set()
        self.is_new = False
        self.source = None
        self.user = None


class ValidationScope:
    """
    The items written inside a block `defer_validate_item()`, validated once each.

    Tags: RAG, EXPORT
    """

    def __init__(self, user=None):
        self.user = user
        self._entries: dict[tuple, _Entry] = {}
        self._validated: set[tuple] = set()

    def _entry(self, item) -> _Entry | None:
        if not validates_items(type(item)) or item.pk is None:
            return None
        key = (item._meta.concrete_model, item.pk)
        if key in self._validated:
            # a write of a validated item (validate_item saving it) is not validated again
            return None
        if (entry := self._entries.get(key)) is None:
            entry = self._entries[key] = _Entry(item)
        # the item is validated as it was written last
        entry.item = item
        return entry

    def mark(self, item, source: str, *, relations: Iterable[str] = (), user=None):
        """
        Declares how the item is written (`ItemChanges.source`, the first declaration
        wins), the relations it sets and the user who writes it.
        """
        if entry := self._entry(item):
            entry.source = entry.source or source
            entry.user = entry.user or user
            entry.relations.update(relations)

    def changed(
        self, item, *, fields: Iterable[str] = (), relations: Iterable[str] = (), is_new=False
    ):
        """
        Records a write of the item.
        """
        if entry := self._entry(item):
            entry.is_new = entry.is_new or is_new
            entry.fields.update(fields)
            entry.relations.update(relations)

    def validate(self):
        """
        Validates the items written so far (the block validates the rest at its end). The
        items `validate_item` writes are validated in turn; an item is validated once.
        """
        while self._entries:
            key = next(iter(self._entries))
            entry = self._entries.pop(key)
            self._validated.add(key)
            source = entry.source or 'save'
            changes = ItemChanges(
                fields=frozenset(entry.fields),
                relations=frozenset(entry.relations),
                is_new=entry.is_new,
                source=source,
                user=entry.user if entry.user is not None else self.user,
            )
            try:
                entry.item.validate_item(changes)
            except ValidationError as e:
                raise JsonApiItemInvalidException(e, item=entry.item, source=source) from e


_CTX_SCOPE: ContextVar[ValidationScope | None] = ContextVar(
    'bazis_validate_item_scope', default=None
)


def _route_user():
    # the user of the route of the request, if the save is made in one
    from bazis.core.models_abstract import JsonApiMixin

    return getattr(getattr(JsonApiMixin.CTX_ROUTE.get(), 'inject', None), 'user', None)


@contextmanager
def defer_validate_item(
    item=None,
    *,
    source: str = 'save',
    user=None,
    relations: Iterable[str] = (),
    savepoint: bool = True,
):
    """
    Defers `validate_item` of the items written inside the block to its end: each item is
    validated once, with the changes of all its writes, before the block leaves its
    transaction (`transaction.atomic(savepoint=savepoint)`); a failure raises
    `JsonApiItemInvalidException` and rolls the writes of the block back (without a
    savepoint, inside a transaction, the whole transaction must be rolled back). A block
    inside another one joins it: the outermost block validates. `item` declares the item
    the block writes (saved already) with its `source` and `relations`; `user` is the user
    of the writes (by default the user of the route of the request). Yields the
    `ValidationScope`.

    Tags: RAG, EXPORT
    """
    scope = _CTX_SCOPE.get()
    if scope is not None:
        if item is not None:
            scope.mark(item, source, relations=relations, user=user)
        yield scope
        return

    scope = ValidationScope(user if user is not None else _route_user())
    token = _CTX_SCOPE.set(scope)
    try:
        with transaction.atomic(savepoint=savepoint):
            if item is not None:
                scope.mark(item, source, relations=relations)
            yield scope
            scope.validate()
    finally:
        _CTX_SCOPE.reset(token)


def item_save(item, save, *, update_fields=None, using=None):
    """
    Saves the item with `save()` and validates it: at the end of the block it is saved in,
    or at once, in a savepoint, so that a failure rolls this save back.
    """
    is_new = item._state.adding

    def write(scope):
        save()
        scope.changed(item, fields=changed_fields(item, is_new, update_fields), is_new=is_new)
        snapshot_take(item, update_fields)

    if (scope := _CTX_SCOPE.get()) is not None:
        write(scope)
        return
    with transaction.atomic(using=using), defer_validate_item(savepoint=False) as scope:
        write(scope)


# the many-to-many field of each `through` model the receiver is connected to
_M2M_FIELDS = {}


def _m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """
    Validates the items whose many-to-many relation a manager changed: the item of the
    manager and the items it links or unlinks.
    """
    if action not in ('pre_clear', 'post_add', 'post_remove', 'post_clear'):
        return
    field = _M2M_FIELDS[sender]
    if field.remote_field.symmetrical:
        accessor = field.name
    else:
        accessor = field.remote_field.get_accessor_name()
    own_name, other_name = (accessor, field.name) if reverse else (field.name, accessor)

    if action == 'pre_clear':
        # the linked items are known only before the clear
        if other_name and validates_items(model):
            instance.__dict__[f'_bazis_cleared_{own_name}'] = set(
                getattr(instance, own_name).values_list('pk', flat=True)
            )
        return
    if action == 'post_clear':
        pk_set = instance.__dict__.pop(f'_bazis_cleared_{own_name}', None)

    # the manager has written already, in its own block without a savepoint
    with defer_validate_item(savepoint=False) as scope:
        scope.changed(instance, relations=[own_name])
        if pk_set and other_name and validates_items(model):
            for other in model._base_manager.filter(pk__in=pk_set):
                scope.changed(other, relations=[other_name])


def connect_m2m_signals(models: Iterable):
    """
    Connects the receiver of the many-to-many changes to the relations of the models that
    validate their items (and only to them: a receiver makes Django check the targets of
    every `add()` of the relation with a query).
    """
    for model in models:
        if not validates_items(model):
            continue
        for field in model._meta.get_fields():
            if not field.many_to_many:
                continue
            m2m_field = field.field if field.auto_created and not field.concrete else field
            through = m2m_field.remote_field.through
            if through in _M2M_FIELDS:
                continue
            _M2M_FIELDS[through] = m2m_field
            m2m_changed.connect(
                _m2m_changed,
                sender=through,
                dispatch_uid=f'bazis_validate_item:{through._meta.label}',
            )
