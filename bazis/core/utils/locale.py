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
from importlib.util import find_spec
from pkgutil import iter_modules


def _bazis_packages() -> list[str]:
    """
    The Bazis packages present in the environment (`bazis.contrib.*`), installed as apps
    or not, by name, without importing them.
    """
    try:
        import bazis.contrib
    except ImportError:
        return []
    return sorted(
        info.name
        for info in iter_modules(bazis.contrib.__path__, 'bazis.contrib.')
        if info.ispkg
    )


def _app_dirs(app: str) -> list[str]:
    """
    The directories of an entry of INSTALLED_APPS, found without importing the app: the
    longest prefix of the entry that is a package or a module, as Django resolves it, so a
    package (`django.contrib.admin`) or the package (module) that declares an AppConfig
    (`sequences.apps.SequencesConfig`, `pkg.PkgConfig`, `pkg.apps.Config`). Only packages
    are imported (to find their submodules), as by any import of the app.
    """
    parts = app.split('.')
    found = None
    for i in range(1, len(parts) + 1):
        try:
            spec = find_spec('.'.join(parts[:i]))
        except (ImportError, ValueError):
            break
        if spec is None:
            # the rest is the name of an AppConfig class
            break
        found = spec
        if not spec.submodule_search_locations:
            # a module: the rest is the name of an AppConfig class in it
            break
    if found is None:
        return []
    if found.submodule_search_locations:
        return list(found.submodule_search_locations)
    return [os.path.dirname(found.origin)] if found.origin else []


def discover_locale_paths(base_dir: str, installed_apps: list[str]) -> list[str]:
    """
    The 'locale' directories, in the priority of their catalogs (the first path wins when
    two catalogs translate the same msgid), as Django orders the catalogs of the apps: the
    project (`<base_dir>/locale`), the installed apps in the order of INSTALLED_APPS, then
    the Bazis packages that are not installed (a project uses the abstract models of
    bazis-users without installing it) by name, under every installed app.

    The result depends only on the settings: not on the hash seed or on the modules the
    process imported before the settings, or the translated titles in the OpenAPI would
    change between processes. The global catalog of Django is not included: Django loads
    it itself, under all the others.
    """
    candidates = [os.path.join(base_dir, 'locale')]
    for app in installed_apps:
        candidates += [os.path.join(path, 'locale') for path in _app_dirs(app)]
    for package in _bazis_packages():
        candidates += [os.path.join(path, 'locale') for path in _app_dirs(package)]

    locale_paths = []
    for path in candidates:
        if path not in locale_paths and os.path.isdir(path):
            locale_paths.append(path)
    return locale_paths
