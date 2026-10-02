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

from django.core.management.base import BaseCommand, CommandError

from bazis.core import introspect


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
        try:
            from bazis.core.app import app  # noqa: F401
        except Exception as err:
            if as_json:
                problem = {
                    'id': 'bazis.app',
                    'level': 'critical',
                    'message': f'The application cannot be loaded: {err!r}',
                    'hint': None,
                    'object': None,
                }
                self.stdout.write(json.dumps([problem], ensure_ascii=False, indent=2))
            raise CommandError(f'The application cannot be loaded: {err!r}') from err

        messages = introspect.check_messages(deploy)

        if as_json:
            self.stdout.write(json.dumps(messages, ensure_ascii=False, indent=2))
        else:
            for message in messages:
                self.stdout.write(_message_text(message))
            self.stdout.write(f'{len(messages)} issue(s).')

        if any(m['level'] in ('error', 'critical') for m in messages):
            raise CommandError('The project has errors.')


def _message_text(message: dict) -> str:
    text = f'{message["object"] or "?"}: ({message["id"]}) {message["message"]}'
    if message['hint']:
        text += f'\n\tHINT: {message["hint"]}'
    return text
