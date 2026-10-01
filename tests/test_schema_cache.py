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

import sys

from bazis.core.schemas import cache as cache_module
from bazis.core.schemas.builders import schema_create
from bazis.core.schemas.cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_ttl_cache_evicts_idle_entries(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(cache_module.time, 'monotonic', clock)
    evicted = []
    cache = TTLCache(10, on_evict=lambda key, value: evicted.append(key))

    cache['a'] = 1
    cache['b'] = 2

    clock.now += 8
    # access refreshes the entry
    assert cache.get('a') == 1

    clock.now += 8
    assert cache.get('a') == 1
    assert cache.get('b') is None
    assert evicted == ['b']

    # adding entries sweeps expired ones at most once per TTL
    clock.now += 11
    cache['c'] = 3
    assert list(cache._data) == ['c']
    assert evicted == ['b', 'a']


def test_ttl_cache_zero_ttl_never_evicts(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(cache_module.time, 'monotonic', clock)
    cache = TTLCache(lambda: 0)

    cache['a'] = 1
    clock.now += 10**9
    cache['b'] = 2
    assert cache.get('a') == 1
    assert list(cache._data) == ['a', 'b']


def test_evicted_schema_is_removed_from_module(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(cache_module.time, 'monotonic', clock)
    cache = TTLCache(10, on_evict=cache_module._schema_evicted)
    schema = schema_create('_TestSchemaCacheEviction', name=(str, ...))
    module = sys.modules[schema.__module__]
    cache['key'] = schema
    assert module._TestSchemaCacheEviction is schema

    clock.now += 11
    assert cache.get('key') is None
    assert not hasattr(module, '_TestSchemaCacheEviction')
