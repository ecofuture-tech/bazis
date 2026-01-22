from django.apps import apps

from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas.fields import SchemaField, SchemaFields

from tests.utils.context_test_route_mixin import ContextTestRouteMixin


class ChildEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ChildEntity')

    fields = {
        None: SchemaFields(
            include={
                'parent_entities': None,
            },
        ),
    }


class DependentEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.DependentEntity')


class DependentEntityNullRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.DependentEntityNull')


class ExtendedEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ExtendedEntity')


class ExtendedEntityNullRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ExtendedEntityNull')


class WithProtectedEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.WithProtectedEntity')


class ParentEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ParentEntity')

    # add fields (extended_entity, dependent_entities and calc property) to schema
    fields = {
        None: SchemaFields(
            include={
                'extended_entity': None,
                'dependent_entities': None,
                'active_children': SchemaField(source='active_children', required=False),
                'count_active_children': SchemaField(
                    source='count_active_children', required=False
                ),
                'has_inactive_children': SchemaField(
                    source='has_inactive_children', required=False
                ),
                'extended_entity_price': SchemaField(
                    source='extended_entity_price', required=False
                ),
            },
        ),
    }


class CountryRouteSet(JsonapiRouteBase):
    """Route for Country"""

    model = apps.get_model('entity.Country')


class VehicleModelRouteSet(JsonapiRouteBase):
    """Route for VehicleModel"""

    model = apps.get_model('entity.VehicleModel')


class VehicleBrandRouteSet(JsonapiRouteBase):
    """Route for VehicleBrand"""

    model = apps.get_model('entity.VehicleBrand')


class CarrierTaskRouteSet(JsonapiRouteBase):
    """Route for CarrierTask"""

    model = apps.get_model('entity.CarrierTask')


### DRIVER


class DriverRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Driver')


class DriverJsonHierarchyRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Driver')

    fields = {
        None: SchemaFields(
            include={
                'carrier_tasks_json_hierarchy': SchemaField(
                    source='carrier_tasks_json_hierarchy', required=False
                ),
            },
        ),
    }


class DriverContextRouteSet(ContextTestRouteMixin, JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Driver')

    fields = {
        None: SchemaFields(
            include={
                'carrier_tasks_context': SchemaField(
                    source='carrier_tasks_context', required=False
                ),
            },
        ),
    }


class DriverSliceRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Driver')

    fields = {
        None: SchemaFields(
            include={
                'last_trip': SchemaField(source='last_trip', required=False),
            },
        ),
    }


class DriverOrderByRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Driver')

    fields = {
        None: SchemaFields(
            include={
                'trips': SchemaField(source='trips', required=False),
            },
        ),
    }


### DIVISION


class DivisionJsonRouteSet(JsonapiRouteBase):
    """Route for Division"""

    model = apps.get_model('entity.Division')


class DivisonContextErrorRouteSet(ContextTestRouteMixin, JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Division')

    fields = {
        None: SchemaFields(
            include={
                # context that does not exist
                'drivers_list': SchemaField(source='drivers_list', required=False),
            },
        ),
    }


class DivisonFieldErrorRouteSet(JsonapiRouteBase):
    """Route for Driver"""

    model = apps.get_model('entity.Division')

    fields = {
        None: SchemaFields(
            include={
                # FieldJson - a field that does not exist
                'drivers_list1': SchemaField(source='drivers_list1', required=False),
            },
        ),
    }


### VEHICLE


class RelatedOneRelationMultipleFieldsRouteSet(JsonapiRouteBase):
    """Route for Related computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'vehicle_model_info': SchemaField(source='vehicle_model_info', required=False),
            },
        ),
    }


class VehicleRelatedRouteSet(JsonapiRouteBase):
    """Route for Related computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                # FieldRelated - vehicle_capacity_1
                'vehicle_capacity_1': SchemaField(source='vehicle_capacity_1', required=False),
                # FieldRelated - vehicle_capacity_2
                'vehicle_capacity_2': SchemaField(source='vehicle_capacity_2', required=False),
                # FieldRelated - vehicle_capacity_3
                'vehicle_capacity_3': SchemaField(source='vehicle_capacity_3', required=False),
                # FieldRelated - brand, several fields
                'brand_info': SchemaField(source='brand_info', required=False),
                # FieldRelated - brand and country, several fields from several related tables
                'brand_and_country': SchemaField(source='brand_and_country', required=False),
            },
        ),
    }


class VehicleJsonRouteSet(JsonapiRouteBase):
    """Route for Json computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                # FieldJson - list of trips
                'carrier_task_list': SchemaField(source='carrier_task_list', required=False),
            },
        ),
    }


### IS EXISTS


class HasActiveTripRouteSet(JsonapiRouteBase):
    """Route for FieldIsExists computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'has_active_trip': SchemaField(source='has_active_trip', required=False),
            },
        ),
    }


class VehicleExistsJoinRouteSet(JsonapiRouteBase):
    """Route for FieldIsExists computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'has_active_trip_with_phone_join': SchemaField(
                    source='has_active_trip_with_phone_join', required=False
                ),
            },
        ),
    }


class VehicleExistsSubQueryRouteSet(JsonapiRouteBase):
    """Route for FieldIsExists computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'has_active_trip_with_phone_subquery': SchemaField(
                    source='has_active_trip_with_phone_subquery', required=False
                ),
            },
        ),
    }


### AGGR SUBAGGR


class VehicleAggrRouteSet(JsonapiRouteBase):
    """Route for Aggr computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'current_tasks_waste_weight_aggr': SchemaField(
                    source='current_tasks_waste_weight_aggr', required=False
                ),
            },
        ),
    }


class VehicleSubaggrRouteSet(JsonapiRouteBase):
    """Route for Subaggr computed fields"""

    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                'current_tasks_waste_weight_subaggr': SchemaField(
                    source='current_tasks_waste_weight_subaggr', required=False
                ),
            },
        ),
    }
