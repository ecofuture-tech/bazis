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
from io import StringIO

from django.core.management import CommandError, call_command

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
        'default': {'HOST': 'db', 'PASSWORD': '***', 'OPTIONS': {'sslpassword': 'x'}}
    }
    assert introspect._jsonable('redis://:pw@redis:6379/1') == 'redis://:***@redis:6379/1'
    assert introspect._jsonable('https://key@sentry.io/1', 'SENTRY_DSN') == '***'
    assert introspect._jsonable('x', 'BAZIS_G_AUTH_CLIENT_SECRET') == '***'
    assert introspect._jsonable([{'NAME': 'v'}], 'AUTH_PASSWORD_VALIDATORS') == [{'NAME': 'v'}]
    assert introspect._jsonable(object()) == '<object>'


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
