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
The geographic filters (`near`, a point, `in_bbox`) and the sorting by the distance from a
point of a request (`<point field>__distance(<lon>,<lat>)`), in meters on the sphere, for a
geography point (`location`), a geometry point in WGS 84 (`entrance`) and in another
projection (`mercator`). `secret` is not in the schema of the route.
"""

from django.conf import settings
from django.contrib.gis.geos import Point
from django.db.models import F

import pytest
from bazis_test_utils.utils import get_api_client
from geo.models import Place

from bazis.core.services.sorting import SortingSearching
from bazis.core.utils.geo import parse_distance, parse_point, point_distance


PLACES = '/api/v1/geo/place/'
MOSCOW = '37.6173,55.7558'
SPB = '30.3351,59.9343'
# the distances from Moscow on the sphere: Tver 162.0 km, Saint Petersburg 633.0 km,
# Kazan 717.7 km
CITIES = {
    'moscow': (37.6173, 55.7558),
    'tver': (35.9006, 56.8587),
    'spb': (30.3351, 59.9343),
    'kazan': (49.1064, 55.7963),
}
POINT_FIELDS = ['location', 'entrance', 'mercator']


@pytest.fixture
def places(db):
    for name, (lon, lat) in CITIES.items():
        point = Point(lon, lat, srid=4326)
        Place.objects.create(
            name=name,
            location=point,
            entrance=point,
            mercator=point.transform(3857, clone=True),
            secret=point,
        )
    Place.objects.create(name='nowhere')


def get(sample_app, **params):
    return get_api_client(sample_app).get(PLACES, params=params)


def names(sample_app, **params):
    response = get(sample_app, **params)
    assert response.status_code == 200, response.text
    return [it['attributes']['name'] for it in response.json()['data']]


def assert_bad_request(response, loc):
    assert response.status_code == 400, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_FILTER'
    assert error['source'] == {'pointer': f'/query/{loc}'}


@pytest.mark.parametrize(
    'value, meters',
    [('500', 500), ('500m', 500), ('2.5km', 2500), ('2.5 KM', 2500), ('.5km', 500)],
)
def test_parse_distance(value, meters):
    assert parse_distance(value) == meters


@pytest.mark.parametrize('value', ['', 'km', '-5', '1e3', '5 miles', '5kmm', 'nan'])
def test_parse_distance_refuses(value):
    with pytest.raises(ValueError, match='A distance is'):
        parse_distance(value)


def test_parse_point():
    point = parse_point(' 37.6 , 55.7 ')
    assert (point.x, point.y, point.srid) == (37.6, 55.7, 4326)


@pytest.mark.parametrize('value', ['37.6', '37.6,55.7,1', 'a,b', '', 'inf,0'])
def test_parse_point_refuses(value):
    with pytest.raises(ValueError, match="A point is '<longitude>,<latitude>'|out of range"):
        parse_point(value)


@pytest.mark.parametrize('value', ['181,0', '0,-91'])
def test_parse_point_out_of_range(value):
    with pytest.raises(ValueError, match='out of range'):
        parse_point(value)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('field', POINT_FIELDS)
def test_near(sample_app, places, field):
    near = f'{field}__near={MOSCOW}'
    # 100 m by default
    assert names(sample_app, filter=near) == ['moscow']
    # meters without a unit, as before, and kilometers
    assert sorted(names(sample_app, filter=f'{near},161000')) == ['moscow']
    assert sorted(names(sample_app, filter=f'{near},163000')) == ['moscow', 'tver']
    assert sorted(names(sample_app, filter=f'{near},161km')) == ['moscow']
    assert sorted(names(sample_app, filter=f'{near},163km')) == ['moscow', 'tver']
    assert sorted(names(sample_app, filter=f'{near},700km')) == ['moscow', 'spb', 'tver']
    # the point itself: within 10 m
    assert names(sample_app, filter=f'{field}={MOSCOW}') == ['moscow']
    assert names(sample_app, filter=f'{field}=37.6175,55.7558') == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('field', POINT_FIELDS)
def test_sort_by_distance(sample_app, places, field):
    nearest = names(sample_app, sort=f'{field}__distance({MOSCOW})')
    # the places without a point last, in both directions
    assert nearest == ['moscow', 'tver', 'spb', 'kazan', 'nowhere']
    farthest = names(sample_app, sort=f'-{field}__distance({MOSCOW})')
    assert farthest == ['kazan', 'spb', 'tver', 'moscow', 'nowhere']
    assert names(sample_app, sort=f'{field}__distance({SPB}),name') == [
        'spb',
        'tver',
        'moscow',
        'kazan',
        'nowhere',
    ]


@pytest.mark.django_db(transaction=True)
def test_sort_and_filter_nearby(sample_app, places):
    """The recipe of the guide: the places within 700 km, the nearest first."""
    assert names(
        sample_app,
        filter=f'location__near={SPB},700km',
        sort=f'location__distance({SPB}),name',
    ) == ['spb', 'tver', 'moscow']


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'sort',
    [
        # not in the schema of the route, answered as an unknown field
        f'secret__distance({MOSCOW})',
        f'unknown__distance({MOSCOW})',
        # not a point field
        f'name__distance({MOSCOW})',
        # not a field of the route itself
        f'place__location__distance({MOSCOW})',
        # malformed points
        'location__distance(37.6)',
        'location__distance(37.6,55.7,1)',
        'location__distance(200,0)',
        'location__distance()',
        f'location__distance({MOSCOW}',
        'location__distance',
    ],
)
def test_sort_by_distance_refused(sample_app, places, sort):
    assert_bad_request(get(sample_app, sort=sort), 'sort')


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'filter_str',
    [
        f'secret__near={MOSCOW},10km',
        f'secret={MOSCOW}',
        'location__near=37.6',
        f'location__near={MOSCOW},10km,1',
        f'location__near={MOSCOW},10 miles',
        'location__near=200,0,10km',
        'location=x,y',
        f'location__distance={MOSCOW}',
    ],
)
def test_filter_refused(sample_app, places, filter_str):
    assert_bad_request(get(sample_app, filter=filter_str), 'filter')


@pytest.mark.django_db(transaction=True)
def test_not_strict_reaches_every_point_field(sample_app, places, monkeypatch):
    """Without the scope (`BAZIS_FILTERS_STRICT` off) any point field of the model sorts."""
    monkeypatch.setattr(settings, 'BAZIS_FILTERS_STRICT', False)
    assert names(sample_app, sort=f'secret__distance({SPB})')[0] == 'spb'


def test_sort_terms_keep_the_point():
    sorting = SortingSearching(f'-location__distance({MOSCOW}), name,location__distance(1,2)')
    assert sorting.terms == [f'-location__distance({MOSCOW})', 'name', 'location__distance(1,2)']


@pytest.mark.django_db
def test_point_distance_expression(places):
    """The distance in meters on the sphere, for an annotation of a project."""
    origin = parse_point(MOSCOW)
    for field in POINT_FIELDS:
        distances = dict(
            Place.objects.annotate(
                distance=point_distance(Place._meta.get_field(field), origin)
            ).values_list('name', 'distance')
        )
        assert round(distances['tver'] / 1000, 1) == 162.0
        assert round(distances['spb'] / 1000, 1) == 633.0
        assert distances['moscow'] == 0
        assert distances['nowhere'] is None
    # a point of another row: an expression of a point field
    spb = Place.objects.filter(name='spb').values('location')[:1]
    from django.db.models import Subquery

    nearest = (
        Place.objects.exclude(location=None)
        .annotate(distance=point_distance(Place._meta.get_field('entrance'), Subquery(spb)))
        .order_by(F('distance').asc())
        .values_list('name', flat=True)
    )
    assert list(nearest) == ['spb', 'tver', 'moscow', 'kazan']


@pytest.mark.django_db(transaction=True)
def test_point_as_geojson(sample_app):
    """
    The guide: the API shows and takes a point as GeoJSON (longitude first, WGS 84); a write
    of a point was a 500 (the GeoJSON object was set on the field as it is).
    """
    client = get_api_client(sample_app)
    point = {'type': 'Point', 'coordinates': [37.6173, 55.7558]}
    response = client.post(
        PLACES,
        json_data={
            'data': {
                'type': 'geo.place',
                'attributes': {'name': 'x', 'location': point, 'mercator': point},
            }
        },
    )
    assert response.status_code == 201, response.text
    place_id = response.json()['data']['id']
    assert response.json()['data']['attributes']['location'] == point
    assert names(sample_app, filter=f'location__near={MOSCOW},1m') == ['x']
    # the projected field stores the point in its own projection
    assert names(sample_app, filter=f'mercator__near={MOSCOW},1m') == ['x']

    tver = {'type': 'Point', 'coordinates': list(CITIES['tver'])}
    response = client.patch(
        f'{PLACES}{place_id}/',
        json_data={'data': {'id': place_id, 'type': 'geo.place', 'attributes': {'entrance': tver}}},
    )
    assert response.status_code == 200, response.text
    assert Place.objects.get(pk=place_id).entrance.coords == CITIES['tver']


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'value',
    [{'type': 'Point', 'coordinates': [1]}, {'type': 'Point', 'coordinates': ['a', 'b']}],
)
def test_malformed_geojson(sample_app, value):
    response = get_api_client(sample_app).post(
        PLACES,
        json_data={'data': {'type': 'geo.place', 'attributes': {'name': 'x', 'location': value}}},
    )
    assert response.status_code == 422, response.text
    error = response.json()['errors'][0]
    assert (error['code'], error['source']) == (
        'ERR_VALIDATE',
        {'pointer': '/data/attributes/location'},
    )
