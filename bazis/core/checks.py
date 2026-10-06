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
Django system checks of the Bazis environment requirements.

Tags: RAG, INTERNAL
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.caches)
def check_cache_backend(app_configs, **kwargs):
    """
    Bazis requires a Redis cache (django-redis): model items are cached and invalidated
    by key pattern, which other Django cache backends do not support.
    """
    from django.core.cache import caches

    backend = caches['default']
    if not hasattr(backend, 'delete_pattern'):
        return [
            Error(
                'The default cache backend does not support delete_pattern.',
                hint=(
                    'Bazis requires Redis: set BS_CACHES__DEFAULT__BACKEND='
                    'django_redis.cache.RedisCache and BS_CACHES__DEFAULT__LOCATION '
                    f'(current backend: {settings.CACHES["default"]["BACKEND"]}).'
                ),
                id='bazis.E001',
            )
        ]
    return []


@register(Tags.security, deploy=True)
def check_allowed_hosts(app_configs, **kwargs):
    """
    A wildcard in ALLOWED_HOSTS accepts any Host header (Django checks only that the list
    is not empty).
    """
    if '*' in settings.ALLOWED_HOSTS:
        return [
            Warning(
                "ALLOWED_HOSTS contains '*': any Host header is accepted.",
                hint='List the domains of the project in BS_ALLOWED_HOSTS.',
                id='bazis.W001',
            )
        ]
    return []


@register()
def check_bazis_apps(app_configs, **kwargs):
    """
    An empty BS_BAZIS_APPS (or BS_BAZIS_CONFIG_APPS) turns off the settings of all Bazis
    packages, also of the ones the project uses: their code then fails on missing settings.
    """
    from bazis.core.configure import listed_bazis_apps

    if listed_bazis_apps() == []:
        return [
            Warning(
                'BS_BAZIS_APPS (or BS_BAZIS_CONFIG_APPS) is an empty list: the settings of '
                'no Bazis package are loaded.',
                hint=(
                    'Unset it to load the settings of all installed Bazis packages, or list '
                    'the Bazis packages of the project in it.'
                ),
                id='bazis.W002',
            )
        ]
    return []
