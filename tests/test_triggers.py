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
`migrate` installs the missing and outdated triggers of the models (pgtrigger) once all the
migrations are applied, only them (a `migrate` with nothing to change runs no DDL), each
waiting for the lock of its table at most `BAZIS_TRIGGERS_LOCK_TIMEOUT`; not after `flush`
or a partial `migrate`; it keeps the triggers no model declares. `bazis_doctor` warns of
both (`bazis.W008`). The tests change the triggers in the transaction of the test, which
rolls them back (but the test of the lock timeout).
"""

import re
import threading
from io import StringIO

from django.core.management import CommandError, call_command
from django.db import connection, connections, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

import pgtrigger
import pytest

from bazis.core import introspect, triggers


URI = 'validation.SessionHost:session_host_period'
SYNC = 'validation.Session:session_period_sync'


@pytest.fixture
def uninstalled(db):
    pgtrigger.uninstall(URI, SYNC)
    assert triggers.triggers_not_installed() == [SYNC, URI]


def warnings_w008():
    return [
        it for it in introspect.check_messages(databases=['default']) if it['id'] == 'bazis.W008'
    ]


def migrate_ddl() -> tuple[list[str], str]:
    """`migrate`: the DDL of the triggers it runs, its output."""
    out = StringIO()
    with CaptureQueriesContext(connection) as queries:
        call_command('migrate', verbosity=1, stdout=out)
    ddl = re.compile(r'\b(CREATE|DROP)\s+(TRIGGER|OR REPLACE FUNCTION|FUNCTION)\b', re.I)
    return [it['sql'] for it in queries if ddl.search(it['sql'])], out.getvalue()


def test_the_test_database_has_the_triggers(db):
    assert triggers.triggers_not_installed() == []
    assert warnings_w008() == []


def test_migrate_installs_the_missing_triggers(uninstalled):
    ddl, out = migrate_ddl()
    assert triggers.triggers_not_installed() == []
    assert 'Installed 2 trigger(s) of the models' in out
    # only the two missing ones (and the function of pgtrigger they call)
    assert {name for it in ddl for name in re.findall(r'pgtrigger_\w+_[0-9a-f]{5}\b', it)} == {
        pgtrigger.registered(uri)[0][1].get_pgid(pgtrigger.registered(uri)[0][0])
        for uri in (URI, SYNC)
    }


def test_migrate_with_the_triggers_installed_runs_no_ddl(db):
    ddl, out = migrate_ddl()
    assert ddl == []
    assert 'trigger' not in out


def test_migrate_installs_a_changed_trigger_again(db):
    ((model, trigger),) = pgtrigger.registered(URI)
    with connection.cursor() as cursor:
        # the hash of the trigger in its comment: as a trigger installed by an older version
        cursor.execute(
            f'COMMENT ON TRIGGER {trigger.get_pgid(model)} ON {model._meta.db_table} IS %s',
            ['outdated'],
        )
    assert triggers.triggers_not_installed() == [URI]
    ddl, out = migrate_ddl()
    assert ddl and all(trigger.get_pgid(model) in it for it in ddl if 'TRIGGER' in it)
    assert triggers.triggers_not_installed() == []
    assert 'Installed 1 trigger(s) of the models' in out


def test_migrate_keeps_the_triggers_no_model_declares(db):
    with connection.cursor() as cursor:
        cursor.execute(
            'CREATE FUNCTION pgtrigger_foreign_abc12() RETURNS trigger AS '
            "$$ BEGIN RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        cursor.execute(
            'CREATE TRIGGER pgtrigger_foreign_abc12 BEFORE INSERT ON validation_room '
            'FOR EACH ROW EXECUTE FUNCTION pgtrigger_foreign_abc12()'
        )
    ddl, _out = migrate_ddl()
    assert ddl == []
    assert triggers.triggers_not_declared() == ['validation_room:pgtrigger_foreign_abc12']
    (warning,) = warnings_w008()
    assert 'no model declares: validation_room:pgtrigger_foreign_abc12' in warning['message']
    assert 'DROP TRIGGER <name> ON <table>' in warning['hint']


def test_flush_does_not_install_them(uninstalled):
    # flush sends post_migrate without a plan
    triggers.install_after_migrate(sender=None, using='default', verbosity=0)
    assert len(triggers.triggers_not_installed()) == 2


def test_partial_migrate_does_not_install_them(uninstalled, monkeypatch):
    monkeypatch.setattr(triggers, 'migrations_complete', lambda using: False)
    triggers.install_after_migrate(sender=None, using='default', verbosity=0, plan=[])
    monkeypatch.undo()
    assert len(triggers.triggers_not_installed()) == 2


def test_doctor_warns_of_the_missing_triggers(uninstalled):
    (warning,) = warnings_w008()
    assert warning['level'] == 'warning'
    assert 'lacks 2 trigger(s)' in warning['message']
    assert URI in warning['message']
    assert 'manage.py migrate --database default' in warning['hint']
    assert 'manage.py pgtrigger install <uri> --database default' in warning['hint']
    assert 'without a URI' in warning['hint']

    pgtrigger.install(URI)
    assert URI not in warnings_w008()[0]['message']


@pytest.mark.django_db(transaction=True)
@override_settings(BAZIS_TRIGGERS_LOCK_TIMEOUT=1)
def test_a_locked_table_fails_the_migrate_after_the_timeout():
    """
    A transaction that holds the table of a missing trigger: the installation waits for
    its lock at most BAZIS_TRIGGERS_LOCK_TIMEOUT and fails, naming the trigger and the fix.
    """
    pgtrigger.uninstall(URI)
    locked, release = threading.Event(), threading.Event()

    def hold():
        with transaction.atomic():
            with connections['default'].cursor() as cursor:
                cursor.execute('LOCK TABLE validation_sessionhost IN ACCESS EXCLUSIVE MODE')
            locked.set()
            release.wait(30)

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert locked.wait(30)
        with pytest.raises(CommandError, match='run `manage.py migrate` again') as raised:
            triggers.install_after_migrate(sender=None, using='default', verbosity=0, plan=[])
        assert URI in str(raised.value)
        assert triggers.triggers_not_installed() == [URI]
    finally:
        release.set()
        holder.join()
        pgtrigger.install(URI)
    assert triggers.triggers_not_installed() == []
