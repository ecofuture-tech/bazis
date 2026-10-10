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
The helpers of the declarations in the code (`bazis.core.declare`) shared by bazis-permit,
bazis-statusy and bazis-bg; their objects are tested by those packages.
"""

import io
import logging
from types import SimpleNamespace

from django.db import connection, transaction

import entity.models
import pytest

from bazis.core import declare


def test_discover_lists_the_items_of_the_modules_of_the_applications(monkeypatch):
    monkeypatch.setattr(entity.models, 'DECLARED', ['a', 'b'], raising=False)
    assert declare.discover('models', 'DECLARED') == [('entity.models', 'a'), ('entity.models', 'b')]
    # a module without the attribute or no such module: nothing
    assert declare.discover('models', 'MISSING') == []
    assert declare.discover('no_such_module', 'DECLARED') == []


@pytest.mark.django_db(transaction=True)
def test_lock_holds_the_advisory_lock_until_the_end_of_the_transaction():
    def held():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid() "
                'AND ((classid::bigint << 32) | objid::bigint) = %s',
                [declare.ADVISORY_LOCK],
            )
            return cursor.fetchone()[0]

    with transaction.atomic():
        declare.lock()
        assert held() == 1
    assert held() == 0


@pytest.mark.django_db
def test_apply_after_migrate_applies_once_the_migrations_are_complete(monkeypatch):
    applied = []

    def apply(using):
        applied.append(using)
        return ['thing a: created', 'thing b: name changed']

    stdout = io.StringIO()
    assert declare.migrations_complete()
    assert declare.apply_after_migrate(apply, 'entity.Country', 'things', stdout=stdout) == [
        'thing a: created', 'thing b: name changed'
    ]
    assert applied == ['default']
    assert stdout.getvalue() == '  Applied the declared things: 2 change(s)\n'

    stdout = io.StringIO()
    declare.apply_after_migrate(apply, 'entity.Country', 'things', verbosity=2, stdout=stdout)
    assert stdout.getvalue().splitlines()[1:] == ['    thing a: created', '    thing b: name changed']

    # a migrate to an earlier migration: nothing is applied
    monkeypatch.setattr(
        'django.db.migrations.executor.MigrationExecutor.migration_plan', lambda self, targets: [object()]
    )
    assert not declare.migrations_complete()
    applied.clear()
    assert declare.apply_after_migrate(apply, 'entity.Country', 'things') is None
    assert applied == []


def test_apply_after_migrate_skips_a_database_without_the_model(monkeypatch):
    monkeypatch.setattr('django.db.router.allow_migrate_model', lambda using, model: False)
    assert declare.apply_after_migrate(lambda using: 1 / 0, 'entity.Country', 'things') is None


class _Thing(SimpleNamespace):
    """
    An object of a model with a slug and a managed flag (no database).
    """

    rows: dict
    _meta = SimpleNamespace(model_name='thing')

    def save(self, using=None, update_fields=None):
        self.saved = update_fields
        type(self).rows[self.slug] = self


class _Manager:
    def using(self, using):
        return self

    def filter(self, slug):
        return SimpleNamespace(first=lambda: _Thing.rows.get(slug))


_Thing.objects = _Manager()


def test_managed_sync_creates_updates_and_takes_over_the_objects(caplog):
    _Thing.rows = {'free': _Thing(slug='free', name='Admin', managed=False)}

    dry = declare.ManagedSync(dry_run=True)
    dry.object(_Thing, 'new', {'name': 'New'})
    assert dry.changes == ['thing new: created']
    assert set(_Thing.rows) == {'free'}

    sync = declare.ManagedSync()
    obj, changed = sync.object(_Thing, 'new', {'name': 'New'})
    assert (obj.managed, obj.name, changed) == (True, 'New', ['name', 'managed'])
    assert _Thing.rows['new'] is obj

    # applied again: nothing changes
    assert sync.object(_Thing, 'new', {'name': 'New'})[1] == []
    assert sync.object(_Thing, 'new', {'name': 'Renamed'})[1] == ['name']
    assert _Thing.rows['new'].saved == ['name']

    # an object of the slug that is not managed is taken over, with a warning
    with caplog.at_level(logging.WARNING, logger='bazis.core.declare'):
        obj, changed = sync.object(_Thing, 'free', {'name': 'Declared'})
    assert (obj.managed, obj.name, changed) == (True, 'Declared', ['name', 'managed'])
    assert 'thing free exists and is not managed' in caplog.text
    assert sync.changes == [
        'thing new: created', 'thing new: name changed', 'thing free: name, managed changed'
    ]
