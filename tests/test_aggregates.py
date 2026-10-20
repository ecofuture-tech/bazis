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
The meta `aggregates` of a list: the functions of `aggregate` over all the objects of the
list with its filter and search (not its page), grouped by `group`; the fields are those
the filter of the route reaches for the user, an error is 400 `ERR_AGGREGATE`.
"""

from datetime import UTC, datetime
from decimal import Decimal

from django.db import models
from django.test import override_settings

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import CarrierTask, ChildEntity, ParentEntity
from entity.routes import ParentEntityRouteSet
from visibility.models import Folder, Label, Note

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase

# every query of the requests is logged to sql.log
import tests.utils.assert_sql  # noqa: F401


PARENTS = '/api/v1/entity/parent_entity/'
TASKS = '/api/v1/entity/carrier_task/'
BRIEF = '/api/v1/visibility/note_brief/'


@pytest.fixture
def parents(db):
    def parent(name, price, state, is_active, dt_approved):
        return ParentEntity.objects.create(
            name=name,
            price=price,
            state=state,
            is_active=is_active,
            dt_approved=dt_approved and datetime(*dt_approved, 12, tzinfo=UTC),
        )

    return [
        parent('alpha', Decimal('10.00'), 'state_one', True, (2026, 1, 15)),
        parent('beta', Decimal('20.50'), 'state_two', True, (2026, 1, 20)),
        parent('gamma', Decimal('30.00'), 'state_one', False, (2026, 2, 3)),
        parent('delta', None, 'state_two', False, None),
    ]


def get(sample_app, url, **params):
    return get_api_client(sample_app).get(url, params=params)


def aggregates(sample_app, url=PARENTS, **params):
    response = get(sample_app, url, meta='aggregates', **params)
    assert response.status_code == 200, response.text
    return response.json()['meta']['aggregates']


def assert_bad_request(response, param):
    assert response.status_code == 400, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_AGGREGATE'
    assert error['source'] == {'pointer': f'/query/{param}'}
    return error


@pytest.mark.django_db(transaction=True)
def test_the_aggregates_of_the_list(sample_app, parents):
    result = aggregates(
        sample_app,
        aggregate='count,sum(price),avg(price),min(price),max(price),count(price),'
        'min(dt_approved),max(dt_approved)',
    )
    assert Decimal(result.pop('avg(price)')).quantize(Decimal('0.01')) == Decimal('20.17')
    assert result == {
        'count': 4,
        'sum(price)': '60.50',
        'min(price)': '10.00',
        'max(price)': '30.00',
        'count(price)': 3,
        'min(dt_approved)': '2026-01-15T12:00:00Z',
        'max(dt_approved)': '2026-02-03T12:00:00Z',
    }


@pytest.mark.django_db(transaction=True)
def test_count_by_default(sample_app, parents):
    assert aggregates(sample_app) == {'count': 4}
    assert aggregates(sample_app, group='state') == [
        {'group': 'state_one', 'values': {'count': 2}},
        {'group': 'state_two', 'values': {'count': 2}},
    ]


@pytest.mark.django_db(transaction=True)
def test_group_by_a_choice_and_a_boolean(sample_app, parents):
    assert aggregates(sample_app, aggregate='count,sum(price)', group='state') == [
        {'group': 'state_one', 'values': {'count': 2, 'sum(price)': '40.00'}},
        {'group': 'state_two', 'values': {'count': 2, 'sum(price)': '20.50'}},
    ]
    assert aggregates(sample_app, aggregate='sum(price)', group='is_active') == [
        {'group': 'false', 'values': {'sum(price)': '30.00'}},
        {'group': 'true', 'values': {'sum(price)': '30.50'}},
    ]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'bucket, groups',
    [
        ('month', [('2026-01-01', 2), ('2026-02-01', 1), (None, 1)]),
        ('week', [('2026-01-12', 1), ('2026-01-19', 1), ('2026-02-02', 1), (None, 1)]),
        ('day', [('2026-01-15', 1), ('2026-01-20', 1), ('2026-02-03', 1), (None, 1)]),
    ],
)
def test_group_by_a_date(sample_app, parents, bucket, groups):
    """By the ISO date of the start of the bucket (a week starts on Monday), None last."""
    assert aggregates(sample_app, group=f'dt_approved:{bucket}') == [
        {'group': group, 'values': {'count': count}} for group, count in groups
    ]


@pytest.mark.django_db(transaction=True)
def test_group_by_a_relation(sample_app, sample_vehicle_data):
    """The group of a to-one relation is the id of the related object."""
    data = sample_vehicle_data
    CarrierTask.objects.create(
        vehicle=data['vehicle'], driver=data['driver'], fact_waste_weight=Decimal('1.25')
    )
    assert aggregates(
        sample_app, TASKS, aggregate='count,sum(fact_waste_weight)', group='org_owner'
    ) == [
        {
            'group': str(data['organization'].pk),
            'values': {'count': 3, 'sum(fact_waste_weight)': '12.500'},
        },
        {'group': None, 'values': {'count': 1, 'sum(fact_waste_weight)': '1.250'}},
    ]


@pytest.mark.django_db(transaction=True)
def test_a_date_bucket_in_the_time_zone_of_the_project(sample_app, db):
    """22:30 UTC of January 15 is January 16 in Moscow."""
    ParentEntity.objects.create(name='late', dt_approved=datetime(2026, 1, 15, 22, 30, tzinfo=UTC))
    assert aggregates(sample_app, group='dt_approved:day') == [
        {'group': '2026-01-15', 'values': {'count': 1}}
    ]
    with override_settings(TIME_ZONE='Europe/Moscow'):
        assert aggregates(sample_app, group='dt_approved:day') == [
            {'group': '2026-01-16', 'values': {'count': 1}}
        ]


@pytest.mark.django_db(transaction=True)
def test_the_filter_and_the_search_apply_the_page_does_not(sample_app, parents, monkeypatch):
    params = {'aggregate': 'count,sum(price)'}
    assert aggregates(sample_app, filter='is_active=true', **params) == {
        'count': 2,
        'sum(price)': '30.50',
    }
    monkeypatch.setattr(ParentEntityRouteSet, 'search_fields', ['name'])
    assert aggregates(sample_app, search='alpha', **params) == {
        'count': 1,
        'sum(price)': '10.00',
    }
    response = get(sample_app, PARENTS, meta='aggregates,pagination', **{'page[limit]': 1})
    assert len(response.json()['data']) == 1
    assert response.json()['meta']['aggregates'] == {'count': 4}


@pytest.mark.django_db(transaction=True)
def test_an_empty_list(sample_app, parents):
    params = {'aggregate': 'count,sum(price),max(dt_approved)', 'filter': 'name=nothing'}
    assert aggregates(sample_app, **params) == {
        'count': 0,
        'sum(price)': None,
        'max(dt_approved)': None,
    }
    assert aggregates(sample_app, group='state', **params) == []


@pytest.mark.django_db(transaction=True)
def test_only_the_objects_of_the_list(sample_app, parents, monkeypatch):
    """
    The objects of `get_queryset_for_list` of the route, which a package restricts (the
    list of bazis-permit is the objects the user may view).
    """

    def get_queryset_for_list(self):
        return JsonapiRouteBase.get_queryset_for_list(self).filter(is_active=True)

    monkeypatch.setattr(ParentEntityRouteSet, 'get_queryset_for_list', get_queryset_for_list)
    response = get(sample_app, PARENTS, meta='aggregates,pagination', aggregate='count,sum(price)')
    meta = response.json()['meta']
    assert meta['aggregates'] == {'count': 2, 'sum(price)': '30.50'}
    assert meta['pagination']['count'] == 2
    assert aggregates(sample_app, group='is_active') == [{'group': 'true', 'values': {'count': 2}}]


@pytest.mark.django_db(transaction=True)
def test_an_object_the_list_repeats_counts_once(sample_app, parents, monkeypatch):
    """
    The objects are taken by their keys: a join of `get_queryset_for_list` that repeats an
    object (two of its children match) does not count it twice.
    """
    alpha = parents[0]
    alpha.child_entities.add(
        ChildEntity.objects.create(child_name='c1'), ChildEntity.objects.create(child_name='c2')
    )

    def get_queryset_for_list(self):
        return JsonapiRouteBase.get_queryset_for_list(self).filter(
            child_entities__child_name__startswith='c'
        )

    monkeypatch.setattr(ParentEntityRouteSet, 'get_queryset_for_list', get_queryset_for_list)
    assert aggregates(sample_app, aggregate='count,sum(price)') == {
        'count': 1,
        'sum(price)': '10.00',
    }
    assert aggregates(sample_app, aggregate='count,sum(price)', group='state') == [
        {'group': 'state_one', 'values': {'count': 1, 'sum(price)': '10.00'}}
    ]


@pytest.mark.django_db(transaction=True)
def test_the_number_of_the_groups_is_limited(sample_app, parents):
    """`BAZIS_API_AGGREGATE_GROUPS_MAX` groups at most; a total is not limited."""
    two = [
        {'group': 'state_one', 'values': {'count': 2}},
        {'group': 'state_two', 'values': {'count': 2}},
    ]
    with override_settings(BAZIS_API_AGGREGATE_GROUPS_MAX=2):
        open('sql.log', 'w').close()
        assert aggregates(sample_app, group='state') == two
        # the limit is in the query: one group more than the limit is fetched, not all
        with open('sql.log') as f:
            grouped = [line for line in f if '_aggregate_group' in line]
        assert len(grouped) == 1
        assert grouped[0].split(';')[0].endswith('LIMIT 3')
    with override_settings(BAZIS_API_AGGREGATE_GROUPS_MAX=1):
        error = assert_bad_request(
            get(sample_app, PARENTS, meta='aggregates', group='state'), 'group'
        )
        assert error['detail'].startswith("More than 1 groups of 'state'")
        assert aggregates(sample_app, aggregate='count,sum(price)') == {
            'count': 4,
            'sum(price)': '60.50',
        }


@pytest.mark.django_db(transaction=True)
def test_the_hint_of_a_group(sample_app, parents):
    """A date field is told its buckets; another field is not offered one."""
    date = assert_bad_request(
        get(sample_app, PARENTS, meta='aggregates', group='dt_approved'), 'group'
    )
    assert 'dt_approved:month' in date['detail']
    other = assert_bad_request(get(sample_app, PARENTS, meta='aggregates', group='id'), 'group')
    assert ':month' not in other['detail']


class HiddenManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().none()


@pytest.mark.django_db(transaction=True)
def test_a_filtering_default_manager(sample_app, parents, monkeypatch):
    """
    The objects are taken by the base manager: a default manager that hides them (a soft
    delete) leaves out none of a list built on another manager.
    """
    hidden = HiddenManager()
    hidden.model = ParentEntity
    monkeypatch.setattr(ParentEntity._meta, 'default_manager', hidden)
    monkeypatch.setattr(
        ParentEntityRouteSet, 'get_queryset', lambda self: ParentEntity._base_manager.all()
    )
    response = get(sample_app, PARENTS, meta='aggregates,pagination', group='state')
    meta = response.json()['meta']
    assert meta['pagination']['count'] == 4
    assert sum(it['values']['count'] for it in meta['aggregates']) == 4
    assert aggregates(sample_app) == {'count': 4}


@pytest.mark.django_db(transaction=True)
def test_only_the_fields_the_filter_reaches(sample_app, db):
    """
    A field out of the LIST schema of the route (`note_brief` shows no name and no label)
    is answered as a field that does not exist.
    """
    folder = Folder.objects.create(name='folder')
    Note.objects.create(name='secret', folder=folder, label=Label.objects.create(name='x'))
    assert aggregates(sample_app, BRIEF, group='folder') == [
        {'group': str(folder.pk), 'values': {'count': 1}}
    ]
    hidden = assert_bad_request(get(sample_app, BRIEF, meta='aggregates', group='label'), 'group')
    unknown = assert_bad_request(get(sample_app, BRIEF, meta='aggregates', group='none'), 'group')
    assert hidden['detail'] == unknown['detail'].replace('none', 'label')
    assert_bad_request(
        get(sample_app, BRIEF, meta='aggregates', aggregate='count(name)'), 'aggregate'
    )


@pytest.mark.django_db(transaction=True)
def test_the_fields_of_the_user(sample_app, parents, monkeypatch):
    """
    The fields of `query_fields` for the user (bazis-permit hides the fields a field
    permission hides): an aggregate and a group by a hidden field are refused like its filter.
    """
    query_fields = ParentEntityRouteSet.query_fields

    def without_price(cls, user=None, **kwargs):
        return [it for it in query_fields(user=user, **kwargs) if it.name not in ('price', 'state')]

    monkeypatch.setattr(ParentEntityRouteSet, 'query_fields', classmethod(without_price))
    assert_bad_request(
        get(sample_app, PARENTS, meta='aggregates', aggregate='sum(price)'), 'aggregate'
    )
    assert_bad_request(get(sample_app, PARENTS, meta='aggregates', group='state'), 'group')
    assert get(sample_app, PARENTS, filter='price=10').status_code == 400
    assert aggregates(sample_app, aggregate='count', group='is_active') == [
        {'group': 'false', 'values': {'count': 2}},
        {'group': 'true', 'values': {'count': 2}},
    ]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'param, value',
    [
        ('aggregate', 'median(price)'),
        ('aggregate', 'sum(price'),
        ('aggregate', 'sum()'),
        ('aggregate', 'count,'),
        ('aggregate', 'sum(nothing)'),
        ('aggregate', 'sum(name)'),
        ('aggregate', 'avg(dt_approved)'),
        ('aggregate', 'min(is_active)'),
        ('aggregate', 'sum(child_entities)'),
        ('aggregate', 'sum(count_active_children)'),
        ('aggregate', 'count(extended_entity)'),
        ('group', 'nothing'),
        ('group', 'name'),
        ('group', 'price'),
        ('group', 'dt_approved'),
        ('group', 'dt_approved:year'),
        ('group', 'state:month'),
        ('group', 'child_entities'),
        ('group', 'extended_entity'),
    ],
)
def test_invalid_arguments_are_400(sample_app, parents, param, value):
    assert_bad_request(get(sample_app, PARENTS, meta='aggregates', **{param: value}), param)


@pytest.mark.django_db(transaction=True)
def test_without_the_meta_nothing_is_computed(sample_app, parents):
    response = get(sample_app, PARENTS, aggregate='median(price)', group='name')
    assert response.status_code == 200, response.text
    assert 'aggregates' not in response.json().get('meta', {})


def queries(sample_app, **params):
    """The number of the queries of a request of the list."""
    open('sql.log', 'w').close()
    assert get(sample_app, PARENTS, **params).status_code == 200
    with open('sql.log') as f:
        return len([line for line in f if line.lstrip('(0123456789.) ').startswith('SELECT')])


@pytest.mark.django_db(transaction=True)
def test_one_query(sample_app, parents):
    base = queries(sample_app)
    assert queries(sample_app, meta='aggregates', aggregate='count,sum(price)') == base + 1
    assert queries(sample_app, meta='aggregates', group='dt_approved:month') == base + 1


def test_the_parameters_and_the_meta_in_the_openapi(sample_app):
    openapi = sample_app.openapi()
    operation = openapi['paths'][PARENTS]['get']
    names = {it['name'] for it in operation['parameters']}
    assert {'aggregate', 'group'} <= names

    def schema(ref):
        return openapi['components']['schemas'][ref.rsplit('/', 1)[-1]]

    response = operation['responses']['200']['content']['application/vnd.api+json']
    meta = schema(response['schema']['$ref'])['properties']['meta']['anyOf'][0]
    aggregates = schema(meta['$ref'])['properties']['aggregates']['anyOf']
    assert aggregates[0]['type'] == 'object'
    assert aggregates[1]['items'] == {'$ref': '#/components/schemas/AggregatesGroup'}
    assert set(schema(aggregates[1]['items']['$ref'])['properties']) == {'group', 'values'}


@pytest.mark.django_db(transaction=True)
def test_the_error_is_translated(sample_app, parents, monkeypatch):
    from django.conf import settings

    # not the fixture `settings`: see tests/test_request_language.py
    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    response = get_api_client(sample_app).get(
        PARENTS,
        params={'meta': 'aggregates', 'aggregate': 'sum(name)'},
        headers={'Accept-Language': 'ru'},
    )
    error = assert_bad_request(response, 'aggregate')
    assert error['title'] == 'Недопустимый агрегат'
    assert error['detail'] == "Агрегат 'sum(name)' неприменим к полю 'name'"
