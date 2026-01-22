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

from django.apps import apps

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas.fields import SchemaField, SchemaFields

from tests.utils.context_test_route_mixin import ContextTestRouteMixin


class CountryRouteSet(JsonapiRouteBase):
    """Route for Country"""

    model = apps.get_model('dynamic.Country')


class DynamicVehicleBrandRouteSet(JsonapiRouteBase):
    """Route for VehicleBrand"""

    model = apps.get_model('dynamic.VehicleBrand')


class DynamicVehicleModelRouteSet(JsonapiRouteBase):
    """Route for VehicleModel"""

    model = apps.get_model('dynamic.VehicleModel')


class CarrierTaskRouteSet(JsonapiRouteBase):
    """Route for CarrierTask"""

    model = apps.get_model('dynamic.CarrierTask')


### DRIVER


class DriverRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('dynamic.Driver')


class DriverDivisionsHiredDatesRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('dynamic.Driver')

    fields = {
        None: SchemaFields(
            include={
                'divisions_hired_info': SchemaField(source='divisions_hired_info', required=False),
            },
        ),
    }


### DIVISION


class DivisionJsonRouteSet(JsonapiRouteBase):
    """Route for Division"""

    model = apps.get_model('dynamic.Division')


class ErrorsContextRouteSet(ContextTestRouteMixin, JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('dynamic.Division')

    fields = {
        None: SchemaFields(
            include={
                # context that does not exist
                'drivers_list': SchemaField(source='drivers_list', required=False),
            },
        ),
    }


class ErrorsRelatedTableRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('dynamic.Division')

    fields = {
        None: SchemaFields(
            include={
                # FieldJson - field that does not exist
                'drivers_list1': SchemaField(source='drivers_list1', required=False),
            },
        ),
    }


# VEHICLE


class RelatedOneRelationOneFieldRouteSet(JsonapiRouteBase):
    """Route for Related computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'vehicle_capacity': SchemaField(source='vehicle_capacity', required=False),
            },
        ),
    }


class RelatedOneRelationMultipleFieldsRouteSet(JsonapiRouteBase):
    """Route for Related computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'vehicle_model_info': SchemaField(source='vehicle_model_info', required=False),
            },
        ),
    }


class RelatedOneToOneRouteSet(JsonapiRouteBase):
    """Route for Related computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'vehicle_assemble_info': SchemaField(
                    source='vehicle_assemble_info', required=False
                ),
            },
        ),
    }


class RelatedHierarchyRouteSet(JsonapiRouteBase):
    """Route for Related computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'brand_info': SchemaField(source='brand_info', required=False),
            },
        ),
    }


class VehicleSubaggrRouteSet(JsonapiRouteBase):
    """Route for Subaggr computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'finished_tasks_waste_weight': SchemaField(
                    source='finished_tasks_waste_weight', required=False
                ),
            },
        ),
    }


class JsonOneRelationRouteSet(JsonapiRouteBase):
    """Route for Json computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'carrier_task_list': SchemaField(source='carrier_task_list', required=False),
            },
        ),
    }


class JsonHierarchyRouteSet(JsonapiRouteBase):
    """Route for Json computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'carrier_tasks_json_hierarchy': SchemaField(
                    source='carrier_tasks_json_hierarchy', required=False
                ),
            },
        ),
    }


class JsonSliceRouteSet(JsonapiRouteBase):
    """Route for Json computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'last_trip': SchemaField(source='last_trip', required=False),
            },
        ),
    }


class JsonOrderByRouteSet(JsonapiRouteBase):
    """Route for Json computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'active_trips': SchemaField(source='active_trips', required=False),
            },
        ),
    }


### IS EXISTS


class IsExistsOneRelationRouteSet(JsonapiRouteBase):
    """Route for FieldIsExists computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'has_active_trip': SchemaField(source='has_active_trip', required=False),
            },
        ),
    }


class IsExistsHierarchyRouteSet(JsonapiRouteBase):
    """Route for FieldIsExists computed fields"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'has_active_trip_with_phone': SchemaField(
                    source='has_active_trip_with_phone', required=False
                ),
            },
        ),
    }


class VehicleContextRouteSet(ContextTestRouteMixin, JsonapiRouteBase):
    """Route for Vehicle"""

    model = apps.get_model('dynamic.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'carrier_tasks_context': SchemaField(
                    source='carrier_tasks_context', required=False
                ),
            },
        ),
    }
