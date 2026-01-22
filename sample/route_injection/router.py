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
