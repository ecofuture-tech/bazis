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
Models of the tests of the geographic filters and of the distance sorting: a point of every
kind (geography, geometry in WGS 84, geometry in another projection), one that the route
does not show, and geometries of other types.
"""

from django.contrib.gis.db import models

from bazis.core.models_abstract import JsonApiMixin


class Place(JsonApiMixin):
    name = models.CharField('Name', max_length=255)
    #: the recommended declaration: a geography point (its GiST index serves the distances)
    location = models.PointField('Location', geography=True, null=True, blank=True)
    entrance = models.PointField('Entrance', null=True, blank=True)
    mercator = models.PointField('Projected point', srid=3857, null=True, blank=True)
    secret = models.PointField('Secret point', null=True, blank=True)
    area = models.PolygonField('Area', null=True, blank=True)
    stops = models.MultiPointField('Stops', null=True, blank=True)
