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

import logging
import os
import subprocess
import sys
import types
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import mailers
from django.test import override_settings

import pytest

import bazis
from bazis.core import checks, configure
from bazis.core.mail import DynamicSMTPEmailBackend


STRONG_KEY = 'k3Y-' + 'x9Qz' * 10


@pytest.mark.parametrize(
    'value, expected',
    [
        ('["a", "b"]', ['a', 'b']),
        ("['a', 'b']", ['a', 'b']),
        ('[]', []),
    ],
)
def test_parse_list_env(value, expected):
    assert configure.parse_list_env(value) == expected


@pytest.mark.parametrize('value', ['__import__("os").system("true")', '"a"', '[1, 2]', '{'])
def test_parse_list_env_rejects_non_lists_and_code(value):
    with pytest.raises(ValueError):
        configure.parse_list_env(value)


@pytest.mark.parametrize(
    'secret_key',
    ['', 'short-key', 'a' * 64, 'django-insecure-' + 'x9Qz' * 10],
)
def test_weak_secret_key_is_rejected_outside_debug(secret_key):
    with pytest.raises(ImproperlyConfigured, match='SECRET_KEY'):
        configure.validate_security_settings({'SECRET_KEY': secret_key, 'DEBUG': False})


def test_strong_secret_key_is_accepted():
    values = {'SECRET_KEY': STRONG_KEY, 'DEBUG': False}
    configure.validate_security_settings(values)
    assert values['SECRET_KEY'] == STRONG_KEY


def test_missing_secret_key_is_generated_with_warning_in_debug(caplog):
    values = {'SECRET_KEY': '', 'DEBUG': True}
    with caplog.at_level(logging.WARNING):
        configure.validate_security_settings(values)
    assert len(values['SECRET_KEY']) >= configure.SECRET_KEY_MIN_LENGTH
    assert 'SECRET_KEY is not set' in caplog.text


def test_mailers_use_bazis_backend():
    # the test runner replaces MAILERS with the locmem backend, so the settings module is checked
    assert configure.SETTINGS_MODULE.MAILERS == {
        'default': {'BACKEND': 'bazis.core.mail.DynamicSMTPEmailBackend'}
    }
    assert settings.BAZIS_EMAIL_BACKEND == 'bazis.core.mail.DynamicSMTPEmailBackend'


def test_configure_mailers_keeps_explicit_and_legacy_settings():
    explicit = {'MAILERS': {'default': {}}, 'BAZIS_EMAIL_BACKEND': 'x'}
    configure.configure_mailers(explicit)
    assert explicit['MAILERS'] == {'default': {}}

    legacy = {'EMAIL_HOST': 'smtp.example.com', 'BAZIS_EMAIL_BACKEND': 'x'}
    configure.configure_mailers(legacy)
    assert 'MAILERS' not in legacy


@override_settings(MAILERS={'default': {'BACKEND': 'bazis.core.mail.DynamicSMTPEmailBackend'}})
def test_dynamic_smtp_backend_reads_settings_on_each_connection(db):
    with override_settings(
        BAZIS_EMAIL_HOST='smtp.example.com',
        BAZIS_EMAIL_PORT='2525',
        BAZIS_EMAIL_HOST_USER='user',
        BAZIS_EMAIL_HOST_PASSWORD='secret',
        BAZIS_EMAIL_USE_TLS=True,
    ):
        backend = mailers.default
        assert isinstance(backend, DynamicSMTPEmailBackend)
        assert (backend.host, backend.port, backend.username, backend.password) == (
            'smtp.example.com',
            2525,
            'user',
            'secret',
        )
        assert backend.use_tls is True

    with override_settings(BAZIS_EMAIL_HOST='smtp2.example.com', BAZIS_EMAIL_PORT=''):
        backend = mailers.default
        assert backend.host == 'smtp2.example.com'
        assert backend.port == 25


def test_legacy_email_env_is_mapped(monkeypatch):
    monkeypatch.setenv('BS_EMAIL_HOST', 'legacy.example.com')
    monkeypatch.delenv('BS_BAZIS_EMAIL_HOST', raising=False)
    monkeypatch.setenv('BS_EMAIL_PORT', '25')
    monkeypatch.setenv('BS_BAZIS_EMAIL_PORT', '587')

    configure.apply_legacy_email_env()

    assert os.environ['BS_BAZIS_EMAIL_HOST'] == 'legacy.example.com'
    assert os.environ['BS_BAZIS_EMAIL_PORT'] == '587'


def test_cache_check_requires_redis():
    assert checks.check_cache_backend(None) == []
    # Django resets the cache handlers when CACHES is overridden
    with override_settings(
        CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    ):
        errors = checks.check_cache_backend(None)
    assert [e.id for e in errors] == ['bazis.E001']


def test_configure_mailers_replaces_stock_smtp_backend():
    # with MAILERS the stock SMTP backend reads only OPTIONS, so BAZIS_EMAIL_* would be ignored
    values = {'BAZIS_EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend'}
    configure.configure_mailers(values)
    assert values['MAILERS'] == {
        'default': {'BACKEND': 'bazis.core.mail.DynamicSMTPEmailBackend'}
    }

    console = {'BAZIS_EMAIL_BACKEND': 'django.core.mail.backends.console.EmailBackend'}
    configure.configure_mailers(console)
    assert console['MAILERS'] == {
        'default': {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}
    }


APPS_PY = """
from django.apps import AppConfig


class Config(AppConfig):
    name = 'bazis.contrib.{name}'
"""
CONF_PY = """
from bazis.core.utils.schemas import BazisSettings


class Settings(BazisSettings):
    {name}: str = '{name}'
"""


@pytest.fixture
def fake_contrib(tmp_path, monkeypatch):
    """
    Bazis packages installed in the environment (instead of the real ones): the Django apps
    cfgtest_used and cfgtest_unused (the project uses only the first one) and the package
    cfgtest_library, which is not a Django app and has a nested conf module.
    """
    contrib = tmp_path / 'contrib'
    for name in ('cfgtest_used', 'cfgtest_unused', 'cfgtest_library'):
        package = contrib / name
        package.mkdir(parents=True)
        (package / '__init__.py').write_text('')
        (package / 'conf.py').write_text(CONF_PY.format(name=name.upper()))
        if name != 'cfgtest_library':
            (package / 'apps.py').write_text(APPS_PY.format(name=name))
    nested = contrib / 'cfgtest_library' / 'services'
    nested.mkdir()
    (nested / '__init__.py').write_text('')
    (nested / 'conf.py').write_text(CONF_PY.format(name='CFGTEST_LIBRARY_SERVICES'))

    fake = types.ModuleType('bazis.contrib')
    fake.__path__ = [str(contrib)]
    monkeypatch.setitem(sys.modules, 'bazis.contrib', fake)
    monkeypatch.setattr(bazis, 'contrib', fake, raising=False)
    monkeypatch.setattr(configure, 'PROJECT_MODULE', None)
    monkeypatch.setenv('BS_INSTALLED_APPS', '["bazis.contrib.cfgtest_used"]')
    for name in ('BS_BAZIS_APPS', 'BS_BAZIS_CONFIG_APPS'):
        monkeypatch.delenv(name, raising=False)
    yield
    for name in list(sys.modules):
        if name.startswith('bazis.contrib.cfgtest_'):
            del sys.modules[name]


def contrib_conf_modules():
    return {
        module.__name__
        for module in configure.conf_modules()
        if module.__name__.startswith('bazis.contrib.')
    }


def test_conf_of_all_installed_contrib_packages(fake_contrib):
    # a package declares only settings of its own namespace, so the settings of all
    # installed packages are loaded, also of the ones the project does not use
    assert contrib_conf_modules() == {
        'bazis.contrib.cfgtest_used.conf',
        'bazis.contrib.cfgtest_unused.conf',
        'bazis.contrib.cfgtest_library.conf',
        'bazis.contrib.cfgtest_library.services.conf',
    }


@pytest.mark.parametrize(
    'variable, value, expected',
    [
        ('BS_BAZIS_APPS', '[]', set()),
        (
            'BS_BAZIS_APPS',
            '["bazis.contrib.cfgtest_unused"]',
            {'bazis.contrib.cfgtest_unused.conf'},
        ),
        (
            'BS_BAZIS_CONFIG_APPS',
            '["bazis.contrib.cfgtest_used", "bazis.contrib.cfgtest_library"]',
            {'bazis.contrib.cfgtest_used.conf', 'bazis.contrib.cfgtest_library.conf'},
        ),
    ],
)
def test_conf_of_listed_contrib_packages(fake_contrib, monkeypatch, variable, value, expected):
    monkeypatch.setenv(variable, value)
    assert contrib_conf_modules() == expected


@pytest.mark.parametrize(
    'env, warned',
    [
        ({}, False),
        ({'BS_BAZIS_APPS': '["bazis.contrib.users"]'}, False),
        ({'BS_BAZIS_APPS': '[]'}, True),
        ({'BS_BAZIS_CONFIG_APPS': '[]'}, True),
        ({'BS_BAZIS_CONFIG_APPS': '[]', 'BS_BAZIS_APPS': '["bazis.contrib.users"]'}, True),
    ],
)
def test_empty_bazis_apps_warning(monkeypatch, env, warned):
    for name in ('BS_BAZIS_APPS', 'BS_BAZIS_CONFIG_APPS'):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert [it.id for it in checks.check_bazis_apps(None)] == (['bazis.W002'] if warned else [])


def test_sample_starts_with_all_installed_contrib_packages():
    # the settings of every Bazis package installed in the environment are loaded, so the
    # sample must start without BS_BAZIS_APPS whichever packages are installed
    root = Path(__file__).resolve().parent.parent
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in ('BS_BAZIS_APPS', 'BS_BAZIS_CONFIG_APPS')
    }
    env['DJANGO_SETTINGS_MODULE'] = 'sample.settings'
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(root), env.get('PYTHONPATH')]))
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import django; django.setup(); '
            'from django.contrib.auth import get_user_model; print(get_user_model()._meta.label)',
        ],
        cwd=root / 'sample',
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == 'auth.User'
