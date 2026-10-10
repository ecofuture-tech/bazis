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
`set_item` returns the item the route holds under the same id, and takes it again, locked,
only when it was not taken locked (bazis-permit takes the item of an action before it runs).
"""

from types import SimpleNamespace

import pytest
from entity.models import Country
from entity.routes import CountryRouteSet


@pytest.mark.django_db
def test_set_item(monkeypatch):
    first, second = Country.objects.create(name='A'), Country.objects.create(name='B')
    lookups = []

    def lookup(self, item_id, with_lock=False):
        lookups.append((item_id, with_lock))
        qs = Country.objects.filter(pk=item_id)
        return qs.select_for_update() if with_lock else qs

    monkeypatch.setattr(CountryRouteSet, 'get_queryset_for_item', lookup)
    route = object.__new__(CountryRouteSet)
    route.inject = SimpleNamespace()

    item = route.set_item(str(first.pk))
    assert route.set_item(str(first.pk)) is item
    # another id is another item, not the one the route holds
    assert route.set_item(str(second.pk)).pk == second.pk
    assert lookups == [(str(first.pk), False), (str(second.pk), False)]

    lookups.clear()
    locked = route.set_item(str(second.pk), with_lock=True)
    assert route.item_locked
    assert route.set_item(str(second.pk), with_lock=True) is locked
    assert route.set_item(str(second.pk)) is locked
    assert route.set_item(str(second.pk), is_force=True) is not locked
    assert lookups == [(str(second.pk), True), (str(second.pk), False)]
