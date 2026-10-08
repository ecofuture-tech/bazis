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

import os
import sys
from importlib import import_module
from pathlib import Path

from bazis.core.utils.imp import walk_packages_excluding


def get_apps_with_locals(package_name) -> set[str]:
    registered_packages = set()

    try:
        # Import the main package
        package = import_module(package_name)

        # If the package has no __path__ attribute, it is not a package
        if not hasattr(package, '__path__'):
            return registered_packages

        # Check whether the current package has a locale folder
        if package.__file__:
            package_path = os.path.dirname(package.__file__)
            locale_path = os.path.join(package_path, 'locale')

            if os.path.isdir(locale_path):
                # Add the package to the list of found ones
                registered_packages.add(package_name)
        # Recursively traverse all subpackages
        for _, name, is_pkg in walk_packages_excluding(
            package.__path__, package.__name__ + '.', exclude={'schemas', 'jsonapi'}
        ):
            if is_pkg:  # Process only packages, not modules
                # Recursive call for the subpackage
                subpackage_results = get_apps_with_locals(name)
                registered_packages.update(subpackage_results)

    except (ImportError, AttributeError) as e:
        print(f'Error while processing package {package_name}: {e}')

    return registered_packages


def _app_rank(package: str, installed_apps: list[str]) -> int:
    """
    The position of the package among the installed apps: the app itself, an AppConfig
    path inside it (`sequences.apps.SequencesConfig`) or a subpackage of an app. A package
    that is not an installed app comes after all of them.
    """
    for i, app in enumerate(installed_apps):
        if app == package or app.startswith(f'{package}.') or package.startswith(f'{app}.'):
            return i
    return len(installed_apps)


def discover_locale_paths(base_dir: str, installed_apps: list[str]) -> list[str]:
    """
    Discovers the 'locale' directories of the project (`<base_dir>/locale`), of the
    imported packages and of all Bazis packages (also the ones whose code a project uses
    without installing them as apps, such as the abstract models of bazis-users).

    The order is the priority of the catalogs (the first path wins when two catalogs
    translate the same msgid), as Django orders the catalogs of the apps: the project, then
    the installed apps in the order of INSTALLED_APPS, then the other packages by name.
    It never depends on the process (the hash seed), or the translated titles in the
    OpenAPI would change between processes. The global catalog of Django is not included:
    Django loads it itself, under all the others.
    """
    import django

    django_locale_path = str(Path(django.__file__).parent / 'conf' / 'locale')

    locale_paths = []

    project_locale_path = os.path.join(base_dir, 'locale')
    if os.path.isdir(project_locale_path):
        locale_paths.append(project_locale_path)

    # the locale directory of a package, by its path: the package that owns it
    package_paths: dict[str, str] = {}
    for name in sorted(set(sys.modules) | get_apps_with_locals('bazis')):
        try:
            module = import_module(name)
            package = module.__package__ or name
            locale_path = str(Path(module.__file__).parent / 'locale')
        except (ModuleNotFoundError, AttributeError, TypeError):
            continue
        if (
            locale_path not in package_paths
            and locale_path not in locale_paths
            and locale_path != django_locale_path
            and os.path.isdir(locale_path)
        ):
            package_paths[locale_path] = package

    locale_paths.extend(
        sorted(
            package_paths,
            key=lambda path: (_app_rank(package_paths[path], installed_apps), package_paths[path]),
        )
    )
    return locale_paths
