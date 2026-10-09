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
Distances between points on the sphere (PostGIS geography), for the `near` filter and the
distance sorting of the routes and for the annotations of a project.

The distances are in meters on the sphere, as `ST_DistanceSphere`. A point field declared
with `geography=True` is used as it is, so its GiST index (created by Django) serves the
`near` filter (`ST_DWithin`) and the nearest N of a project
(`order_by(point_distance(...))[:n]`, the KNN operator `<->`); a geometry point field (the
default of `PointField`) is cast to geography on every row: the same distances, without
the index. The sorting of the routes adds the primary key after the distance (a stable
order for the pages), so it computes the distance of every row its filter leaves: bound it
with `near` on a large table.

Tags: RAG, EXPORT
"""

import json
import math
import re

from django.contrib.gis.db.models import GeometryField, PointField
from django.contrib.gis.db.models.functions import Transform
from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point
from django.db.models import BooleanField, F, FloatField, Func, Q, Value
from django.db.models.functions import Cast
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _


#: the coordinates of the points of a request: longitude, latitude (WGS 84)
SRID_WGS84 = 4326

_DISTANCE = re.compile(r'(?P<value>[0-9]*\.?[0-9]+)\s*(?P<unit>m|km)?', re.IGNORECASE)
_UNITS = {'': 1.0, 'm': 1.0, 'km': 1000.0}


def parse_point(value: str) -> Point:
    """
    The point of `<longitude>,<latitude>` (degrees of WGS 84). Raises ValueError for
    anything else.
    """
    try:
        lon, lat = (float(it) for it in value.split(','))
    except (AttributeError, TypeError, ValueError):
        raise ValueError(
            format_lazy(_("A point is '<longitude>,<latitude>', not '{value}'"), value=value)
        ) from None
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(
            format_lazy(
                _('The point {value} is out of range: longitude -180..180, latitude -90..90'),
                value=value,
            )
        )
    return Point(lon, lat, srid=SRID_WGS84)


def parse_distance(value: str) -> float:
    """
    The distance in meters of `<number>[m|km]` (`500`, `500m`, `2.5km`; a number without a
    unit is in meters). Raises ValueError for anything else.
    """
    if not isinstance(value, str) or not (match := _DISTANCE.fullmatch(value.strip())):
        raise ValueError(
            format_lazy(
                _("A distance is a number of meters or '<number>km', not '{value}'"), value=value
            )
        )
    return float(match['value']) * _UNITS[(match['unit'] or '').lower()]


def _geography_field() -> PointField:
    return PointField(geography=True, srid=SRID_WGS84)


def _geography(expression, field: GeometryField):
    """The expression of a value of the field as geography."""
    if field.geography:
        return expression
    if field.srid != SRID_WGS84:
        expression = Transform(expression, SRID_WGS84)
    return Cast(expression, _geography_field())


def _point(point):
    """A point (a GEOS point or an expression of a point field) as geography."""
    if hasattr(point, 'resolve_expression'):
        output_field = getattr(point, '_output_field_or_none', None)
        if isinstance(output_field, GeometryField):
            return _geography(point, output_field)
        return Cast(point, _geography_field())
    if point.srid != SRID_WGS84:
        point = point.transform(SRID_WGS84, clone=True)
    return Value(point, output_field=_geography_field())


def point_distance(field: GeometryField, point) -> Func:
    """
    The distance in meters on the sphere from the value of a point field of the model
    (`Site._meta.get_field('location')`) to a point: a GEOS point (`parse_point`) or an
    expression of a point (a `Subquery` of a point field). Null when the field is null.
    The KNN operator `<->`: for a geography field, an `order_by` by it alone with a limit
    (the nearest N) uses the GiST index of the field.

    Tags: RAG, EXPORT
    """
    return Func(
        _geography(F(field.name), field),
        _point(point),
        template='(%(expressions)s)',
        arg_joiner=' <-> ',
        output_field=FloatField(),
    )


def point_within(field: GeometryField, point, meters: float) -> Q:
    """
    The objects whose point field is within `meters` of a point on the sphere
    (`ST_DWithin`; for a geography field it uses the GiST index of the field).

    Tags: RAG, EXPORT
    """
    return Q(
        Func(
            _geography(F(field.name), field),
            _point(point),
            Value(float(meters)),
            Value(False),
            function='ST_DWithin',
            output_field=BooleanField(),
        )
    )


def geojson_geometry(value: dict, field: GeometryField) -> GEOSGeometry:
    """
    The geometry of a GeoJSON object of a request for a geometry field of the model:
    longitude and latitude of WGS 84 (RFC 7946; a `crs` member is refused), of the type of
    the field (any for a `GeometryField`) and of its dimension. A field of another SRID
    stores it transformed. Raises ValueError for anything else (422 ERR_VALIDATE at the
    attribute).

    Tags: RAG, EXPORT
    """
    if 'crs' in value:
        raise ValueError('A GeoJSON geometry is in WGS 84 (RFC 7946): the crs member is refused')
    try:
        geometry = GEOSGeometry(json.dumps(value), srid=SRID_WGS84)
    except (GDALException, GEOSException, ValueError, TypeError):
        raise ValueError('Invalid GeoJSON geometry') from None
    if field.geom_type != 'GEOMETRY' and geometry.geom_type.upper() != field.geom_type:
        raise ValueError(f'A {field.geom_type.title()} is expected, not a {geometry.geom_type}')
    if geometry.hasz != (field.dim == 3):
        raise ValueError(f'The coordinates have {field.dim} dimensions')
    if not geometry.empty:
        lon_min, lat_min, lon_max, lat_max = geometry.extent
        if lon_min < -180 or lon_max > 180 or lat_min < -90 or lat_max > 90:
            raise ValueError('Out of range: longitude -180..180, latitude -90..90')
    return geometry
