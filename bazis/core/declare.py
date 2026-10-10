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
The helpers of the declarations in the code that `migrate` applies to the database: the
roles of bazis-permit (`<app>/roles.py`), the workflows of bazis-statusy
(`<app>/workflow.py`), the schedules of bazis-bg (`<app>/schedules.py`).

A package finds the declarations of the applications with `discover`, applies them in its
`post_migrate` receiver with `apply_after_migrate` (once all the migrations of the project
are applied), in a transaction that holds `lock` (concurrent `migrate` runs apply them one
after the other). The objects of a model with a unique `slug` and a `managed` flag are
brought to their declaration by `ManagedSync`: created, updated or taken over (an existing
object of the slug that is not `managed`, with a warning); `managed_orphans` are the
managed ones no longer declared. What happens to them is the policy of each package: the
roles and groups of bazis-permit (and the transits of bazis-statusy) are kept as they are
and reported by a database check, as their removal would revoke permissions or history;
the periodic tasks of bazis-bg are disabled and unmarked (ordinary ones the admin may
enable again), as an enabled one would keep running.
`ManagedAdminMixin` (`bazis.core.admin_abstract`) shows the declared objects read-only.
"""

import logging
import sys
from importlib import import_module

from django.apps import apps
from django.db import DEFAULT_DB_ALIAS, connections, router
from django.db.migrations.executor import MigrationExecutor
from django.utils.module_loading import module_has_submodule


logger = logging.getLogger(__name__)

#: the key of the PostgreSQL advisory lock that serializes the application of the
#: declarations of all the packages by concurrent `migrate` runs
ADVISORY_LOCK = 0x62617A6973  # 'bazis'


def discover(module: str, attribute: str) -> list[tuple[str, object]]:
    """
    The items of the list `attribute` of the modules `<app>.<module>` of the installed
    applications, with the name of their module. A module without the attribute is not a
    declaration and is skipped.
    """
    found = []
    for app_config in apps.get_app_configs():
        if module_has_submodule(app_config.module, module):
            declared = import_module(f'{app_config.name}.{module}')
            found.extend((declared.__name__, it) for it in getattr(declared, attribute, ()))
    return found


def lock(using: str = DEFAULT_DB_ALIAS) -> None:
    """
    In a transaction, waits for the other applications of the declarations (another
    `migrate` of the same database) to end: a PostgreSQL advisory lock released at the end
    of the transaction. Other databases have none.
    """
    connection = connections[using]
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [ADVISORY_LOCK])


def migrations_complete(using: str = DEFAULT_DB_ALIAS) -> bool:
    """
    Whether the database has all the migrations of the project: the declarations are
    applied only then (a `migrate` to an earlier migration skips them).
    """
    executor = MigrationExecutor(connections[using])
    return not executor.migration_plan(executor.loader.graph.leaf_nodes())


def apply_after_migrate(
    apply, model: str, what: str, using: str = DEFAULT_DB_ALIAS, verbosity: int = 1, stdout=None
) -> list[str] | None:
    """
    The work of the `post_migrate` receiver of a package (the signal is also sent by
    `flush`): `apply(using)` applies the declarations of the package once the migrations of
    the project are all applied, if the model `model` (an `app_label.Model`) is migrated in
    the database. Writes the number of changes (`what`: "roles"), each one with verbosity
    2, and returns them; None when nothing is applied.
    """
    if not router.allow_migrate_model(using, apps.get_model(model)):
        return None
    if not migrations_complete(using):
        logger.info('Not all the migrations are applied: the declared %s are not applied.', what)
        return None
    changes = apply(using)
    stdout = stdout or sys.stdout
    if changes and verbosity >= 1:
        stdout.write(f'  Applied the declared {what}: {len(changes)} change(s)\n')
    if verbosity >= 2:
        for change in changes:
            stdout.write(f'    {change}\n')
    return changes


def managed_orphans(model, slugs, using: str = DEFAULT_DB_ALIAS):
    """
    The managed objects of the model (a unique `slug`, a `managed` flag) whose slug is not
    one of the declared `slugs`, by slug.
    """
    return model.objects.using(using).filter(managed=True).exclude(slug__in=slugs).order_by('slug')


class ManagedSync:
    """
    Brings the objects of models with a unique `slug` and a `managed` flag to their
    declarations, or only lists the changes (`dry_run`), in `changes`.
    """

    def __init__(self, using: str = DEFAULT_DB_ALIAS, dry_run: bool = False):
        self.using = using
        self.dry_run = dry_run
        self.changes: list[str] = []

    def object(self, model, slug: str, values: dict) -> tuple[object, list[str]]:
        """
        The managed object of the slug with these field values, and the fields changed:
        created (all the fields), updated, or taken over when it exists and is not managed
        (with a warning; `managed` is one of the fields changed).
        """
        label = f'{model._meta.model_name} {slug}'
        obj = model.objects.using(self.using).filter(slug=slug).first()
        if obj is None:
            self.changes.append(f'{label}: created')
            obj = model(slug=slug, managed=True, **values)
            if not self.dry_run:
                obj.save(using=self.using)
            return obj, [*values, 'managed']
        changed = [name for name, value in values.items() if getattr(obj, name) != value]
        if not obj.managed:
            if not self.dry_run:
                logger.warning(
                    'The %s exists and is not managed by the code: the declaration takes it over.', label
                )
            changed.append('managed')
            obj.managed = True
        if changed:
            self.changes.append(f'{label}: {", ".join(changed)} changed')
            for name in changed:
                if name in values:
                    setattr(obj, name, values[name])
            if not self.dry_run:
                obj.save(using=self.using, update_fields=changed)
        return obj, changed
