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
Facts about a Bazis project for tools and AI agents: the installed Bazis packages with
their manifests, the settings, the models and the API routes.

The data is plain JSON-serializable dictionaries (see the `bazis_introspect` management
command). Everything is read from the running project, not from documentation.

Tags: RAG, EXPORT
"""

import inspect
import sys
import tomllib
from collections.abc import Iterator, Sequence
from importlib import import_module, metadata, resources
from importlib.util import find_spec
from pathlib import Path

from django.apps import apps
from django.conf import settings

from fastapi.routing import APIRoute

from starlette.routing import BaseRoute


MANIFEST_FILE = 'bazis_manifest.toml'
AGENTS_FILE = 'AGENTS.md'

#: substrings of setting names whose values are not shown
SECRET_MARKERS = ('SECRET', 'PASSWORD', 'TOKEN', 'PRIVATE')


def package_module(dist_name: str) -> str | None:
    """
    The module of a Bazis distribution: `bazis` -> `bazis.core`,
    `bazis-users` -> `bazis.contrib.users`, `bazis-test-utils` -> `bazis_test_utils`.
    """
    candidates = ['bazis.core'] if dist_name == 'bazis' else [
        'bazis.contrib.' + dist_name.removeprefix('bazis-').replace('-', '_'),
        dist_name.replace('-', '_'),
    ]
    for module in candidates:
        try:
            if find_spec(module) is not None:
                return module
        except ModuleNotFoundError:
            continue
    return None


def read_manifest(module: str) -> dict | None:
    """
    The `bazis_manifest.toml` of a package module, or None if the package has none.
    """
    path = resources.files(module) / MANIFEST_FILE
    if not path.is_file():
        return None
    return tomllib.loads(path.read_text(encoding='utf-8'))


def validate_manifest(module: str) -> list[str]:
    """
    The problems of the manifest of a package module: a missing name, an `import` path of
    an extension point that does not import, a `check` id of a pitfall that the package
    code does not contain. Each package runs it in its tests, so that the manifest cannot
    drift from the code.
    """
    manifest = read_manifest(module)
    if manifest is None:
        return [f'{module}: {MANIFEST_FILE} not found']

    problems = []
    if not manifest.get('package', {}).get('name'):
        problems.append('[package] name is missing')

    for point in manifest.get('extension_points', []):
        path = point.get('import', '')
        module_path, _, attr = path.rpartition('.')
        try:
            getattr(import_module(module_path), attr)
        except (ImportError, AttributeError, ValueError):
            problems.append(f'extension point {point.get("name")!r}: cannot import {path!r}')

    sources = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in Path(str(resources.files(module))).rglob('*.py')
    )
    for pitfall in manifest.get('pitfalls', []):
        if (check := pitfall.get('check')) and f"'{check}'" not in sources:
            problems.append(f'pitfall check {check!r} is not defined in {module}')
    return problems


def packages() -> list[dict]:
    """
    The installed Bazis distributions with their versions, modules and manifests.
    """
    result = {}
    for dist in metadata.distributions():
        name = (dist.metadata['Name'] or '').lower()
        if name != 'bazis' and not name.startswith('bazis-'):
            continue
        module = package_module(name)
        has_agents = module is not None and (resources.files(module) / AGENTS_FILE).is_file()
        result[name] = {
            'name': name,
            'version': dist.version,
            'module': module,
            'manifest': read_manifest(module) if module else None,
            'agents_md': f'{module}/{AGENTS_FILE}' if has_agents else None,
        }
    return [result[name] for name in sorted(result)]


def _is_secret(name: str) -> bool:
    return any(marker in name for marker in SECRET_MARKERS) or name.endswith('_KEY')


def settings_info() -> list[dict]:
    """
    The settings declared by the `conf.py` modules of the core, the packages and the
    project. Secret values are hidden; dynamic settings (stored in the database) are
    listed without a value.
    """
    from bazis.core.configure import conf_modules

    result = {}
    for conf in conf_modules():
        conf_settings = getattr(conf, 'Settings', None)
        if conf_settings is None:
            continue
        for name in inspect.get_annotations(conf_settings):
            field = conf_settings.model_fields.get(name)
            if field is None or name in result:
                continue
            dynamic = bool((field.json_schema_extra or {}).get('dynamic'))
            item = {
                'name': name,
                'module': conf.__name__,
                'title': str(field.title) if field.title else None,
                'type': getattr(field.annotation, '__name__', None) or str(field.annotation),
                'dynamic': dynamic,
            }
            if not dynamic:
                value = getattr(settings, name, None)
                item['value'] = '***' if value and _is_secret(name) else _jsonable(value)
            result[name] = item
    return [result[name] for name in sorted(result)]


def _jsonable(value):
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    return str(value)


def models_info() -> list[dict]:
    """
    The JSON:API models (subclasses of `JsonApiMixin`) with their attributes and relations.
    """
    from bazis.core.models_abstract import JsonApiMixin

    result = []
    for model in apps.get_models():
        if not issubclass(model, JsonApiMixin):
            continue
        info = model.get_fields_info()
        result.append(
            {
                'model': model._meta.label,
                'resource': model.get_resource_label(),
                'pk': info.pk.name,
                'attributes': sorted(info.attributes),
                'relations': [
                    {
                        'name': name,
                        'model': rel.related_model._meta.label,
                        'to_many': rel.to_many,
                        'reverse': rel.reverse,
                    }
                    for name, rel in sorted(info.relations.items())
                ],
            }
        )
    return sorted(result, key=lambda it: it['model'])


def iter_routes_with_paths(routes: Sequence[BaseRoute], prefix: str = '') -> Iterator[tuple]:
    """
    Yields `(full path, APIRoute)` for the declared API routes, with the prefixes of the
    included routers.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif (router := getattr(route, 'original_router', None)) is not None:
            context = getattr(route, 'include_context', None)
            yield from iter_routes_with_paths(
                router.routes, prefix + (getattr(context, 'prefix', '') or '')
            )


def loaded_app():
    """
    The FastAPI application if `bazis.core.app` is imported (checks that need the routes
    are skipped otherwise), else None.
    """
    module = sys.modules.get('bazis.core.app')
    return getattr(module, 'app', None)


def route_sets(app) -> dict[type, list[dict]]:
    """
    The route classes of the application with their routes.
    """
    result: dict[type, list[dict]] = {}
    for path, route in iter_routes_with_paths(app.routes):
        route_ctx = getattr(route.endpoint, 'route_ctx', None)
        route_cls = getattr(route_ctx, 'route_cls', None)
        if route_cls is None:
            continue
        result.setdefault(route_cls, []).append(
            {'path': path, 'methods': sorted(route.methods or ()), 'action': route_ctx.name}
        )
    return result


def routes_info(app) -> list[dict]:
    """
    The route classes of the application: the model, the base classes and the routes.
    """
    result = []
    for route_cls, routes in route_sets(app).items():
        model = getattr(route_cls, 'model', None)
        result.append(
            {
                'route_set': f'{route_cls.__module__}.{route_cls.__qualname__}',
                'resource': model.get_resource_label() if model is not None else None,
                'bases': [
                    f'{base.__module__}.{base.__qualname__}'
                    for base in route_cls.__mro__[1:]
                    if base.__module__.startswith('bazis.')
                ],
                'routes': sorted(routes, key=lambda it: (it['path'], it['methods'])),
            }
        )
    return sorted(result, key=lambda it: it['route_set'])


def project_info(app=None) -> dict:
    """
    All facts about the project. The routes are included if the application is given
    or already imported.
    """
    app = app or loaded_app()
    return {
        'packages': packages(),
        'settings': settings_info(),
        'models': models_info(),
        'routes': routes_info(app) if app is not None else None,
    }
