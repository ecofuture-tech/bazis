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
Cache of the dynamically generated Pydantic schemas.

Bazis generates a schema per route, action and combination of requested inclusions, so
the number of schemas is large by design. Entries that are not used for
``BAZIS_SCHEMA_CACHE_TTL`` seconds are evicted (0 disables eviction) and generated again
on the next request. Schemas referenced elsewhere (e.g. by the registered routes) stay
alive regardless of the cache.

Tags: RAG, INTERNAL
"""

import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


__all__ = [
    'DEFAULT_SCHEMA_CACHE_TTL',
    'SCHEMAS_CACHE',
    'TTLCache',
    'get_schema_cache_ttl',
    'get_schema_from_cache',
    'set_schema_to_cache',
]

DEFAULT_SCHEMA_CACHE_TTL = 3600


def get_schema_cache_ttl() -> float:
    """
    Returns the idle lifetime of the cached schemas in seconds from the settings.
    """
    from django.conf import settings

    return getattr(settings, 'BAZIS_SCHEMA_CACHE_TTL', DEFAULT_SCHEMA_CACHE_TTL)


class TTLCache:
    """
    Thread-safe dictionary-like cache that evicts entries not accessed for the TTL.

    :param ttl: Idle lifetime in seconds, or a callable returning it; 0 disables eviction.
    :param on_evict: Optional callback called with the key and value of an evicted entry.
    """

    def __init__(
        self,
        ttl: float | Callable[[], float],
        on_evict: Callable[[str, Any], None] | None = None,
    ):
        self._ttl = ttl
        self._on_evict = on_evict
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()
        self._last_sweep = time.monotonic()

    @property
    def ttl(self) -> float:
        return self._ttl() if callable(self._ttl) else self._ttl

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            value, accessed = entry
            ttl = self.ttl
            now = time.monotonic()
            if ttl and now - accessed > ttl:
                self._evict(key)
                return default
            self._data[key] = (value, now)
            return value

    def __getitem__(self, key: str) -> Any:
        marker = object()
        value = self.get(key, marker)
        if value is marker:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic())
            self._sweep()

    def __contains__(self, key: str) -> bool:
        marker = object()
        return self.get(key, marker) is not marker

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        with self._lock:
            for key in list(self._data):
                self._evict(key)

    def _evict(self, key: str) -> None:
        value, _ = self._data.pop(key)
        if self._on_evict:
            self._on_evict(key, value)

    def _sweep(self) -> None:
        """
        Evicts expired entries. Runs at most once per TTL, so that adding entries stays cheap.
        """
        ttl = self.ttl
        now = time.monotonic()
        if not ttl or now - self._last_sweep < ttl:
            return
        self._last_sweep = now
        for key, (_, accessed) in list(self._data.items()):
            if now - accessed > ttl:
                self._evict(key)


def _schema_evicted(key: str, schema: type[BaseModel]) -> None:
    """
    Removes the evicted schema from the module it was registered in, so that it can be
    garbage collected once nothing else references it.
    """
    module = sys.modules.get(getattr(schema, '__module__', ''))
    name = getattr(schema, 'schema_name', None)
    if module is not None and name and getattr(module, name, None) is schema:
        delattr(module, name)


SCHEMAS_CACHE = TTLCache(get_schema_cache_ttl, on_evict=_schema_evicted)


def get_schema_from_cache(key: str) -> type[BaseModel] | None:
    return SCHEMAS_CACHE.get(key)


def set_schema_to_cache(key: str, schema: type[BaseModel]) -> None:
    SCHEMAS_CACHE[key] = schema
