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
