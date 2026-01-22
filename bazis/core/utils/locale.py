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


def discover_locale_paths(base_dir: str) -> list[str]:
    """
    Discovers and returns a list of paths to 'locale' directories within the given
    base directory and all imported packages. It first checks for a 'locale'
    directory in the base directory, then iterates through all imported packages to
    find their 'locale' directories.
    """
    locale_paths = []

    project_locale_path = os.path.join(base_dir, 'locale')
    if os.path.isdir(project_locale_path):
        locale_paths.append(project_locale_path)

    for package in set(sys.modules.keys()) | get_apps_with_locals('bazis'):
        try:
            module = import_module(package)
            package_path = Path(module.__file__).parent
            locale_path = package_path / 'locale'
            locale_path_str = str(locale_path)

            if locale_path.is_dir() and locale_path_str not in locale_paths:
                locale_paths.append(locale_path_str)
        except (ModuleNotFoundError, AttributeError, TypeError):
            continue

    return locale_paths
