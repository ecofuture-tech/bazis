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
A write refused by a unique (or exclusion) constraint is 409 `ERR_CONFLICT`, also when two
parallel requests race for it; the other integrity errors stay 500.
"""

import threading

from django.db import connections
from django.test import override_settings

from fastapi.testclient import TestClient

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Memo, Step
from entity.models import Country


URL = '/api/v1/entity/country/'


def create(app, name):
    return get_api_client(app).post(
        URL, json_data={'data': {'type': 'entity.country', 'bs:action': 'add', 'attributes': {'name': name}}}
    )


@pytest.mark.django_db(transaction=True)
def test_unique_violation(sample_app):
    assert create(sample_app, 'Norway').status_code == 201
    response = create(sample_app, 'Norway')
    assert response.status_code == 409, response.content
    (error,) = response.json()['errors']
    assert (error['status'], error['code']) == (409, 'ERR_CONFLICT')
    assert error['detail'] == 'The change conflicts with the current data'
    assert 'meta' not in error
    with override_settings(DEBUG=True):
        (error,) = create(sample_app, 'Norway').json()['errors']
    # the constraint, only with DEBUG
    assert error['meta'] == {'constraint': 'entity_country_name_key'}
    assert Country.objects.filter(name='Norway').count() == 1


@pytest.mark.django_db(transaction=True)
def test_other_integrity_errors_stay_500(sample_app):
    """
    A foreign key to a missing object (checked at the commit) is not a conflict: 500, as any
    integrity error but a unique or an exclusion one (keep such rules in validate_item).
    """
    client = TestClient(sample_app, raise_server_exceptions=False)
    response = client.post(
        '/api/v1/entity/extended_entity/',
        headers={'Content-Type': 'application/vnd.api+json'},
        json={
            'data': {
                'type': 'entity.extended_entity',
                'bs:action': 'add',
                'attributes': {
                    'extended_name': 'Name',
                    'extended_description': 'Description',
                    'extended_is_active': False,
                    'extended_price': '25.19',
                    'extended_dt_approved': '2024-01-13T16:54:12Z',
                },
                'relationships': {
                    'parent_entity': {
                        'data': {
                            'id': '9b657232-4178-4d7f-8b0c-e8ab16f2b309',
                            'type': 'entity.parent_entity',
                        },
                    },
                },
            },
        },
    )
    assert response.status_code == 500, response.content


@pytest.mark.django_db(transaction=True)
def test_parallel_requests(sample_app):
    """
    Parallel creates of the same unique value: one is created, the others are 409, none 500.
    """
    results = parallel(4, lambda: create(sample_app, 'Iceland').status_code)
    assert sorted(results) == [201, 409, 409, 409]
    assert Country.objects.filter(name='Iceland').count() == 1


@pytest.mark.django_db(transaction=True)
def test_no_more_than_n_under_concurrency(sample_app):
    """
    The recipe of the guide (sample `catalog.Step`): the parent locked in `save` and
    `validate_item`, the number taken under the lock, a unique constraint as the barrier:
    of 6 parallel creates 3 pass, numbered 1 to 3, the others are 422.
    """
    memo = Memo.objects.create(title='Plan')

    def add_step():
        return get_api_client(sample_app).post(
            '/api/v1/catalog/step/',
            json_data={
                'data': {
                    'type': 'catalog.step',
                    'relationships': {'memo': {'data': {'type': 'catalog.memo', 'id': str(memo.pk)}}},
                }
            },
        ).status_code

    assert sorted(parallel(6, add_step)) == [201] * 3 + [422] * 3
    assert sorted(Step.objects.filter(memo=memo).values_list('number', flat=True)) == [1, 2, 3]


def parallel(count, func):
    """The results of `count` calls of `func` started at once in threads."""
    barrier = threading.Barrier(count)
    results = []

    def worker():
        try:
            barrier.wait()
            results.append(func())
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results
