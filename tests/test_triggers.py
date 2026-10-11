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
`migrate` installs the triggers of the models (pgtrigger) once all the migrations are
applied, not after `flush` or a partial `migrate`; `bazis_doctor` warns when the database
lacks them (`bazis.W008`). The tests change the triggers in the transaction of the test,
which rolls them back.
"""

from io import StringIO

from django.core.management import call_command

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


def test_the_test_database_has_the_triggers(db):
    assert triggers.triggers_not_installed() == []
    assert warnings_w008() == []


def test_migrate_installs_the_triggers(uninstalled):
    out = StringIO()
    call_command('migrate', verbosity=1, stdout=out)
    assert triggers.triggers_not_installed() == []
    assert 'Installed the triggers of the models' in out.getvalue()


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
    assert 'manage.py pgtrigger install --database default' in warning['hint']

    pgtrigger.install(URI)
    assert URI not in warnings_w008()[0]['message']
