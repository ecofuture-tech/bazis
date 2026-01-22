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


router = BazisRouter(tags=['RouteInjection'])

router.register(routes.VehicleModelRouteBase.as_router())
router.register(routes.VehicleBrandRouteBase.as_router())
router.register(routes.VehicleRouteBase.as_router())
router.register(routes.CarrierTaskRouteSet.as_router())

router_custom_response_model = BazisRouter(tags=['CustomResponseModel'])
router_custom_response_model.register(routes.VehicleCarrierTaskRouteBase.as_router())

routers_with_prefix = {
    'custom_response_model': router_custom_response_model,
}
