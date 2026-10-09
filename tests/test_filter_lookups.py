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

"""Lookup suffixes of the fields that the sample models do not have (geometry, ranges)."""

from django.contrib.gis.db.models import PointField
from django.contrib.postgres.fields import DateRangeField
from django.db.models import Q

import pytest
from entity.models import ParentEntity

from bazis.core.utils.query_complex import QueryToOrm


def _native(field, name: str, key: str, value: str) -> Q:
    field.set_attributes_from_name(name)
    params = key.split('__')[1:]
    return QueryToOrm('', ParentEntity)._filters_apply_native(params, value, field)


@pytest.mark.parametrize(
    'field, key, value, lookup',
    [
        (PointField(), 'point__in_bbox', '160.6,-55.95,-170,-25.89', 'point__contained'),
        (DateRangeField(), 'period__overlap', '2024-01-01,2024-02-01', 'period__overlap'),
        (DateRangeField(), 'period__fully_lt', '2024-01-01,2024-02-01', 'period__fully_lt'),
    ],
)
def test_supported_lookups(field, key, value, lookup):
    assert _native(field, key.split('__')[0], key, value).children[0][0] == lookup


@pytest.mark.parametrize('field', [PointField(), DateRangeField()])
def test_isnull(field):
    assert _native(field, 'f', 'f__isnull', 'true') == Q(f__isnull=True)
    assert _native(field, 'f', 'f__isnull', 'false') == Q(f__isnull=False)


@pytest.mark.parametrize(
    'field, key, value, message',
    [
        # was a match of the point within 10 m
        (PointField(), 'point__distance', '49.124,55.7648', "lookup 'distance' is not supported"),
        # were ignored (no condition at all)
        (DateRangeField(), 'period', '2024-01-01,2024-02-01', "'period' requires a lookup"),
        (DateRangeField(), 'period__foo', '2024-01-01,2024-02-01', "'foo' is not supported"),
        # a transform, not a comparison with a range
        (DateRangeField(), 'period__isempty', 'true', "'isempty' is not supported"),
    ],
)
def test_unsupported_lookups(field, key, value, message):
    with pytest.raises(ValueError, match=message):
        _native(field, key.split('__')[0], key, value)


def test_filters_aliases():
    aliases = {'title': 'name', 'kids': 'child_entities'}

    assert QueryToOrm('title=x', ParentEntity, aliases).q == Q(name='x')
    assert QueryToOrm('kids__exists=true', ParentEntity, aliases).q
    with pytest.raises(ValueError, match="Unknown filter field 'title'"):
        QueryToOrm('title=x', ParentEntity)
