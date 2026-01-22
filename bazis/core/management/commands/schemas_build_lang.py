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

import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import get_language

import jsonref


def get_definitions(schema):
    if settings.BAZIS_SCHEMA_WITHOUT_REF:
        schema = jsonref.replace_refs(schema)

    definitions = schema['components']['schemas']

    if settings.BAZIS_SCHEMA_WITHOUT_REF:
        return {key: it for key, it in definitions.items() if not key.startswith('_')}
    else:
        return definitions


class Command(BaseCommand):
    """
    The command creates OpenAPI schemas for the current language
    and saves them to a JSON file in the static directory.

    Tags: RAG
    """

    def handle(self, **kwargs):
        from bazis.core.app import app
        from bazis.core.router import router
        from bazis.core.routing import BazisRoute

        os.makedirs(settings.STATIC_ROOT, exist_ok=True)

        router.routes_cast(BazisRoute)
        app.include_router(router)

        with open(os.path.join(settings.STATIC_ROOT, f'schemas_{get_language()}.json'), 'w') as fp:
            json.dump(get_definitions(app.openapi()), fp, ensure_ascii=False)
