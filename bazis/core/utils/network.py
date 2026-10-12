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

"""
Deprecated: the health check server of the background processes is
`bazis.contrib.bg.network` (bazis-bg 2.6), which declares the dependency aiohttp. To be
removed in Bazis 3.0.
"""

import warnings

from bazis.contrib.bg.network import check_port, healthcheck_server  # noqa: F401


warnings.warn(
    'bazis.core.utils.network is deprecated (removed in Bazis 3.0): '
    'import bazis.contrib.bg.network of bazis-bg',
    DeprecationWarning,
    stacklevel=2,
)
