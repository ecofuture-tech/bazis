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

from django.core.management.base import BaseCommand

from bazis.core import introspect


SECTIONS = ('packages', 'settings', 'models', 'routes')


class Command(BaseCommand):
    """
    Prints the facts about the project as JSON: the installed Bazis packages with their
    manifests, the settings, the models and the API routes (see `bazis.core.introspect`).

    Tags: RAG
    """

    help = 'Prints the Bazis packages, settings, models and routes of the project as JSON.'

    def add_arguments(self, parser):
        parser.add_argument('sections', nargs='*', choices=SECTIONS, help='Default: all.')

    def handle(self, *args, sections, **options):
        from bazis.core.app import app

        info = introspect.project_info(app)
        if sections:
            info = {key: value for key, value in info.items() if key in sections}
        self.stdout.write(json.dumps(info, ensure_ascii=False, indent=2))
