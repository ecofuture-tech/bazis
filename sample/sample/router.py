from bazis.core.routing import BazisRouter


router = BazisRouter(prefix='/api/v1')

router.register('entity.router')
router.register('dynamic.router')
router.register('route_injection.router')
router.register('sparse_fieldsets.router')
