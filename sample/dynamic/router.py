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


router = BazisRouter(tags=['Dynamic'])

router.register(routes.DynamicVehicleModelRouteSet.as_router())
router.register(routes.DynamicVehicleBrandRouteSet.as_router())
router.register(routes.CountryRouteSet.as_router())
router.register(routes.CarrierTaskRouteSet.as_router())
router.register(routes.DivisionJsonRouteSet.as_router())
router.register(routes.DriverRouteSet.as_router())

router_is_exists_one_relation = BazisRouter(tags=['Dynamic_IsExistsOneRelation'])
router_is_exists_one_relation.register(routes.IsExistsOneRelationRouteSet.as_router())

router_is_exists_hierarchy = BazisRouter(tags=['Dynamic_IsExistsHierarchy'])
router_is_exists_hierarchy.register(routes.IsExistsHierarchyRouteSet.as_router())

router_json_one_relation = BazisRouter(tags=['Dynamic_JsonOneRelation'])
router_json_one_relation.register(routes.JsonOneRelationRouteSet.as_router())

router_json_hierarchy = BazisRouter(tags=['Dynamic_JsonHierarchy'])
router_json_hierarchy.register(routes.JsonHierarchyRouteSet.as_router())

router_json_order_by = BazisRouter(tags=['Dynamic_JsonOrderBy'])
router_json_order_by.register(routes.JsonOrderByRouteSet.as_router())

router_json_slice = BazisRouter(tags=['Dynamic_JsonSlice'])
router_json_slice.register(routes.JsonSliceRouteSet.as_router())

router_json_many_to_many = BazisRouter(tags=['Dynamic_ManyToMany'])
router_json_many_to_many.register(routes.DriverDivisionsHiredDatesRouteSet.as_router())

router_related_one_relation_one_field = BazisRouter(tags=['Dynamic_RelatedOneRelation'])
router_related_one_relation_one_field.register(
    routes.RelatedOneRelationOneFieldRouteSet.as_router()
)

router_related_one_relation_multiple_fields = BazisRouter(tags=['Dynamic_RelatedOneRelation'])
router_related_one_relation_multiple_fields.register(
    routes.RelatedOneRelationMultipleFieldsRouteSet.as_router()
)

router_related_one_to_one = BazisRouter(tags=['Dynamic_RelatedOneToOne'])
router_related_one_to_one.register(routes.RelatedOneToOneRouteSet.as_router())

router_related_hierarchy_one_branch = BazisRouter(tags=['Dynamic_RelatedHierarchyOneBranch'])
router_related_hierarchy_one_branch.register(routes.RelatedHierarchyRouteSet.as_router())

router_subaggr = BazisRouter(tags=['Dynamic_SubAggr'])
router_subaggr.register(routes.VehicleSubaggrRouteSet.as_router())

router_context = BazisRouter(tags=['Dynamic_Context'])
router_context.register(routes.VehicleContextRouteSet.as_router())

router_errors_related_table = BazisRouter(tags=['Dynamic_ErrorsRelatedTable'])
router_errors_related_table.register(routes.ErrorsRelatedTableRouteSet.as_router())

router_errors_context = BazisRouter(tags=['Dynamic_ErrorsContext'])
router_errors_context.register(routes.ErrorsContextRouteSet.as_router())

routers_with_prefix = {
    'is_exists_one_relation': router_is_exists_one_relation,
    'is_exists_hierarchy': router_is_exists_hierarchy,
    'json_one_relation': router_json_one_relation,
    'json_hierarchy': router_json_hierarchy,
    'json_order_by': router_json_order_by,
    'json_slice': router_json_slice,
    'json_many_to_many': router_json_many_to_many,
    'related_one_relation_one_field': router_related_one_relation_one_field,
    'related_one_relation_multiple_fields': router_related_one_relation_multiple_fields,
    'related_one_to_one': router_related_one_to_one,
    'related_hierarchy_one_branch': router_related_hierarchy_one_branch,
    'subaggr': router_subaggr,
    'context': router_context,
    'errors_related_table': router_errors_related_table,
    'errors_context': router_errors_context,
}
