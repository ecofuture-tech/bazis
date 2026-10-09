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

from django.apps import apps
from django.db.backends.signals import connection_created

from bazis.core.utils.apps import BaseConfig


class BazisCoreConfig(BaseConfig):
    """
    Configuration class for the 'bazis.core' application, providing application-
    specific settings and metadata.

    Tags: RAG, EXPORT
    """

    name = 'bazis.core'
    verbose_name = 'Bazis core'

    def ready(self):
        super().ready()
        from bazis.core import checks  # noqa: F401  registers the system checks
        from bazis.core.item_validation import connect_m2m
        from bazis.core.utils.orm import close_with_thread

        connect_m2m(apps.get_models())
        connection_created.connect(close_with_thread, dispatch_uid='bazis.core.close_with_thread')
