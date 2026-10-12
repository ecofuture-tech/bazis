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
import time
from contextlib import contextmanager
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError, connection, models, transaction
from django.db.backends.signals import connection_created
from django.db.models import F
from django.db.models.functions import Lower
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from fastapi.testclient import TestClient

import pytest
from bazis_test_utils.utils import get_api_client, parallel
from catalog.models import Card, Memo, Reader, Step
from catalog.routes import MemoRouteSet, ReaderRouteSet, StepRouteSet
from entity.models import Country
from psycopg.errors import DeadlockDetected, QueryCanceled, SerializationFailure

from bazis.core.models_abstract import JsonApiMixin
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas.enums import CrudApiAction, RouteKind
from bazis.core.utils.orm import unique_constraint_error


URL = '/api/v1/entity/country/'


def create(app, name):
    return get_api_client(app).post(
        URL, json_data={'data': {'type': 'entity.country', 'bs:action': 'add', 'attributes': {'name': name}}}
    )


@pytest.mark.django_db(transaction=True)
def test_unique_violation(sample_app):
    """
    A unique field of the model of the route (`unique=True`): the error points to it, with
    the message of Django.
    """
    assert create(sample_app, 'Norway').status_code == 201
    response = create(sample_app, 'Norway')
    assert response.status_code == 409, response.content
    (error,) = response.json()['errors']
    assert (error['status'], error['code']) == (409, 'ERR_CONFLICT')
    assert error['detail'] == 'Country with this Country Name already exists.'
    assert error['source'] == {'pointer': '/data/attributes/name'}
    assert 'meta' not in error
    with override_settings(DEBUG=True):
        (error,) = create(sample_app, 'Norway').json()['errors']
    # the constraint, only with DEBUG
    assert error['meta'] == {'constraint': 'entity_country_name_key'}
    assert Country.objects.filter(name='Norway').count() == 1


@pytest.mark.django_db(transaction=True)
def test_other_integrity_errors_stay_500(sample_app, monkeypatch):
    """
    A foreign key to a missing object that a hook writes (checked at the commit) is not a
    conflict: 500, as any integrity error but a unique or an exclusion one (keep such rules
    in validate_item). One the document links is 422 (`test_relation_missing.py`).
    """
    from entity.models import ParentEntity
    from entity.routes import ExtendedEntityRouteSet

    def hook_before_create(self, item):
        item.parent_entity_id = '9b657232-4178-4d7f-8b0c-e8ab16f2b309'

    monkeypatch.setattr(ExtendedEntityRouteSet, 'hook_before_create', hook_before_create)
    parent = ParentEntity.objects.create(name='Parent')
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
                        'data': {'id': str(parent.id), 'type': 'entity.parent_entity'},
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
    responses = parallel(4, lambda: create(sample_app, 'Iceland'))
    assert sorted(it.status_code for it in responses) == [201, 409, 409, 409]
    for response in responses:
        if response.status_code == 409:
            (error,) = response.json()['errors']
            assert error['source'] == {'pointer': '/data/attributes/name'}
    assert Country.objects.filter(name='Iceland').count() == 1


@pytest.mark.django_db(transaction=True)
def test_no_more_than_n_under_concurrency(sample_app):
    """
    The recipe of the guide (sample `catalog.Step`): the parent declared in
    `lock_on_write` and locked in `save` before the number, the count in `validate_item`,
    a unique constraint as the barrier: of 6 parallel creates 3 pass, numbered 1 to 3, the
    others are 422.
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
        responses = parallel(calls)
        statuses = [r.status_code for r in responses]
        assert sorted(s for s in statuses if s not in (200, 201)) == [409] * 7, [
            (r.status_code, r.content) for r in responses
        ]
        assert not [r for r in responses if (r.json().get('errors') or [{}])[0].get('meta')]
        assert Reader.objects.filter(memo=memo).count() == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_creates_point_to_the_constraint_fields(sample_app):
    """
    Parallel creates of a reader with the same e-mail in a memo (`UniqueConstraint` of
    `memo` and `email`): one is created, each other answers an error for each field of the
    constraint, at the relation and at the attribute. The action that creates a reader on
    the route of the memo has no pointer: the constraint is not one of the model of its
    route.
    """
    memo = Memo.objects.create(title='Plan')
    responses = parallel(4, lambda: add_reader(sample_app, memo, 'a@example.com'))
    assert sorted(it.status_code for it in responses) == [201, 409, 409, 409], [
        (it.status_code, it.content) for it in responses
    ]
    for response in responses:
        if response.status_code == 409:
            errors = response.json()['errors']
            assert [it['source'] for it in errors] == [
                {'pointer': '/data/relationships/memo'},
                {'pointer': '/data/attributes/email'},
            ]
            assert {it['detail'] for it in errors} == {
                'Reader with this Memo and E-mail already exists.'
            }
    assert Reader.objects.filter(memo=memo).count() == 1

    response = subscribe(sample_app, memo, 'a@example.com')
    assert response.status_code == 409, response.content
    (error,) = response.json()['errors']
    assert 'source' not in error
    assert error['detail'] == 'The change conflicts with the current data'


def conflict_without_fields(response):
    """A 409 of a constraint that names no field: a single error without a pointer."""
    assert response.status_code == 409, response.content
    errors = response.json()['errors']
    assert len(errors) == 1, errors
    (error,) = errors
    assert error['code'] == 'ERR_CONFLICT' and 'source' not in error
    assert error['detail'] == 'The change conflicts with the current data'
    return error


@pytest.mark.django_db(transaction=True)
def test_field_filled_by_the_server_is_not_named(sample_app, monkeypatch):
    """
    A unique constraint with a field the user does not write (`Step.number`, numbered by
    the server, not in the schema of the create): no pointer and no name of a field.
    """
    save = Step.save

    def save_numbered_one(self, *args, **kwargs):
        # the number the server takes, here always the same one
        if self._state.adding:
            self.number = 1
        save(self, *args, **kwargs)

    monkeypatch.setattr(Step, 'save', save_numbered_one)
    memo = Memo.objects.create(title='Plan')
    Step.objects.create(memo=memo)
    response = get_api_client(sample_app).post(
        '/api/v1/catalog/step/',
        json_data={
            'data': {
                'type': 'catalog.step',
                'relationships': {'memo': {'data': {'type': 'catalog.memo', 'id': str(memo.pk)}}},
            }
        },
    )
    conflict_without_fields(response)
    assert 'Number' not in response.text
    assert Step.objects.filter(memo=memo).count() == 1


def test_field_not_in_the_schema_of_the_user_is_not_named():
    """
    `unique_conflict` names the fields only when all of them are in the schema of the write
    the user has: a field hidden from him (here the schema of a route without the e-mail)
    leaves the conflict without fields; the create and the update only, of the table of
    the model of the route.
    """
    reader_schema = ReaderRouteSet.schema_defaults[CrudApiAction.CREATE]
    hidden_schema = StepRouteSet.schema_defaults[CrudApiAction.CREATE]   # the memo alone

    def conflict(kind, schema, table='catalog_reader'):
        route = SimpleNamespace(
            route_ctx=SimpleNamespace(kind=kind),
            model=Reader,
            schemas={CrudApiAction.CREATE: schema, CrudApiAction.UPDATE: schema},
        )
        return JsonapiRouteBase.unique_conflict(route, table, 'catalog_reader_email_uniq')

    assert conflict(RouteKind.CREATE, reader_schema)[0] == ('memo', 'email')
    assert conflict(RouteKind.UPDATE, reader_schema)[0] == ('memo', 'email')
    assert conflict(RouteKind.CREATE, hidden_schema) is None
    assert conflict(RouteKind.RELATIONSHIP, reader_schema) is None
    assert conflict(RouteKind.OTHER, reader_schema) is None
    assert conflict(RouteKind.CREATE, reader_schema, table='catalog_step') is None


@pytest.mark.django_db(transaction=True)
def test_relationships_endpoint_names_no_field(sample_app):
    """
    A relationships endpoint that moves a reader to a memo that has his e-mail: 409 without
    a pointer (its body is the relationship, not the document of the item).
    """
    first, second = Memo.objects.create(title='First'), Memo.objects.create(title='Second')
    Reader.objects.create(memo=first, email='a@example.com')
    reader = Reader.objects.create(memo=second, email='a@example.com')
    response = TestClient(sample_app, raise_server_exceptions=False).patch(
        f'/api/v1/catalog/reader/{reader.pk}/relationships/memo',
        headers={'Content-Type': 'application/vnd.api+json'},
        json={'data': {'type': 'catalog.memo', 'id': str(first.pk)}},
    )
    conflict_without_fields(response)
    assert Reader.objects.get(pk=reader.pk).memo_id == second.pk


@pytest.mark.django_db(transaction=True)
def test_conflict_of_a_model_whose_default_reads_the_database(sample_app, monkeypatch):
    """
    The message of the conflict is made without an instance of the model: a default that
    reads the database (a next number) failed in the handler (SynchronousOnlyOperation, a
    500).
    """
    field = Country._meta.get_field('name')
    monkeypatch.setattr(field, '_get_default', lambda: f'Country {Country.objects.count()}')
    assert create(sample_app, 'Chile').status_code == 201
    response = create(sample_app, 'Chile')
    assert response.status_code == 409, response.content
    assert [it['source'] for it in response.json()['errors']] == [{'pointer': '/data/attributes/name'}]

    def fail():
        raise AssertionError('an instance of the model is created')

    monkeypatch.setattr(field, '_get_default', fail)
    assert unique_constraint_error(Country, 'entity_country_name_key') == (
        ('name',),
        'Country with this Country Name already exists.',
    )


@pytest.mark.django_db
@pytest.mark.parametrize('model', apps.get_models(), ids=lambda it: it._meta.label)
def test_unique_constraint_names(model):
    """
    Every unique constraint and unique index of the tables of the sample, as the migrations
    made them, maps to its columns (`unique_constraint_error`): a `unique=True` field
    (created with the table, `_key`, or added later, `_uniq`), a `unique_together`, a
    `UniqueConstraint`.
    """
    if model._meta.proxy or not model._meta.managed:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT index.relname, array_agg(attribute.attname ORDER BY key.ord)
            FROM pg_index AS i
            JOIN pg_class AS index ON index.oid = i.indexrelid
            JOIN pg_class AS tbl ON tbl.oid = i.indrelid
            CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS key(attnum, ord)
            LEFT JOIN pg_attribute AS attribute
                ON attribute.attrelid = tbl.oid AND attribute.attnum = key.attnum
            WHERE i.indisunique AND NOT i.indisprimary AND tbl.relname = %s
              AND tbl.relnamespace = 'public'::regnamespace
            GROUP BY index.relname
            """,
            [model._meta.db_table],
        )
        uniques = cursor.fetchall()
    for name, columns in uniques:
        found = unique_constraint_error(model, name)
        assert found, (model, name)
        fields, message = found
        assert sorted(model._meta.get_field(it).column for it in fields) == sorted(columns)
        assert message


def test_unique_constraint_of_expressions(monkeypatch):
    """
    A `UniqueConstraint` of expressions points to the fields they name; one that declares
    its message gives it; a name that is no constraint of the model is None.
    """
    lower = models.UniqueConstraint(Lower('email'), F('memo'), name='reader_lower_email_uniq')
    told = models.UniqueConstraint(
        fields=['memo', 'email'], name='reader_told_uniq', violation_error_message='Subscribed'
    )
    monkeypatch.setattr(Reader._meta, 'constraints', [lower, told])
    assert unique_constraint_error(Reader, 'reader_lower_email_uniq') == (
        ('email', 'memo'),
        'Reader with this E-mail and Memo already exists.',
    )
    assert unique_constraint_error(Reader, 'reader_told_uniq') == (('memo', 'email'), 'Subscribed')
    assert unique_constraint_error(Reader, 'catalog_step_number_uniq') is None


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
    statuses = [r.status_code for r in parallel(calls)]
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

    responses = parallel(
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


def rename(app, reader, email):
    """An action of the reader (set_item with a lock, as the actions bazis-permit checks)."""
    return TestClient(app, raise_server_exceptions=False).post(
        f'/api/v1/catalog/reader/{reader.pk}/rename/', json={'email': email}
    )


def normalize(app, memo):
    """An action of the memo: the memo locked, then each of its readers saved."""
    return TestClient(app, raise_server_exceptions=False).post(
        f'/api/v1/catalog/memo/{memo.pk}/normalize/'
    )


def retried(responses) -> list:
    return [
        r for r in responses if r.status_code == 409 and r.json()['errors'][0].get('meta')
    ]


@pytest.mark.django_db(transaction=True)
def test_an_action_of_the_item_locks_the_parent_first(sample_app, monkeypatch):
    """
    An action of an item that takes it locked (`set_item(with_lock=True)`, as bazis-permit
    does for the write actions of an item) locks the parent of `lock_on_write` before the
    item: it waits for a write of the parent that saves the item, no deadlock. The two are
    put in the order that deadlocked before (the item locked first, then its parent): the
    action of the memo holds the memo and saves the reader after the action of the reader
    started.
    """
    memo = Memo.objects.create(title='Plan')
    reader = Reader.objects.create(memo=memo, email='A@Example.com')
    parent_holds = threading.Event()

    def save(self, *args, **kwargs):
        if isinstance(JsonApiMixin.CTX_ROUTE.get(), MemoRouteSet):
            parent_holds.set()
            # the action of the reader runs meanwhile, up to the lock it waits for
            time.sleep(0.5)
        JsonApiMixin.save(self, *args, **kwargs)

    monkeypatch.setattr(Reader, 'save', save)

    def rename_later():
        assert parent_holds.wait(10)
        return rename(sample_app, reader, 'B@Example.com')

    responses = parallel([lambda: normalize(sample_app, memo), rename_later])

    assert [r.status_code for r in responses] == [200, 200], [r.content for r in responses]
    reader.refresh_from_db()
    # the action of the reader waited for the memo: it wrote last
    assert reader.email == 'B@Example.com'


@pytest.mark.django_db(transaction=True)
def test_actions_of_the_parent_and_of_the_items_race(sample_app):
    """
    Writes of the parent that save its items race the actions of the items: no deadlock (a
    409 with `meta.retry`), no 500.
    """
    for round_ in range(3):
        memo = Memo.objects.create(title=f'Plan {round_}')
        readers = [
            Reader.objects.create(memo=memo, email=f'R{i}@Example.com') for i in range(3)
        ]
        calls = [lambda memo=memo: normalize(sample_app, memo)] * 3 + [
            lambda reader=reader: rename(sample_app, reader, f'N{reader.pk}@Example.com')
            for reader in readers
        ]
        responses = parallel(calls)
        assert [r.status_code for r in responses] == [200] * 6, [r.content for r in responses]
        assert not retried(responses)


@pytest.mark.django_db(transaction=True)
def test_set_item_locks_the_parents_before_the_item():
    """
    `set_item(with_lock=True)` on a route of a model with `lock_on_write`: the parent by the
    value read without a lock, the item, the parent again (held: no wait).
    """
    memo = Memo.objects.create(title='Plan')
    reader = Reader.objects.create(memo=memo, email='a@example.com')
    route = ReaderRouteSet(inject=SimpleNamespace(), route_ctx=SimpleNamespace(store={}))
    with transaction.atomic(), CaptureQueriesContext(connection) as queries:
        assert route.set_item(str(reader.pk), with_lock=True) == reader
    assert locks_and_inserts(queries) == [
        'lock catalog_memo',
        'lock catalog_reader',
        'lock catalog_memo',
    ]
    lock = next(q['sql'] for q in queries if 'FOR NO KEY UPDATE' in q['sql'])
    assert f'= {memo.pk}' in lock


@contextmanager
def queries_of_the_requests():
    """The SQL of the connections opened inside the block (those of the endpoints)."""
    found = []

    def record(execute, sql, params, many, context):
        found.append(sql)
        return execute(sql, params, many, context)

    def created(sender, connection, **kwargs):
        connection.execute_wrappers.append(record)

    connection_created.connect(created, weak=False)
    try:
        yield found
    finally:
        connection_created.disconnect(created)


def parent_locked_before_each_update(sqls, table) -> bool:
    """Each UPDATE of `table` right after a lock of the memo (lock_on_write of the item)."""
    updates = [i for i, sql in enumerate(sqls) if sql.startswith(f'UPDATE "{table}"')]
    return bool(updates) and all(
        'FOR NO KEY UPDATE' in sqls[i - 1] and '"catalog_memo"' in sqls[i - 1] for i in updates
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('path', ['relationships', 'update', 'create'])
def test_linked_by_a_reverse_relation(sample_app, monkeypatch, path):
    """
    The items a reverse foreign key links (the relationships endpoints, the update and the
    create of the parent with the relation) are saved one by one with their lock, also of a
    model without validate_item that declares `lock_on_write` (`Card`), not by a bulk
    update without the lock.
    """
    monkeypatch.setattr(Card, 'lock_on_write', ('memo',))
    memo = Memo.objects.create(title='Plan')
    cards = [Card.objects.create(name=f'Card {i}') for i in range(2)]
    linked = [{'type': 'catalog.card', 'id': str(card.pk)} for card in cards]
    client = get_api_client(sample_app)
    with queries_of_the_requests() as queries:
        if path == 'relationships':
            response = client.post(
                f'/api/v1/catalog/memo/{memo.pk}/relationships/cards', json_data={'data': linked}
            )
        elif path == 'update':
            response = client.patch(
                f'/api/v1/catalog/memo/{memo.pk}/',
                json_data={
                    'data': {
                        'id': str(memo.pk),
                        'type': 'catalog.memo',
                        'relationships': {'cards': {'data': linked}},
                    }
                },
            )
        else:
            response = client.post(
                '/api/v1/catalog/memo/',
                json_data={
                    'data': {
                        'type': 'catalog.memo',
                        'attributes': {'title': 'New'},
                        'relationships': {'cards': {'data': linked}},
                    }
                },
            )
    assert response.status_code in (200, 201, 204), response.text
    assert parent_locked_before_each_update(queries, 'catalog_card'), queries
    assert Card.objects.exclude(memo=None).count() == 2

