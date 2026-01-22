from bazis.core.routing import BazisRouter

from . import routes


router = BazisRouter(tags=['SparseFieldsets'])

router.register(routes.PeopleRouteSet.as_router())
router.register(routes.CategoryRouteSet.as_router())
router.register(routes.ArticleRouteSet.as_router())
