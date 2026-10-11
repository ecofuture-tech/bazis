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
A many-to-many relation with a through model of the project is written like any other
(optional with `blank=True`), its reverse side is read-only; the recipe of the guide "no
overlapping intervals of a participant" (sample `validation.Session`): the through model
holds the period of the session (filled by triggers) under an exclusion constraint.
"""

from datetime import UTC, datetime

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange

import pytest
from bazis_test_utils.utils import get_api_client, parallel
from validation.models import Person, Session, SessionHost

from bazis.core.utils.model_meta import FieldsInfo, get_relation_kwargs


URL = '/api/v1/validation/session/'


def at(hour, minute=0):
    return datetime(2026, 10, 12, hour, minute, tzinfo=UTC)


def document(title, start, end, hosts=None, pk=None):
    data = {
        'type': 'validation.session',
        'attributes': {'title': title, 'dt_start': start.isoformat(), 'dt_end': end.isoformat()},
    }
    if pk:
        data['id'] = str(pk)
    if hosts is not None:
        data['relationships'] = {
            'hosts': {'data': [{'type': 'validation.person', 'id': str(it.pk)} for it in hosts]}
        }
    return {'data': data}


def create(app, title, start, end, hosts=None):
    return get_api_client(app).post(URL, json_data=document(title, start, end, hosts))


def conflict(response):
    assert response.status_code == 409, response.text
    (error,) = response.json()['errors']
    assert error['code'] == 'ERR_CONFLICT'
    assert 'source' not in error


def test_forward_side_is_writable_and_optional_with_blank():
    info = FieldsInfo.get_fields_info(Session)
    kwargs = get_relation_kwargs('hosts', info.relations['hosts'])
    assert 'read_only' not in kwargs
    assert kwargs['required'] is False
    assert kwargs['allow_blank'] is True

    reverse = FieldsInfo.get_fields_info(Person).relations['sessions']
    assert get_relation_kwargs('sessions', reverse)['read_only'] is True


@pytest.mark.django_db(transaction=True)
def test_schemas_of_the_writes(sample_app):
    client = get_api_client(sample_app)
    session = Session.objects.create(title='Session', dt_start=at(9), dt_end=at(10))
    for path in ('schema_create/', f'{session.pk}/schema_update/'):
        schema = client.get(f'{URL}{path}').json()
        (relationships,) = [
            it
            for name, it in schema['$defs'].items()
            if 'Relationships' in name and 'hosts' in it.get('properties', {})
        ]
        assert 'hosts' not in relationships.get('required', []), path
        assert not relationships['properties']['hosts'].get('readOnly'), path


@pytest.mark.django_db(transaction=True)
def test_create_with_and_without_hosts(sample_app):
    ann, bob = Person.objects.create(name='Ann'), Person.objects.create(name='Bob')

    response = create(sample_app, 'Without hosts', at(9), at(10))
    assert response.status_code == 201, response.text
    assert response.json()['data']['relationships']['hosts']['data'] == []

    response = create(sample_app, 'With hosts', at(10), at(11), [ann, bob])
    assert response.status_code == 201, response.text
    session = Session.objects.get(pk=response.json()['data']['id'])
    assert set(session.hosts.all()) == {ann, bob}
    # the period of the rows of the through model is filled by the trigger
    assert {it.period for it in SessionHost.objects.filter(session=session)} == {
        DateTimeTZRange(at(10), at(11))
    }


@pytest.mark.django_db(transaction=True)
def test_no_overlapping_sessions_of_a_host(sample_app):
    ann, bob = Person.objects.create(name='Ann'), Person.objects.create(name='Bob')
    assert create(sample_app, 'First', at(10), at(11), [ann]).status_code == 201

    # the same host at an overlapping time: refused by the exclusion constraint
    conflict(create(sample_app, 'Overlaps', at(10, 30), at(11, 30), [ann, bob]))
    assert not Session.objects.filter(title='Overlaps').exists()
    # another host, or the next hour (the ranges are half-open): created
    assert create(sample_app, 'Other host', at(10, 30), at(11, 30), [bob]).status_code == 201
    response = create(sample_app, 'Next', at(11), at(12), [ann])
    assert response.status_code == 201, response.text
    later = response.json()['data']['id']

    client = get_api_client(sample_app)
    # moving a session over another one of its host: the trigger moves the periods
    moved = client.patch(f'{URL}{later}/', json_data=document('Next', at(10, 45), at(12), pk=later))
    conflict(moved)
    assert Session.objects.get(pk=later).dt_start == at(11)

    # adding the host by the relationships endpoint is refused the same way
    other = Session.objects.get(title='Other host')
    response = client.post(
        f'{URL}{other.pk}/relationships/hosts',
        json_data={'data': [{'type': 'validation.person', 'id': str(ann.pk)}]},
    )
    conflict(response)
    assert list(other.hosts.all()) == [bob]


@pytest.mark.django_db(transaction=True)
def test_parallel_sessions_of_a_host(sample_app):
    ann = Person.objects.create(name='Ann')
    responses = parallel(
        [
            lambda: create(sample_app, 'One', at(10), at(11), [ann]),
            lambda: create(sample_app, 'Two', at(10, 30), at(11, 30), [ann]),
        ]
    )
    assert sorted(it.status_code for it in responses) == [201, 409]
    assert SessionHost.objects.filter(host=ann).count() == 1
