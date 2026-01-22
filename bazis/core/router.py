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
