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

from types import ModuleType, SimpleNamespace

from django.conf import LazySettings, settings
from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone

import pytest

from bazis.core import configure


DYNAMIC_KEY = 'BAZIS_API_PAGINATION_PAGE_SIZE_MAX'


@pytest.fixture
def dynamic_config(monkeypatch):
    config = SimpleNamespace(**{DYNAMIC_KEY: 100})
    monkeypatch.setattr(configure.constance_conf, 'config', config)
    return config


def test_django_module_and_early_settings_references_are_preserved():
    import django.conf

    assert isinstance(django.conf, ModuleType)
    assert timezone.settings is settings


def test_static_overrides_are_shared_with_bazis():
    before = settings.TIME_ZONE
    with override_settings(TIME_ZONE='Europe/Warsaw'):
        assert settings.TIME_ZONE == configure.settings.TIME_ZONE == 'Europe/Warsaw'
    assert settings.TIME_ZONE == configure.settings.TIME_ZONE == before


def test_nested_override_restores_dynamic_value_without_persisting(dynamic_config):
    with override_settings(**{DYNAMIC_KEY: 45}):
        assert getattr(settings, DYNAMIC_KEY) == getattr(configure.settings, DYNAMIC_KEY) == 45
        with override_settings(TIME_ZONE='UTC'):
            assert getattr(configure.settings, DYNAMIC_KEY) == 45
            with override_settings(**{DYNAMIC_KEY: 30}):
                assert getattr(configure.settings, DYNAMIC_KEY) == 30
            assert getattr(configure.settings, DYNAMIC_KEY) == 45
    assert getattr(settings, DYNAMIC_KEY) == 100
    assert getattr(dynamic_config, DYNAMIC_KEY) == 100


def test_dynamic_reads_are_not_cached_and_writes_reach_constance(dynamic_config):
    assert getattr(settings, DYNAMIC_KEY) == 100
    setattr(dynamic_config, DYNAMIC_KEY, 80)
    assert getattr(configure.settings, DYNAMIC_KEY) == 80
    setattr(settings, DYNAMIC_KEY, 60)
    assert getattr(dynamic_config, DYNAMIC_KEY) == 60
    assert getattr(settings, DYNAMIC_KEY) == 60


def test_unrelated_lazy_settings_remain_independent(dynamic_config):
    other = LazySettings()
    other.configure(**{DYNAMIC_KEY: 5})
    assert getattr(other, DYNAMIC_KEY) == 5
    setattr(other, DYNAMIC_KEY, 6)
    assert getattr(other, DYNAMIC_KEY) == 6
    assert getattr(dynamic_config, DYNAMIC_KEY) == 100


def test_startup_reads_typed_default_then_switches_to_constance(monkeypatch, dynamic_config):
    with monkeypatch.context() as startup:
        startup.setattr(configure.apps, 'ready', False)
        assert getattr(settings, DYNAMIC_KEY) == 1000
    assert getattr(settings, DYNAMIC_KEY) == 100


def test_runtime_database_failure_is_not_hidden(monkeypatch):
    class UnavailableConfig:
        def __getattr__(self, name):
            raise OperationalError('database unavailable')

    monkeypatch.setattr(configure.constance_conf, 'config', UnavailableConfig())
    with pytest.raises(OperationalError, match='database unavailable'):
        getattr(settings, DYNAMIC_KEY)


@pytest.mark.django_db
def test_persisted_constance_value_and_override_are_separate():
    from constance import config

    setattr(config, DYNAMIC_KEY, 72)
    assert getattr(settings, DYNAMIC_KEY) == 72
    with override_settings(**{DYNAMIC_KEY: 42}):
        assert getattr(configure.settings, DYNAMIC_KEY) == 42
        assert getattr(config, DYNAMIC_KEY) == 72
    assert getattr(configure.settings, DYNAMIC_KEY) == 72


SENDER = 'DEFAULT_FROM_EMAIL'


def saved(key):
    from constance.models import Constance

    return Constance.objects.filter(key=key).exists()


@pytest.fixture
def sender_default(monkeypatch):
    """Sets the default of the sender, as a BS_DEFAULT_FROM_EMAIL of the process does."""
    from constance import settings as constance_settings

    def set_default(value):
        monkeypatch.setitem(
            constance_settings.CONFIG, SENDER, (value, *constance_settings.CONFIG[SENDER][1:])
        )

    return set_default


def test_default_sender_is_the_django_default():
    assert configure.Settings.model_fields[SENDER].default == 'webmaster@localhost'


@pytest.mark.django_db
def test_a_read_does_not_save_the_default(sender_default):
    """
    The reads (of Bazis, of constance: the admin, `manage.py constance get`) do not save
    the default: a later BS_* variable of the setting takes effect.
    """
    from constance import config

    sender_default('noreply@first.example')
    assert settings.DEFAULT_FROM_EMAIL == getattr(config, SENDER) == 'noreply@first.example'
    assert not saved(SENDER)

    sender_default('noreply@second.example')
    assert settings.DEFAULT_FROM_EMAIL == 'noreply@second.example'


@pytest.mark.django_db
def test_a_set_value_wins_over_the_default(sender_default):
    from constance import config

    # the value of the default is not saved: nothing to keep
    setattr(config, SENDER, configure.CONSTANCE_CONFIG[SENDER][0])
    assert not saved(SENDER)

    setattr(config, SENDER, 'office@example.com')
    assert saved(SENDER)
    sender_default('noreply@other.example')
    assert settings.DEFAULT_FROM_EMAIL == 'office@example.com'

    # once saved, the value of the default is saved too
    setattr(config, SENDER, 'noreply@other.example')
    sender_default('noreply@third.example')
    assert settings.DEFAULT_FROM_EMAIL == 'noreply@other.example'


@pytest.mark.django_db
def test_doctor_warns_of_an_empty_sender():
    from constance import config

    from bazis.core import introspect

    def warnings():
        messages = introspect.check_messages(databases=['default'])
        return [it for it in messages if it['id'] == 'bazis.W009']

    assert warnings() == []
    setattr(config, SENDER, '')
    (warning,) = warnings()
    assert 'DEFAULT_FROM_EMAIL' in warning['message']
    assert 'manage.py constance set DEFAULT_FROM_EMAIL' in warning['hint']
    # without the database the check does not run
    assert not [it for it in introspect.check_messages() if it['id'] == 'bazis.W009']


@pytest.mark.django_db
def test_a_read_of_a_setting_without_a_value_is_one_query():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        for _ in range(3):
            assert settings.DEFAULT_FROM_EMAIL == configure.CONSTANCE_CONFIG[SENDER][0]
    assert len(queries) == 3
    assert not saved(SENDER)


@pytest.mark.django_db
def test_the_absence_of_a_value_is_cached(monkeypatch):
    """With CONSTANCE_DATABASE_CACHE_BACKEND a setting without a value is not read again."""
    from django.core.cache import caches
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from constance import settings as constance_settings

    from bazis.core.constance_conf.backend import DatabaseBackend

    monkeypatch.setattr(constance_settings, 'DATABASE_CACHE_BACKEND', 'default')
    cache = caches['default']
    keys = ['autofilled', SENDER, f'bazis_unset:{SENDER}']
    cache.delete_many(keys)
    try:
        backend = DatabaseBackend()
        with CaptureQueriesContext(connection) as queries:
            assert backend.get(SENDER) is None
        assert len(queries) == 1
        with CaptureQueriesContext(connection) as queries:
            assert backend.get(SENDER) is None
        assert len(queries) == 0

        backend.set(SENDER, 'office@example.com')
        with CaptureQueriesContext(connection) as queries:
            assert backend.get(SENDER) == 'office@example.com'
        assert len(queries) == 0
    finally:
        cache.delete_many(keys)


@pytest.mark.django_db
def test_a_late_marker_of_absence_does_not_hide_a_value(monkeypatch):
    """
    A value set while a read misses it: the marker of absence the read adds after the set
    is dropped, and a cached value is read before a marker.
    """
    from django.core.cache import caches

    from constance import settings as constance_settings
    from constance.backends.database import DatabaseBackend as DatabaseBackendBase

    from bazis.core.constance_conf.backend import DatabaseBackend

    monkeypatch.setattr(constance_settings, 'DATABASE_CACHE_BACKEND', 'default')
    cache = caches['default']
    marker = f'bazis_unset:{SENDER}'
    keys = ['autofilled', SENDER, marker]
    cache.delete_many(keys)
    try:
        backend, other = DatabaseBackend(), DatabaseBackend()
        miss = DatabaseBackendBase.get

        def get_then_set(self, key):
            value = miss(self, key)
            # another process sets the value after this read missed it
            other.set(SENDER, 'office@example.com')
            return value

        monkeypatch.setattr(DatabaseBackendBase, 'get', get_then_set)
        assert backend.get(SENDER) is None
        monkeypatch.setattr(DatabaseBackendBase, 'get', miss)
        assert cache.get(marker) is None
        assert backend.get(SENDER) == 'office@example.com'

        # a marker left with a cached value: the value wins
        cache.set(marker, True)
        assert backend.get(SENDER) == 'office@example.com'
    finally:
        cache.delete_many(keys)
