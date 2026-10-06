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

import ast
import json
import logging
import os
from copy import deepcopy
from importlib import import_module
from typing import Any, cast

from django.apps import apps
from django.conf import LazySettings, UserSettingsHolder
from django.utils.functional import empty
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


SECRET_KEY_MIN_LENGTH = 32
SECRET_KEY_MIN_UNIQUE_CHARACTERS = 5


def validate_security_settings(values: dict) -> None:
    """
    Validates the security-critical settings of the merged Django settings module.

    SECRET_KEY must be set in the project environment (BS_SECRET_KEY). A key generated
    per process breaks sessions, CSRF tokens and signed data as soon as more than one
    process (e.g. several gunicorn workers) is running, so it is only generated as a
    temporary fallback in DEBUG mode. Outside DEBUG an absent or weak key is an error.
    """
    from django.core.exceptions import ImproperlyConfigured

    secret_key = values.get('SECRET_KEY') or ''
    debug = bool(values.get('DEBUG'))

    problems = []
    if not secret_key:
        problems.append('SECRET_KEY is not set (define BS_SECRET_KEY in the project environment)')
    else:
        if len(secret_key) < SECRET_KEY_MIN_LENGTH:
            problems.append(f'SECRET_KEY must be at least {SECRET_KEY_MIN_LENGTH} characters long')
        if len(set(secret_key)) < SECRET_KEY_MIN_UNIQUE_CHARACTERS:
            problems.append(
                f'SECRET_KEY must contain at least {SECRET_KEY_MIN_UNIQUE_CHARACTERS} '
                'unique characters'
            )
        if secret_key.startswith('django-insecure-'):
            problems.append("SECRET_KEY must not be a 'django-insecure-' development key")

    if not problems:
        return
    if not debug:
        raise ImproperlyConfigured('Invalid security settings: ' + '; '.join(problems) + '.')

    for problem in problems:
        logger.warning('%s. This is only allowed with DEBUG enabled.', problem)
    if not secret_key:
        from bazis.core.conf import secret_key_generate

        values['SECRET_KEY'] = secret_key_generate()


def parse_list_env(value: str) -> list[str]:
    """
    Parses a list of module names from an environment variable.
    Accepts JSON (``["a", "b"]``) and Python literal (``['a', 'b']``) notation.
    Unlike ``eval``, never executes code.
    """
    try:
        result = json.loads(value)
    except ValueError:
        try:
            result = ast.literal_eval(value)
        except (ValueError, SyntaxError) as e:
            raise ValueError(f'Expected a list of module names, got: {value!r}') from e
    if not isinstance(result, list | tuple) or not all(isinstance(it, str) for it in result):
        raise ValueError(f'Expected a list of module names, got: {value!r}')
    return list(result)


def listed_bazis_apps() -> list[str] | None:
    """
    The Bazis packages to load the settings from, listed in BS_BAZIS_CONFIG_APPS or
    BS_BAZIS_APPS; None if neither is set (the settings of all installed packages are
    loaded). An empty list loads the settings of no package (see the check bazis.W002).
    """
    value = os.environ.get('BS_BAZIS_CONFIG_APPS') or os.environ.get('BS_BAZIS_APPS')
    return parse_list_env(value) if value else None


def conf_modules():
    """
    Discovers and yields all configuration modules from Bazis framework and project.

    Search order. The modules become the bases of one Settings class in this order and,
    as in any Python class, the first base that declares a field gives its default: the
    core wins over the packages and the packages over the project (an environment
    variable BS_<NAME> wins over every default):
    1. bazis.core.conf
    2. Bazis contrib apps: all installed ones, or those listed in BS_BAZIS_CONFIG_APPS or
       BS_BAZIS_APPS (an explicit override)
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
    BAZIS_CONFIG_APPS = listed_bazis_apps()
    if BAZIS_CONFIG_APPS is not None:
        for bazis_app_name in reversed(BAZIS_CONFIG_APPS):
            for conf in get_modules_from_pkg(
                import_module(bazis_app_name), 'conf', first_level_only=True
            ):
                yield conf
    elif hasattr(bazis, 'contrib'):
        for conf in get_modules_from_pkg(bazis.contrib, 'conf'):
            yield conf

    # Project configuration
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

# Deprecated Django email settings (Django 6.1) -> Bazis settings (see bazis.core.mail)
LEGACY_EMAIL_SETTINGS = {
    'EMAIL_BACKEND': 'BAZIS_EMAIL_BACKEND',
    'EMAIL_HOST': 'BAZIS_EMAIL_HOST',
    'EMAIL_PORT': 'BAZIS_EMAIL_PORT',
    'EMAIL_HOST_USER': 'BAZIS_EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD': 'BAZIS_EMAIL_HOST_PASSWORD',
    'EMAIL_USE_TLS': 'BAZIS_EMAIL_USE_TLS',
    'EMAIL_USE_SSL': 'BAZIS_EMAIL_USE_SSL',
}


DJANGO_SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
DYNAMIC_SMTP_BACKEND = 'bazis.core.mail.DynamicSMTPEmailBackend'


def apply_legacy_email_env() -> None:
    """
    Maps the environment variables of the renamed email settings (BS_EMAIL_HOST, ...)
    to the new names (BS_BAZIS_EMAIL_HOST, ...), unless the new ones are set.
    """
    for legacy_name, name in LEGACY_EMAIL_SETTINGS.items():
        legacy_env, env = f'BS_{legacy_name}', f'BS_{name}'
        if legacy_env in os.environ and env not in os.environ:
            logger.warning(
                '%s is deprecated, rename it to %s (Django 6.1 replaced EMAIL_* with MAILERS).',
                legacy_env,
                env,
            )
            os.environ[env] = os.environ[legacy_env]


def configure_mailers(values: dict) -> None:
    """
    Configures the default mailer (Django 6.1 MAILERS) with BAZIS_EMAIL_BACKEND.
    A project that still defines the deprecated EMAIL_* settings in its settings module
    keeps the legacy configuration: Django does not allow combining it with MAILERS.
    """
    if 'MAILERS' in values:
        return
    if legacy := sorted(name for name in LEGACY_EMAIL_SETTINGS if name in values):
        logger.warning(
            'Deprecated email settings %s are defined in the settings module, so MAILERS '
            'is not configured. Use the BAZIS_EMAIL_* settings instead.',
            ', '.join(legacy),
        )
        return
    backend = values['BAZIS_EMAIL_BACKEND']
    if backend == DJANGO_SMTP_BACKEND:
        # with MAILERS the stock SMTP backend takes its parameters from OPTIONS only,
        # the dynamic one reads them from the BAZIS_EMAIL_* settings
        backend = DYNAMIC_SMTP_BACKEND
    values['MAILERS'] = {'default': {'BACKEND': backend}}


apply_legacy_email_env()

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
        from django.conf import settings as django_settings
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

        # A wildcard set explicitly in the project settings module is kept (see below)
        _project_allowed_hosts = SETTINGS_MODULE.__dict__.get('ALLOWED_HOSTS')
        _project_wildcard = isinstance(_project_allowed_hosts, list | tuple) and (
            '*' in _project_allowed_hosts
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
                    existing_value.extend(it for it in sett_value if it not in existing_value)
                elif isinstance(existing_value, set) and isinstance(sett_value, set):
                    existing_value.update(sett_value)
                elif isinstance(existing_value, tuple) and isinstance(sett_value, tuple):
                    SETTINGS_MODULE.__dict__[sett_key] = existing_value + sett_value

        # The default Bazis wildcard merged with concrete hosts would disable host validation,
        # so it is dropped unless the project settings module set it explicitly.
        ALLOWED_HOSTS = SETTINGS_MODULE.__dict__.get('ALLOWED_HOSTS')
        if (
            isinstance(ALLOWED_HOSTS, list)
            and len(ALLOWED_HOSTS) > 1
            and '*' in ALLOWED_HOSTS
            and not _project_wildcard
        ):
            ALLOWED_HOSTS.remove('*')

        validate_security_settings(SETTINGS_MODULE.__dict__)
        configure_mailers(SETTINGS_MODULE.__dict__)

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

        if not getattr(LazySettings, '_bazis_dynamic_patch_applied', False):
            _original_getattr = LazySettings.__getattr__
            _original_setattr = LazySettings.__setattr__

            def _dynamic_setting_value(wrapped, name):
                holder = wrapped
                while isinstance(holder, UserSettingsHolder):
                    if name in holder._deleted:
                        raise AttributeError(name)
                    if name in holder.__dict__:
                        return getattr(holder, name)
                    holder = holder.default_settings

                # Models and routes may read defaults while Django is loading apps.
                # Do not cache them: Constance becomes authoritative after startup.
                if not apps.ready:
                    return getattr(wrapped, name)
                return getattr(constance_conf.config, name)

            def _bazis_getattr(self, name):
                if self is django_settings and name in CONSTANCE_CONFIG:
                    if (_wrapped := self._wrapped) is empty:
                        self._setup(name)
                        _wrapped = self._wrapped
                    return _dynamic_setting_value(_wrapped, name)
                return _original_getattr(self, name)

            def _bazis_setattr(self, name, value):
                if self is django_settings and name != '_wrapped' and name in CONSTANCE_CONFIG:
                    setattr(constance_conf.config, name, value)
                    self.__dict__.pop(name, None)
                    return
                return _original_setattr(self, name, value)

            LazySettings.__getattr__ = _bazis_getattr
            LazySettings.__setattr__ = _bazis_setattr
            LazySettings._bazis_dynamic_patch_applied = True
            for name in CONSTANCE_CONFIG:
                django_settings.__dict__.pop(name, None)


class SettingsWrapper:
    """
    Unified settings accessor for Bazis framework.
    Prioritizes Constance dynamic settings over static settings.

    Used as global settings object throughout application.

    RAG keywords: settings accessor, bazis settings, settings wrapper
    """

    def __getattribute__(self, name):
        """
        Retrieves setting from Django settings, but preserves Constance priority
        for dynamic keys unless Django temporarily overrides them in tests.
        """
        if name.startswith('__'):
            return object.__getattribute__(self, name)

        try:
            from django.conf import settings as django_settings
        except ImportError:
            django_settings = None

        if SETTINGS_MODULE and django_settings is not None:
            return getattr(django_settings, name)
        return getattr(_settings, name)


# Global settings instance for application use
settings = SettingsWrapper()
