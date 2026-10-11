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
parallel requests race for it; the other integrity errors stay 500. A request PostgreSQL
aborts for a parallel one (a deadlock, a serialization failure) is 409 `ERR_CONFLICT` with
`meta.retry`. `lock_on_write` locks the parent before every write of an item.
"""

import threading

from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError, connection, connections
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from fastapi.testclient import TestClient

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Card, Memo, Reader, Step
from catalog.routes import MemoRouteSet
from entity.models import Country
from psycopg.errors import DeadlockDetected, QueryCanceled, SerializationFailure

from bazis.core.models_abstract import JsonApiMixin


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


def subscribe(app, memo, email):
    """A guest subscribes to the memo by the action, which locks the memo first."""
    return TestClient(app, raise_server_exceptions=False).post(
        f'/api/v1/catalog/memo/{memo.pk}/subscribe/', json={'email': email}
    )


def add_reader(app, memo, email):
    """A reader created by the CRUD route."""
    return TestClient(app, raise_server_exceptions=False).post(
        '/api/v1/catalog/reader/',
        headers={'Content-Type': 'application/vnd.api+json'},
        json={
            'data': {
                'type': 'catalog.reader',
                'attributes': {'email': email},
                'relationships': {'memo': {'data': {'type': 'catalog.memo', 'id': str(memo.pk)}}},
            }
        },
    )


@pytest.mark.django_db(transaction=True)
def test_action_and_create_of_the_same_item(sample_app):
    """
    An action that locks the parent and then creates a child races a create of the same
    child (a unique e-mail): the model declares `lock_on_write`, so the create locks the
    parent before its insert too, in the same order. One is created, the others are 409
    (the unique constraint), never a deadlock (500, or 409 with `meta.retry`).
    """
    for round_ in range(3):
        memo = Memo.objects.create(title=f'Plan {round_}')
        calls = [lambda memo=memo: subscribe(sample_app, memo, 'a@example.com')] * 4 + [
            lambda memo=memo: add_reader(sample_app, memo, 'a@example.com')
        ] * 4
        responses = parallel_calls(calls)
        statuses = [r.status_code for r in responses]
        assert sorted(s for s in statuses if s not in (200, 201)) == [409] * 7, [
            (r.status_code, r.content) for r in responses
        ]
        assert not [r for r in responses if (r.json().get('errors') or [{}])[0].get('meta')]
        assert Reader.objects.filter(memo=memo).count() == 1


@pytest.mark.django_db(transaction=True)
def test_action_and_create_under_the_limit(sample_app):
    """
    The limit counted in validate_item holds when the action and the create race: of 8
    readers with their own e-mails 3 are added, the others are 422.
    """
    memo = Memo.objects.create(title='Plan')
    calls = [lambda i=i: subscribe(sample_app, memo, f'a{i}@example.com') for i in range(4)] + [
        lambda i=i: add_reader(sample_app, memo, f'c{i}@example.com') for i in range(4)
    ]
    statuses = [r.status_code for r in parallel_calls(calls)]
    assert sorted(s for s in statuses if s not in (200, 201)) == [422] * 5, statuses
    assert Reader.objects.filter(memo=memo).count() == Reader.MAX_PER_MEMO


@pytest.mark.django_db(transaction=True)
def test_deadlock_is_a_conflict_to_retry(sample_app, monkeypatch):
    """
    Without `lock_on_write` (the parent locked only in validate_item, after the insert) the
    action and the create deadlock: PostgreSQL aborts one of them, which answers 409
    `ERR_CONFLICT` with `meta.retry`; the other one is done. The two are put in the order of
    the deadlock: the create inserts, the action locks the memo, the create locks the memo,
    the action inserts.
    """
    inserted, locked = threading.Event(), threading.Event()

    def save(self, *args, **kwargs):
        if isinstance(JsonApiMixin.CTX_ROUTE.get(), MemoRouteSet):
            # the action holds the memo: the create has its row
            locked.set()
            inserted.wait(10)
        JsonApiMixin.save(self, *args, **kwargs)

    def validate_item(self, changes):
        if changes.source == 'create':
            inserted.set()
            locked.wait(10)
        Memo.objects.select_for_update().get(pk=self.memo_id)

    monkeypatch.setattr(Reader, 'lock_on_write', ())
    monkeypatch.setattr(Reader, 'save', save)
    monkeypatch.setattr(Reader, 'validate_item', validate_item)
    memo = Memo.objects.create(title='Plan')

    responses = parallel_calls(
        [
            lambda: add_reader(sample_app, memo, 'a@example.com'),
            lambda: subscribe(sample_app, memo, 'a@example.com'),
        ]
    )

    assert sorted(r.status_code for r in responses)[-1] == 409, [r.content for r in responses]
    assert sorted(r.status_code for r in responses)[0] in (200, 201)
    (error,) = next(r for r in responses if r.status_code == 409).json()['errors']
    assert (error['code'], error['title'], error['meta']) == (
        'ERR_CONFLICT',
        'Conflict',
        {'retry': True},
    )
    assert error['detail'] == 'The request conflicted with a parallel one: retry it'
    assert Reader.objects.filter(memo=memo).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'cause, sqlstate', [(DeadlockDetected, '40P01'), (SerializationFailure, '40001')]
)
def test_aborted_for_a_parallel_request(sample_app, monkeypatch, cause, sqlstate):
    """A deadlock and a serialization failure are 409 to retry; DEBUG adds the SQLSTATE."""

    def save(self, *args, **kwargs):
        raise OperationalError('aborted') from cause('aborted')

    monkeypatch.setattr(Country, 'save', save)

    response = create(sample_app, 'Norway')
    assert response.status_code == 409, response.content
    (error,) = response.json()['errors']
    assert (error['code'], error['meta']) == ('ERR_CONFLICT', {'retry': True})
    with override_settings(DEBUG=True):
        (error,) = create(sample_app, 'Norway').json()['errors']
    assert error['meta'] == {'retry': True, 'sqlstate': sqlstate}
    assert not Country.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_other_operational_errors_stay_500(sample_app, monkeypatch):
    """A cancelled query (a statement timeout) is not a conflict: 500."""

    def save(self, *args, **kwargs):
        raise OperationalError('canceled') from QueryCanceled('canceled')

    monkeypatch.setattr(Country, 'save', save)
    client = TestClient(sample_app, raise_server_exceptions=False)
    response = client.post(
        URL,
        headers={'Content-Type': 'application/vnd.api+json'},
        json={'data': {'type': 'entity.country', 'attributes': {'name': 'Norway'}}},
    )
    assert response.status_code == 500, response.content


def locks_and_inserts(queries) -> list[str]:
    """The locks and the inserts of the captured queries, in their order."""
    found = []
    for query in queries:
        sql = query['sql']
        if 'FOR NO KEY UPDATE' in sql:
            found.append(f'lock {sql.split(" FROM ")[1].split()[0].strip(chr(34))}')
        elif sql.startswith('INSERT INTO '):
            found.append(f'insert {sql.split()[2].strip(chr(34))}')
        elif sql.startswith('UPDATE '):
            found.append(f'update {sql.split()[1].strip(chr(34))}')
    return found


@pytest.mark.django_db(transaction=True)
def test_lock_on_write_locks_before_the_write():
    """
    Every save of a model that declares `lock_on_write` (here a script, outside the API)
    locks the row of the foreign key by its current value before it writes: the new
    parent when the item moves.
    """
    memo, other = Memo.objects.create(title='Plan'), Memo.objects.create(title='Other')
    with CaptureQueriesContext(connection) as queries:
        reader = Reader.objects.create(memo=memo, email='a@example.com')
    assert locks_and_inserts(queries) == ['lock catalog_memo', 'insert catalog_reader']
    lock = next(q['sql'] for q in queries if 'FOR NO KEY UPDATE' in q['sql'])
    assert f'= {memo.pk}' in lock

    reader.memo = other
    with CaptureQueriesContext(connection) as queries:
        reader.save()
    assert locks_and_inserts(queries)[:2] == ['lock catalog_memo', 'update catalog_reader']
    lock = next(q['sql'] for q in queries if 'FOR NO KEY UPDATE' in q['sql'])
    assert f'= {other.pk}' in lock


@pytest.mark.django_db(transaction=True)
def test_lock_on_write_without_validate_item(monkeypatch):
    """
    A model without validate_item that declares `lock_on_write` locks too; an empty
    foreign key locks nothing; a name that is not a foreign key is an error of the model.
    """
    memo = Memo.objects.create(title='Plan')
    monkeypatch.setattr(Card, 'lock_on_write', ('memo',))
    with CaptureQueriesContext(connection) as queries:
        Card.objects.create(name='With a memo', memo=memo)
    assert locks_and_inserts(queries) == ['lock catalog_memo', 'insert catalog_card']
    with CaptureQueriesContext(connection) as queries:
        Card.objects.create(name='Alone')
    assert locks_and_inserts(queries) == ['insert catalog_card']

    monkeypatch.setattr(Card, 'lock_on_write', ('name',))
    with pytest.raises(ImproperlyConfigured, match='name is not a foreign key'):
        Card.objects.create(name='Typo')
    assert not Card.objects.filter(name='Typo').exists()


def parallel_calls(funcs):
    """The results of the calls of `funcs` started at once in threads, in their order."""
    barrier = threading.Barrier(len(funcs))
    results = [None] * len(funcs)

    def worker(index, func):
        try:
            barrier.wait()
            results[index] = func()
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=item) for item in enumerate(funcs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


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
