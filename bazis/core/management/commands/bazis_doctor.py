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
from django.db import DEFAULT_DB_ALIAS, connections

from bazis.core import introspect


class Command(BaseCommand):
    """
    Runs the Django system checks of the project, including the checks of the Bazis
    packages that need the API routes (the application is loaded first) and the database
    checks, which compare the project with its database (`--database`, by default the
    database `default` when it can be reached; otherwise they are skipped with the info
    `bazis.database`). With `--json` prints the messages for tools and AI agents. Fails if
    there is an error.

    Tags: RAG
    """

    help = 'Checks the project for errors and risky settings of the Bazis packages.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--deploy', action='store_true', help='Also run the deployment checks.')
        parser.add_argument(
            '--database',
            action='append',
            dest='databases',
            help=(
                'Run the database checks against this database (repeatable). Default: the '
                'database "default" when it can be reached; one given that cannot is an error.'
            ),
        )
        parser.add_argument(
            '--json', action='store_true', dest='as_json', help='Print the messages as JSON.'
        )

    def handle(self, *args, deploy, databases, as_json, **options):
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

        reachable, messages = _reachable(databases)
        messages += introspect.check_messages(deploy, reachable)

        if as_json:
            self.stdout.write(json.dumps(messages, ensure_ascii=False, indent=2))
        else:
            for message in messages:
                self.stdout.write(_message_text(message))
            self.stdout.write(f'{len(messages)} issue(s).')

        if any(m['level'] in ('error', 'critical') for m in messages):
            raise CommandError('The project has errors.')


def _reachable(databases: list[str] | None) -> tuple[list[str], list[dict]]:
    """
    The databases the database checks run against, and a message for each one that cannot
    be reached: an error for one given with `--database`, an info for `default` checked by
    default (a project checked without its database, such as before it is created).
    """
    reachable, messages = [], []
    for alias in databases or [DEFAULT_DB_ALIAS]:
        try:
            connections[alias].ensure_connection()
        except Exception as err:
            messages.append(
                {
                    'id': 'bazis.database',
                    'level': 'error' if databases else 'info',
                    'message': (
                        f'The database {alias} cannot be reached, its database checks are '
                        f'skipped: {" ".join(str(err).split()) or type(err).__name__}'
                    ),
                    'hint': (
                        'The database checks compare the project with its database (such as '
                        'the declared roles and workflows); run them with the database up.'
                    ),
                    'object': None,
                }
            )
        else:
            reachable.append(alias)
    return reachable, messages


def _message_text(message: dict) -> str:
    text = f'{message["object"] or "?"}: ({message["id"]}) {message["message"]}'
    if message['hint']:
        text += f'\n\tHINT: {message["hint"]}'
    return text
