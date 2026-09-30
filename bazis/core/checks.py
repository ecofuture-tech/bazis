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
from django.core.checks import Error, Tags, register


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
