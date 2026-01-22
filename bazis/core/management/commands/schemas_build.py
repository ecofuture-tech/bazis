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
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

import psutil


class Command(BaseCommand):
    """
    The command creates OpenAPI schemas for all supported languages
    by running a separate process for each language.

    Tags: RAG
    """

    def handle(self, **kwargs):
        envs_common = os.environ.copy()

        for lang_code, lang_name in settings.LANGUAGES:
            langs = json.dumps(
                sorted(settings.LANGUAGES, key=lambda x: x[0] != lang_code), ensure_ascii=False
            )

            envs = {**envs_common, **{'BS_LANGUAGE_CODE': lang_code, 'BS_LANGUAGES': langs}}

            print(f'Building schemas for {lang_name} ({lang_code})')

            psutil.Popen([sys.executable, 'manage.py', 'schemas_build_lang'], env=envs)

        psutil.wait_procs(psutil.Process().children())
