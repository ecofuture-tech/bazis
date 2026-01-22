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

from bazis.core.routing import BazisRouter

from . import routes


router = BazisRouter(tags=['Entity'])

router.register(routes.ChildEntityRouteSet.as_router())
router.register(routes.DependentEntityRouteSet.as_router())
router.register(routes.DependentEntityNullRouteSet.as_router())
router.register(routes.ExtendedEntityRouteSet.as_router())
router.register(routes.ExtendedEntityNullRouteSet.as_router())
router.register(routes.ParentEntityRouteSet.as_router())
router.register(routes.WithProtectedEntityRouteSet.as_router())

router.register(routes.VehicleModelRouteSet.as_router())
router.register(routes.VehicleBrandRouteSet.as_router())
router.register(routes.CountryRouteSet.as_router())
router.register(routes.CarrierTaskRouteSet.as_router())
router.register(routes.DivisionJsonRouteSet.as_router())
router.register(routes.DriverRouteSet.as_router())

router_context = BazisRouter(tags=['Context'])
router_context.register(routes.DriverContextRouteSet.as_router())
router_context.register(routes.DivisonContextErrorRouteSet.as_router())

router_json = BazisRouter(tags=['Json'])
router_json.register(routes.DriverJsonHierarchyRouteSet.as_router())
router_json.register(routes.VehicleJsonRouteSet.as_router())
router_json.register(routes.DivisonFieldErrorRouteSet.as_router())

router_related_one_relation_multiple_fields = BazisRouter(
    tags=['Related_One_Relation_Multiple_Fields']
)
router_related_one_relation_multiple_fields.register(
    routes.RelatedOneRelationMultipleFieldsRouteSet.as_router()
)

router_related = BazisRouter(tags=['Related'])
router_related.register(routes.VehicleRelatedRouteSet.as_router())

router_aggr = BazisRouter(tags=['Aggr'])
router_aggr.register(routes.VehicleAggrRouteSet.as_router())

router_subaggr = BazisRouter(tags=['SubAggr'])
router_subaggr.register(routes.VehicleSubaggrRouteSet.as_router())

router_has_active_trip = BazisRouter(tags=['HasActiveTrip'])
router_has_active_trip.register(routes.HasActiveTripRouteSet.as_router())

router_is_exists_join = BazisRouter(tags=['IsExistsJoin'])
router_is_exists_join.register(routes.VehicleExistsJoinRouteSet.as_router())

router_is_exists_subquery = BazisRouter(tags=['IsExistsSubquery'])
router_is_exists_subquery.register(routes.VehicleExistsSubQueryRouteSet.as_router())

router_slice = BazisRouter(tags=['Slice'])
router_slice.register(routes.DriverSliceRouteSet.as_router())

router_order_by = BazisRouter(tags=['OrderBy'])
router_order_by.register(routes.DriverOrderByRouteSet.as_router())

routers_with_prefix = {
    'context': router_context,
    'json': router_json,
    'related_one_relation_multiple_fields': router_related_one_relation_multiple_fields,
    'related': router_related,
    'aggr': router_aggr,
    'subaggr': router_subaggr,
    'has_active_trip': router_has_active_trip,
    'is_exists_join': router_is_exists_join,
    'is_exists_subquery': router_is_exists_subquery,
    'slice': router_slice,
    'order_by': router_order_by,
}
