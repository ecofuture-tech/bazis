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
The database connections of the threads other than the main one: the sync endpoints run in
the worker threads of AnyIO, each with its own connection kept for `CONN_MAX_AGE`, and a
worker ends after 10 s without work. The connection of a thread is closed when the thread
ends, not left to the garbage collector (an idle PostgreSQL session until a collection,
then a `ResourceWarning` of psycopg).

The garbage collector is disabled in these tests: a connection is closed only by Bazis.
"""

import gc
import threading
import time
import warnings

from django.db import connection, connections
from django.db.backends.signals import connection_created

from starlette.testclient import TestClient

import pytest


URL = '/api/v1/entity/parent_entity/'


class OpenedInThreads:
    """The connections opened by the threads other than the main one during a test."""

    def __init__(self):
        self.threads = []
        self.pids = []

    def __call__(self, sender, connection, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return
        self.threads.append(threading.current_thread())
        self.pids.append(connection.connection.info.backend_pid)

    def join(self):
        for thread in self.threads:
            thread.join(timeout=10)
            assert not thread.is_alive(), thread

    @staticmethod
    def live(pids) -> list[int]:
        """The sessions of `pids` that PostgreSQL still has."""
        with connection.cursor() as cursor:
            cursor.execute('SELECT pid FROM pg_stat_activity WHERE pid = ANY(%s)', [list(pids)])
            return [row[0] for row in cursor.fetchall()]


@pytest.fixture
def opened_in_threads():
    gc.collect()
    gc.disable()
    opened = OpenedInThreads()
    connection_created.connect(opened, weak=False, dispatch_uid='test_thread_connections')
    try:
        yield opened
    finally:
        connection_created.disconnect(dispatch_uid='test_thread_connections')
        gc.enable()


def assert_no_unclosed_connection():
    """Nothing the garbage collector frees is a connection still open."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always', ResourceWarning)
        gc.collect()
    unclosed = [
        str(it.message)
        for it in caught
        if issubclass(it.category, ResourceWarning) and 'psycopg' in str(it.message)
    ]
    assert not unclosed


@pytest.mark.django_db(transaction=True)
def test_connection_of_a_thread_is_closed_when_it_ends(opened_in_threads):
    from entity.models import ParentEntity

    thread = threading.Thread(target=lambda: ParentEntity.objects.exists())
    thread.start()
    thread.join()

    assert len(opened_in_threads.pids) == 1
    assert opened_in_threads.live(opened_in_threads.pids) == []
    assert_no_unclosed_connection()


@pytest.mark.django_db(transaction=True)
def test_closed_connection_of_a_thread_and_the_main_one(opened_in_threads):
    """A thread that closed its connection ends as well; the main thread keeps its own."""
    from entity.models import ParentEntity

    def work():
        ParentEntity.objects.exists()
        connections.close_all()

    connection.ensure_connection()
    main_pid = connection.connection.info.backend_pid
    thread = threading.Thread(target=work)
    thread.start()
    thread.join()

    assert len(opened_in_threads.pids) == 1
    assert opened_in_threads.live(opened_in_threads.pids + [main_pid]) == [main_pid]
    assert_no_unclosed_connection()


@pytest.mark.django_db(transaction=True)
def test_connections_of_the_ended_workers_are_closed(sample_app, opened_in_threads):
    """
    Outside a `with` block a `TestClient` runs every request in a new event loop: AnyIO
    stops its worker threads when the loop ends, as it stops a worker without work.
    """
    client = TestClient(sample_app)
    for _ in range(3):
        assert client.get(URL).status_code == 200

    opened_in_threads.join()
    assert len(opened_in_threads.pids) == 3
    assert opened_in_threads.live(opened_in_threads.pids) == []
    assert_no_unclosed_connection()


@pytest.mark.django_db(transaction=True)
def test_worker_reuses_its_connection(sample_app, opened_in_threads):
    """A worker keeps its connection between the requests for `CONN_MAX_AGE`."""
    with TestClient(sample_app) as client:
        for _ in range(3):
            assert client.get(URL).status_code == 200
        pids = list(opened_in_threads.pids)
        assert len(pids) == 1
        assert opened_in_threads.live(pids) == pids

    opened_in_threads.join()
    assert opened_in_threads.live(pids) == []
    assert_no_unclosed_connection()


@pytest.mark.django_db(transaction=True)
def test_endpoint_closes_an_obsolete_connection(sample_app, opened_in_threads, monkeypatch):
    """
    The endpoint closes the connection of its worker once it is past `CONN_MAX_AGE`: the
    one of the sync dependencies when it starts, its own when it ends.
    """
    monkeypatch.setitem(connections.settings['default'], 'CONN_MAX_AGE', 0)

    with TestClient(sample_app) as client:
        for _ in range(2):
            assert client.get(URL).status_code == 200
            pids = list(opened_in_threads.pids)
            assert pids
            assert opened_in_threads.live(pids) == []
        assert len(opened_in_threads.pids) >= 2


@pytest.mark.django_db(transaction=True)
def test_plain_route_reconnects_after_its_connection_broke(opened_in_threads):
    """
    A plain sync FastAPI route, outside the route sets, gets the checks of the connection
    of its worker on every request: once the connection broke, the next request on that
    worker checks it again (`CONN_HEALTH_CHECKS`) and reconnects.
    """
    from bazis.core.app_factory import _create_app_base, _initialize_app

    app = _create_app_base()
    _initialize_app(app)

    @app.get('/plain-connection/')
    def plain_connection():
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid()')
            return cursor.fetchone()[0]

    with TestClient(app) as client:
        first = client.get('/plain-connection/').json()
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_terminate_backend(%s)', [first])
        for _ in range(100):
            if not opened_in_threads.live([first]):
                break
            time.sleep(0.05)

        response = client.get('/plain-connection/')
        assert response.status_code == 200
        assert response.json() != first
        pids = list(opened_in_threads.pids)
        assert opened_in_threads.live(pids) == [response.json()]

    opened_in_threads.join()
    assert opened_in_threads.live(opened_in_threads.pids) == []
    assert_no_unclosed_connection()
