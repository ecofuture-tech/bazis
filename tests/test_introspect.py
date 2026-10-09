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

import json
import time
from io import StringIO

from django.core import checks
from django.core.management import CommandError, call_command
from django.db import connections

import pytest

from bazis.core import introspect


def test_core_manifest_is_valid():
    assert introspect.validate_manifest('bazis.core') == []


def test_packages():
    packages = {it['name']: it for it in introspect.packages()}
    core = packages['bazis']
    assert core['module'] == 'bazis.core'
    assert core['manifest']['package']['name'] == 'bazis'
    assert core['agents_md'].endswith('bazis/core/AGENTS.md')


def test_settings_hide_secrets():
    settings_info = {it['name']: it for it in introspect.settings_info()}
    assert settings_info['SECRET_KEY']['value'] == '***'
    assert isinstance(settings_info['DEBUG']['value'], bool)
    assert settings_info['SECRET_KEY']['module'] == 'bazis.core.conf'
    dynamic = [it for it in settings_info.values() if it['dynamic']]
    assert dynamic
    assert all('value' not in it for it in dynamic)


def test_secrets_are_hidden_at_any_depth():
    databases = {'default': {'HOST': 'db', 'PASSWORD': 'pw', 'OPTIONS': {'sslpassword': 'x'}}}
    assert introspect._jsonable(databases, 'DATABASES') == {
        'default': {'HOST': 'db', 'PASSWORD': '***', 'OPTIONS': {'sslpassword': '***'}}
    }
    assert introspect._jsonable('redis://:pw@redis:6379/1') == 'redis://:***@redis:6379/1'
    assert introspect._jsonable('redis://u:p@ss@redis:6379/1') == 'redis://u:***@redis:6379/1'
    assert introspect._jsonable('https://key@sentry.io/1', 'SENTRY_DSN') == '***'
    assert introspect._jsonable('x', 'BAZIS_G_AUTH_CLIENT_SECRET') == '***'
    assert introspect._jsonable([{'NAME': 'v'}], 'AUTH_PASSWORD_VALIDATORS') == [{'NAME': 'v'}]
    assert introspect._jsonable('users.User', 'AUTH_USER_MODEL') == 'users.User'
    assert introspect._jsonable(object()) == '<object>'


@pytest.mark.parametrize(
    'name',
    ['api_keys', 'apikey', 'private_key_pem', 'connection_string', 'Authorization',
     'x-api-key', 'AWS_SECRET_ACCESS_KEY', 'access_token', 'credentials'],
)
def test_secret_names(name):
    assert introspect._jsonable({name: 'value'}) == {name: '***'}


def test_authorization_values_are_hidden():
    assert introspect._jsonable({'headers': ['Bearer abc', 'Basic YWJj']}) == {
        'headers': ['***', '***']
    }


def test_check_messages(settings):
    settings.ALLOWED_HOSTS = ['*']
    assert 'bazis.W001' not in {it['id'] for it in introspect.check_messages()}
    warning = next(it for it in introspect.check_messages(deploy=True) if it['id'] == 'bazis.W001')
    assert warning['level'] == 'warning'
    assert set(warning) == {'id', 'level', 'message', 'hint', 'object'}


def test_models():
    models = {it['resource']: it for it in introspect.models_info()}
    parent = models['entity.parent_entity']
    relations = {it['name']: it for it in parent['relations']}
    assert relations['child_entities'] == {
        'name': 'child_entities',
        'model': 'entity.ChildEntity',
        'to_many': True,
        'reverse': False,
    }
    assert relations['dependent_entities']['reverse'] is True


def test_routes():
    from bazis.core.app import app

    routes = {it['route_set']: it for it in introspect.routes_info(app)}
    parent = routes['entity.routes.ParentEntityRouteSet']
    assert parent['resource'] == 'entity.parent_entity'
    assert 'bazis.core.routes_abstract.jsonapi.route_base.JsonapiRouteBase' in parent['bases']
    paths = {(it['path'], tuple(it['methods'])) for it in parent['routes']}
    assert ('/api/v1/entity/parent_entity/', ('GET',)) in paths
    assert ('/api/v1/entity/parent_entity/{item_id}/', ('PATCH',)) in paths


def test_introspect_command():
    out = StringIO()
    call_command('bazis_introspect', 'packages', 'routes', stdout=out)
    info = json.loads(out.getvalue())
    assert set(info) == {'packages', 'routes'}
    assert info['routes']


@pytest.mark.parametrize('deploy', [False, True])
def test_doctor_command(settings, deploy):
    settings.ALLOWED_HOSTS = ['*']
    out = StringIO()
    args = ['--json', '--deploy'] if deploy else ['--json']
    try:
        call_command('bazis_doctor', *args, stdout=out)
    except CommandError:
        # the deployment checks of the test settings report errors; the messages are printed
        pass
    ids = {it['id'] for it in json.loads(out.getvalue())}
    assert ('bazis.W001' in ids) is deploy


@pytest.fixture
def database_check():
    """
    Registers a database check (tag `database`) that reports the databases it is run
    against, as the checks of the declarations of bazis-permit and bazis-statusy do, with
    the level given (a warning by default).
    """
    registered = []

    def register(level=checks.Warning):
        def check(app_configs, databases=None, **kwargs):
            return [level(f'checked {",".join(databases or ())}', id='tests.W001')]

        checks.register(check, checks.Tags.database)
        registered.append(check)

    yield register
    for check in registered:
        checks.registry.registry.registered_checks.discard(check)


def doctor(*args) -> tuple[list[dict], bool]:
    out = StringIO()
    try:
        call_command('bazis_doctor', '--json', *args, stdout=out)
    except CommandError:
        failed = True
    else:
        failed = False
    return json.loads(out.getvalue()), failed


def checked(messages: list[dict]) -> list[str]:
    return [it['message'] for it in messages if it['id'] == 'tests.W001']


def unreachable(monkeypatch, host='127.0.0.1', port='1'):
    """
    The database `default` at an address where nothing answers, for the probe of the
    doctor (a connection of its own: the open connection of the test is not changed).
    """
    settings_dict = connections['default'].settings_dict
    monkeypatch.setitem(settings_dict, 'HOST', host)
    monkeypatch.setitem(settings_dict, 'PORT', port)


def test_check_messages_databases(database_check):
    database_check()
    assert checked(introspect.check_messages()) == []
    assert checked(introspect.check_messages(databases=['default'])) == ['checked default']


@pytest.mark.django_db
@pytest.mark.parametrize('args', [(), ('--database', 'default')])
def test_doctor_runs_the_database_checks(database_check, args):
    database_check()
    messages, failed = doctor(*args)
    assert 'bazis.database' not in {it['id'] for it in messages}
    assert checked(messages) == ['checked default']
    assert not failed


@pytest.mark.django_db
def test_doctor_fails_on_an_error_of_a_database_check(database_check):
    database_check(checks.Error)
    messages, failed = doctor()
    assert [it['level'] for it in messages if it['id'] == 'tests.W001'] == ['error']
    assert failed


@pytest.mark.django_db
def test_doctor_skips_the_database_checks_without_the_database(database_check, monkeypatch):
    database_check()
    unreachable(monkeypatch)
    messages, failed = doctor()
    assert checked(messages) == []
    note = next(it for it in messages if it['id'] == 'bazis.database')
    assert note['level'] == 'info'
    assert 'The database default cannot be reached' in note['message']
    assert not failed


@pytest.mark.django_db
def test_doctor_does_not_wait_for_an_unroutable_database(monkeypatch):
    # a private address that no host answers: the probe gives up after PROBE_TIMEOUT
    unreachable(monkeypatch, host='10.255.255.1', port='5432')
    started = time.monotonic()
    messages, failed = doctor()
    assert time.monotonic() - started < 15
    assert 'bazis.database' in {it['id'] for it in messages}
    assert not failed


@pytest.mark.django_db
@pytest.mark.parametrize('silenced', [False, True])
def test_the_info_of_the_database_can_be_silenced(monkeypatch, settings, silenced):
    if silenced:
        settings.SILENCED_SYSTEM_CHECKS = ['bazis.database']
    unreachable(monkeypatch)
    messages, failed = doctor()
    assert ('bazis.database' in {it['id'] for it in messages}) is not silenced
    assert not failed


@pytest.mark.django_db
@pytest.mark.parametrize('alias', ['default', 'no_such_database'])
def test_doctor_fails_without_a_database_given(database_check, monkeypatch, alias):
    database_check()
    unreachable(monkeypatch)
    messages, failed = doctor('--database', alias)
    assert checked(messages) == []
    note = next(it for it in messages if it['id'] == 'bazis.database')
    assert note['level'] == 'error'
    assert f'The database {alias} cannot be reached' in note['message']
    assert failed


@pytest.mark.django_db
def test_doctor_with_databases_reached_and_not(database_check):
    database_check()
    messages, failed = doctor('--database', 'default', '--database', 'no_such_database')
    # the database checks run against the database reached, the other one is an error
    assert checked(messages) == ['checked default']
    notes = [it for it in messages if it['id'] == 'bazis.database']
    assert [(it['level'], 'no_such_database' in it['message']) for it in notes] == [
        ('error', True)
    ]
    assert failed
