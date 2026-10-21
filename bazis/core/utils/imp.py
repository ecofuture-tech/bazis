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
from collections.abc import Generator
from importlib import import_module
from pkgutil import iter_modules


def import_class(name: str, base_module=None):
    """
    Dynamically imports class by dotted path string.

    Args:
        name: Class path (e.g., 'myapp.models.User') or class name
        base_module: Base module prefix if name is unqualified

    Examples:
        import_class('myapp.models.User')
        import_class('User', base_module='myapp.models')

    Returns: Class object

    Tags: RAG, EXPORT
    """
    if '.' not in name:
        name = f'{base_module}.{name}'
    module_path, class_name = name.rsplit('.', 1)
    module = import_module(module_path)
    return getattr(module, class_name)


def pkg_load(pkg):
    """
    Eagerly loads all Python modules in package directory.
    Imports every .py file in package's __path__[0].

    Used for auto-discovery patterns (e.g., loading all models/views).

    Args:
        pkg: Package object with __path__ attribute

    Tags: RAG, EXPORT
    """
    for path in os.listdir(pkg.__path__[0]):
        f_name, ext = os.path.splitext(path)
        if ext == '.py':
            import_module(f'{pkg.__name__}.{f_name}')


def walk_packages_excluding(path, prefix='', exclude: set[str] = None) -> Generator:
    """
    Custom pkgutil.walk_packages with exclusion filter.
    Recursively discovers modules while excluding by name substring. The packages are
    not imported: the search path of a subpackage is taken from the spec of its finder,
    so the __init__ of a package nobody asked for is never executed.

    Args:
        path: Package path(s) to search
        prefix: Module name prefix (e.g., 'mypkg.')
        exclude: Set of substrings to exclude from module names

    Yields:
        ModuleInfo tuples (finder, name, ispkg)

    Usage:
        for info in walk_packages_excluding(
            myapp.__path__,
            prefix='myapp.',
            exclude={'tests', 'migrations'}
        ):
            print(info.name)

    Tags: RAG, EXPORT
    """
    exclude = exclude or set()
    seen_paths = set()

    def seen(p):
        """Tracks visited paths to prevent duplicates."""
        if p in seen_paths:
            return True
        seen_paths.add(p)
        return False

    for info in iter_modules(path, prefix):
        # Skip modules containing any exclusion substring
        if any(skip in info.name for skip in exclude):
            continue

        yield info

        if info.ispkg:
            spec = info.module_finder.find_spec(info.name)
            sub_path = [p for p in (spec.submodule_search_locations or []) if not seen(p)]
            yield from walk_packages_excluding(sub_path, info.name + '.', exclude=exclude)


def get_modules_from_pkg(pkg, module_name: str, first_level_only: bool = False):
    """
    Discovers and yields the modules of a package named `module_name`, imported once
    (a module imported before is the one of sys.modules). Only the matching modules, with
    the packages they sit in, are imported; the other subpackages are not.

    Args:
        pkg: Package or module to search
        module_name: Module name to match (e.g., 'conf', 'models')
        first_level_only: If True, only search immediate children (no recursion)

    Yields:
        Loaded module objects matching the name

    Exclusions: Automatically excludes 'schemas' and 'jsonapi' packages

    Examples:
        # Find all conf modules
        for mod in get_modules_from_pkg(myapp, 'conf'):
            print(mod)

        # Find only top-level models
        for mod in get_modules_from_pkg(myapp, 'models', first_level_only=True):
            print(mod)

    Tags: RAG, EXPORT
    """
    # Handle single module (not package)
    if not hasattr(pkg, '__path__'):
        if pkg.__name__.rsplit('.', 1)[-1] == module_name:
            yield pkg
        return

    # Walk package tree
    for _finder, name, _is_pkg in walk_packages_excluding(
        pkg.__path__, prefix=pkg.__name__ + '.', exclude={'schemas', 'jsonapi'}
    ):
        # Skip nested modules if first_level_only
        if first_level_only and '.' in name[len(pkg.__name__) + 1 :]:
            continue

        if name.rsplit('.', 1)[-1] == module_name:
            yield import_module(name)
