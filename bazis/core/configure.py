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
Bazis framework core configuration module.

Tags: RAG, INTERNAL
"""

# ruff: noqa: N806

# Monkey patching moved here to avoid circular import issues.
# Placing in bazis/__init__.py causes infinite loop in top-level module linking.

import logging
import os
import sys
from copy import deepcopy
from importlib import import_module
from typing import Any, cast

from django.db import connections
from django.utils.translation import gettext_lazy as _

from pydantic import create_model

from dotenv import load_dotenv

import bazis
import bazis.core.utils.fastapi_monkey_patch
from bazis.core import constance_conf
from bazis.core.utils.imp import get_modules_from_pkg
from bazis.core.utils.locale import discover_locale_paths
from bazis.core.utils.logging_level import force_global_logging_level
from bazis.core.utils.schemas import BazisSettings


try:
    import bazis.contrib
except ImportError:
    pass

logger = logging.getLogger()

# Auto-detect project structure from DJANGO_SETTINGS_MODULE
PROJECT_MODULE = None
SETTINGS_MODULE = None
BASE_DIR = None
if settings_module_path := os.getenv('DJANGO_SETTINGS_MODULE'):
    SETTINGS_MODULE = import_module(settings_module_path)
    if project_module_path := '.'.join(settings_module_path.split('.')[:-1]):
        PROJECT_MODULE = import_module('.'.join(settings_module_path.split('.')[:-1]))
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(PROJECT_MODULE.__file__)))
    else:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(SETTINGS_MODULE.__file__)))

# Load environment files with priority preservation
env_files = BazisSettings.model_config['env_file']
if isinstance(env_files, str):
    env_files = [env_files]

# Preserve system environment variables (highest priority)
sys_envs = deepcopy(os.environ)

# Load .env files in order
for env_file in env_files:
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file, override=True)

# Restore system env vars to ensure they override .env files
for k, v in sys_envs.items():
    if v is not None:
        os.environ[k] = v

# Configure logging level from BS_LOG_LEVEL environment variable
log_level = logging.INFO
if os.environ.get('BS_LOG_LEVEL') is not None:
    log_level_name = os.environ['BS_LOG_LEVEL'].upper()
    if log_level_name in logging._nameToLevel:
        log_level = logging._nameToLevel[log_level_name]
    else:
        logger.warning(f'Invalid log level: {log_level_name}. Using default level: WARNING.')

force_global_logging_level(log_level)
logging.basicConfig(
    level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
)

# Set BASE_DIR and expand __BASE_DIR__ placeholders in environment variables
os.environ.setdefault('BS_BASE_DIR', BASE_DIR)
for key, value in os.environ.items():
    if key.startswith('BS_') and '__BASE_DIR__' in value:
        os.environ[key] = value.replace('__BASE_DIR__', BASE_DIR)

# Core Django apps required by Bazis framework
DEFAULT_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'bazis.core',
    # sequences app is necessary for UniqNumberMixin
    'sequences.apps.SequencesConfig',
    'rangefilter',
    'admin_auto_filters',
    'pgtrigger',
    # Constance: dynamic settings via admin panel and database
    'constance',
    'constance.backends.database',
]

# Core Django middleware required by Bazis framework
DEFAULT_MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


def conf_modules():
    """
    Discovers and yields all configuration modules from Bazis framework and project.

    Search order (reverse priority):
    1. bazis.core.conf
    2. Bazis contrib apps (from BS_BAZIS_CONFIG_APPS or BS_BAZIS_APPS)
    3. Project-level conf modules

    Yields:
        Configuration modules containing Settings classes

    RAG keywords: config discovery, settings modules, conf modules,
                  configuration discovery, settings assembly
    """
    # Core Bazis configuration
    for conf in get_modules_from_pkg(import_module('bazis.core'), 'conf', first_level_only=True):
        yield conf

    # Bazis contrib apps configuration
    BAZIS_CONFIG_APPS = os.environ.get('BS_BAZIS_CONFIG_APPS') or os.environ.get('BS_BAZIS_APPS')
    if BAZIS_CONFIG_APPS:
        BAZIS_CONFIG_APPS = reversed(eval(BAZIS_CONFIG_APPS))

        for bazis_app_name in BAZIS_CONFIG_APPS:
            for conf in get_modules_from_pkg(
                import_module(bazis_app_name), 'conf', first_level_only=True
            ):
                yield conf
    elif hasattr(bazis, 'contrib'):
        for conf in get_modules_from_pkg(bazis.contrib, 'conf'):
            yield conf

    # Project configuration (highest priority)
    if PROJECT_MODULE:
        for conf in get_modules_from_pkg(PROJECT_MODULE, 'conf'):
            yield conf


# Dynamically create unified Settings class from all discovered conf modules
# Uses Pydantic's create_model to merge Settings classes via multiple inheritance
Settings = cast(
    Any,
    create_model(
        'Settings',
        __base__=tuple(conf.Settings for conf in conf_modules() if hasattr(conf, 'Settings')),
    ),
)

# Instantiate local settings object from merged Settings class
_settings = Settings()

# Constance configuration for dynamic settings editable via admin panel
CONSTANCE_CONFIG = {
    # TODO: Temporary setting, should be configurable per installation
    'BAZIS_TIME_ZONE': (
        'Europe/Moscow',
        _('System time zone for generating agent report'),
        'timezone_select',
    )
}

if SETTINGS_MODULE:
    try:
        from django import conf
        from django.conf import LazySettings
    except ImportError as e:
        logger.error(f'Import error: {e}')
    else:
        # Build CONSTANCE_CONFIG from Settings fields marked as dynamic
        # Fields with json_schema_extra={'dynamic': True} become admin-editable
        for field_name, field_info in Settings.model_fields.items():
            if field_info.json_schema_extra and field_info.json_schema_extra.get('dynamic'):
                CONSTANCE_CONFIG[field_name] = (
                    getattr(_settings, field_name),
                    field_info.title,
                    field_info.annotation,
                )

        # Merge Bazis settings into Django SETTINGS_MODULE
        # Strategy: update existing collections, set missing values
        for sett_key, sett_value in _settings.model_dump().items():
            if sett_key not in SETTINGS_MODULE.__dict__:
                SETTINGS_MODULE.__dict__[sett_key] = sett_value
            else:
                existing_value = SETTINGS_MODULE.__dict__[sett_key]

                # Merge collections intelligently
                if isinstance(existing_value, dict) and isinstance(sett_value, dict):
                    existing_value.update(sett_value)
                elif isinstance(existing_value, list) and isinstance(sett_value, list):
                    existing_value.extend(sett_value)
                elif isinstance(existing_value, set) and isinstance(sett_value, set):
                    existing_value.update(sett_value)
                elif isinstance(existing_value, tuple) and isinstance(sett_value, tuple):
                    SETTINGS_MODULE.__dict__[sett_key] = existing_value + sett_value

        SETTINGS_MODULE.__dict__['CONSTANCE_CONFIG'] = CONSTANCE_CONFIG
        SETTINGS_MODULE.__dict__.setdefault(
            'CONSTANCE_BACKEND', 'constance.backends.database.DatabaseBackend'
        )

        # Ensure all required apps are in INSTALLED_APPS
        INSTALLED_APPS = SETTINGS_MODULE.__dict__.setdefault('INSTALLED_APPS', [])
        for _i, default_app in enumerate(DEFAULT_APPS):
            if default_app not in INSTALLED_APPS:
                INSTALLED_APPS.append(default_app)

        # Ensure all required middleware in MIDDLEWARE
        MIDDLEWARE_NEW = SETTINGS_MODULE.__dict__.get('MIDDLEWARE', [])
        MIDDLEWARE = SETTINGS_MODULE.__dict__['MIDDLEWARE'] = []
        for default_middleware in DEFAULT_MIDDLEWARE:
            if default_middleware not in MIDDLEWARE:
                MIDDLEWARE.append(default_middleware)
        for midl in MIDDLEWARE_NEW:
            if midl not in MIDDLEWARE:
                MIDDLEWARE.append(midl)

        # Auto-discover locale paths for i18n
        SETTINGS_MODULE.__dict__['LOCALE_PATHS'] = discover_locale_paths(BASE_DIR)

        django_settings = LazySettings()

        class DjangoSettingsWrapper:
            """
            Three-tier settings accessor: Constance DB → settings.py → .env

            Provides dynamic settings through Constance (admin-editable) while
            maintaining backward compatibility with static Django settings.

            Database check prevents errors during tests when DB not initialized.

            RAG keywords: settings wrapper, constance, dynamic settings,
                          database settings, admin editable settings
            """

            def __getattribute__(self, name):
                """
                Retrieves setting value with priority: Constance DB > Django settings.
                Checks database availability before Constance lookup (for pytest).
                """
                if name in CONSTANCE_CONFIG:
                    try:
                        # Verify DB connection ready (important for tests)
                        for conn in connections.all(initialized_only=True)[:1]:
                            conn.cursor().execute('select 1')
                    except Exception as e:
                        logger.info(
                            f"""DjangoSettingsWrapper raise exception with not ready db connection {e}\n
                                       if you run test - do not worry about this message, otherwise - it is PROBLEM!
                                    """
                        )
                        return ''
                    return getattr(constance_conf.config, name)
                else:
                    return getattr(django_settings, name)

            def __setattr__(self, name, value):
                """
                Sets setting value in Constance DB if dynamic, else Django settings.
                """
                if name in CONSTANCE_CONFIG:
                    setattr(constance_conf.config, name, value)
                else:
                    setattr(django_settings, name, value)

            def __delattr__(self, name):
                try:
                    object.__delattr__(self, name)
                except AttributeError:
                    pass

            def __iter__(self):
                """
                Iterates all settings from both Constance and Django settings.
                """
                for key in CONSTANCE_CONFIG:
                    yield (key, getattr(constance_conf.config, key))
                for key in django_settings.__dict__.keys():
                    yield (key, getattr(django_settings, key))

        django_settings_wrapper = DjangoSettingsWrapper()

        class ConfWrapper:
            """
            Monkey patches django.conf module to inject DjangoSettingsWrapper.
            Replaces django.conf.settings with our custom wrapper.

            RAG keywords: django conf wrapper, monkey patch django, settings override
            """

            def __getattribute__(self, name):
                """
                Returns DjangoSettingsWrapper for 'settings' attribute.
                Delegates all other attributes to original django.conf module.
                """
                if name == 'settings':
                    return django_settings_wrapper
                return getattr(conf, name)

        # Replace django.conf module with wrapper
        sys.modules['django.conf'] = ConfWrapper()


class SettingsWrapper:
    """
    Unified settings accessor for Bazis framework.
    Prioritizes Constance dynamic settings over static settings.

    Used as global settings object throughout application.

    RAG keywords: settings accessor, bazis settings, settings wrapper
    """

    def __getattribute__(self, name):
        """
        Retrieves setting: Constance DB if dynamic, else static Settings.
        """
        if name in CONSTANCE_CONFIG:
            return getattr(constance_conf.config, name)
        else:
            return getattr(_settings, name)


# Global settings instance for application use
settings = SettingsWrapper()
