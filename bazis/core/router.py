import importlib
import logging

from django.conf import settings

from bazis.core.routing import BazisRouter


LOG = logging.getLogger()


if BAZIS_ROUTER_MODULE := getattr(settings, 'BAZIS_ROUTER_MODULE', None):
    router_module = importlib.import_module(BAZIS_ROUTER_MODULE)
    router = router_module.router
else:
    LOG.info('Custom router not found. Default will be created')
    router = BazisRouter()
