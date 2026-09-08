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
