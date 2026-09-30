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

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import mailers
from django.test import override_settings

import pytest

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
