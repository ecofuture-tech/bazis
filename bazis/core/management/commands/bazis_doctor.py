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

from django.core import checks
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """
    Runs the Django system checks of the project, including the checks of the Bazis
    packages that need the API routes (the application is loaded first). With `--json`
    prints the messages for tools and AI agents. Fails if there is an error.

    Tags: RAG
    """

    help = 'Checks the project for errors and risky settings of the Bazis packages.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--deploy', action='store_true', help='Also run the deployment checks.')
        parser.add_argument(
            '--json', action='store_true', dest='as_json', help='Print the messages as JSON.'
        )

    def handle(self, *args, deploy, as_json, **options):
        # the checks of the routes need the application
        from bazis.core.app import app  # noqa: F401

        messages = checks.run_checks(include_deployment_checks=deploy)
        messages = [m for m in messages if not m.is_silenced()]

        if as_json:
            self.stdout.write(
                json.dumps([_message_dict(m) for m in messages], ensure_ascii=False, indent=2)
            )
        else:
            for message in messages:
                self.stdout.write(str(message))
            self.stdout.write(f'{len(messages)} issue(s).')

        if any(m.level >= checks.ERROR for m in messages):
            raise CommandError('The project has errors.')


def _message_dict(message: checks.CheckMessage) -> dict:
    return {
        'id': message.id,
        'level': _level_name(message.level),
        'message': message.msg,
        'hint': message.hint,
        'object': str(message.obj) if message.obj is not None else None,
    }


def _level_name(level: int) -> str:
    for name in ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'):
        if level >= getattr(checks, name):
            return name.lower()
    return 'debug'
