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
Django system checks of the Bazis environment requirements.

Tags: RAG, INTERNAL
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.caches)
def check_cache_backend(app_configs, **kwargs):
    """
    Bazis requires a Redis cache (django-redis): model items are cached and invalidated
    by key pattern, which other Django cache backends do not support.
    """
    from django.core.cache import caches

    backend = caches['default']
    if not hasattr(backend, 'delete_pattern'):
        return [
            Error(
                'The default cache backend does not support delete_pattern.',
                hint=(
                    'Bazis requires Redis: set BS_CACHES__DEFAULT__BACKEND='
                    'django_redis.cache.RedisCache and BS_CACHES__DEFAULT__LOCATION '
                    f'(current backend: {settings.CACHES["default"]["BACKEND"]}).'
                ),
                id='bazis.E001',
            )
        ]
    return []


@register(Tags.security, deploy=True)
def check_allowed_hosts(app_configs, **kwargs):
    """
    A wildcard in ALLOWED_HOSTS accepts any Host header (Django checks only that the list
    is not empty).
    """
    if '*' in settings.ALLOWED_HOSTS:
        return [
            Warning(
                "ALLOWED_HOSTS contains '*': any Host header is accepted.",
                hint='List the domains of the project in BS_ALLOWED_HOSTS.',
                id='bazis.W001',
            )
        ]
    return []


@register()
def check_bazis_apps(app_configs, **kwargs):
    """
    An empty BS_BAZIS_APPS (or BS_BAZIS_CONFIG_APPS) turns off the settings of all Bazis
    packages, also of the ones the project uses: their code then fails on missing settings.
    """
    from bazis.core.configure import listed_bazis_apps

    if listed_bazis_apps() == []:
        return [
            Warning(
                'BS_BAZIS_APPS (or BS_BAZIS_CONFIG_APPS) is an empty list: the settings of '
                'no Bazis package are loaded.',
                hint=(
                    'Unset it to load the settings of all installed Bazis packages, or list '
                    'the Bazis packages of the project in it.'
                ),
                id='bazis.W002',
            )
        ]
    return []


@register()
def check_default_routes(app_configs, **kwargs):
    """
    The default route of a model restricts the objects of the model in the relationships
    and `included` of the other routes (its `restrict_queryset`). With several route sets
    of a model in the application that restrict its objects differently, the last defined
    one is the default unless one of them declares `default_route = True`: the order of
    the imports decides otherwise. Needs the application (`bazis_doctor` loads it);
    skipped without it.
    """
    from bazis.core import introspect
    from bazis.core.routes_abstract.jsonapi.mixins import restrict_queryset_override

    if (app := introspect.loaded_app()) is None:
        return []

    by_model: dict[type, list[type]] = {}
    for route_cls in introspect.route_sets(app):
        if (model := getattr(route_cls, 'model', None)) is not None:
            by_model.setdefault(model, []).append(route_cls)

    messages = []
    for model, route_classes in by_model.items():
        if len({id(restrict_queryset_override(it)) for it in route_classes}) < 2:
            continue
        if sum(1 for it in route_classes if vars(it).get('default_route')) == 1:
            continue
        names = ', '.join(sorted(_qualname(it) for it in route_classes))
        messages.append(
            Warning(
                f'The model has several route sets that restrict its objects differently '
                f'({names}) and not one explicit default route: the default one is '
                f'{_qualname(model.get_default_route())}.',
                hint=(
                    'Declare `default_route = True` in the route set whose restrict_queryset '
                    'restricts the objects of the model in the relationships and `included` '
                    'of the other routes.'
                ),
                obj=model._meta.label,
                id='bazis.W003',
            )
        )
    return messages


@register(Tags.security)
def check_filters_strict(app_configs, **kwargs):
    """
    `BAZIS_FILTERS_STRICT=false` is the transitional rollback of 2.9: the filter, the sorting
    and the search of the API reach every field of the models and every relation, also the
    fields a route does not show and the objects a user cannot see.
    """
    if getattr(settings, 'BAZIS_FILTERS_STRICT', True):
        return []
    return [
        Warning(
            'BAZIS_FILTERS_STRICT is off: the filter, sort and search of the API reach the '
            'fields the routes do not show and the related objects the users cannot see.',
            hint=(
                'Remove BS_BAZIS_FILTERS_STRICT=false: the setting is transitional and will be '
                'removed. Add the fields a client filters, sorts or searches by to the LIST '
                'schema of the route (`fields`, `search_fields`).'
            ),
            id='bazis.W006',
        )
    ]


@register()
def check_search_fields(app_configs, **kwargs):
    """
    A search field of a route must be a field of its LIST schema (`fields`): the search of a
    request (BAZIS_FILTERS_STRICT) leaves out the others. Needs the application
    (`bazis_doctor` loads it); skipped without it.
    """
    from bazis.core import introspect
    from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
    from bazis.core.utils.query_complex import LOOKUP_PREFIXES, QueryScope

    if (app := introspect.loaded_app()) is None:
        return []

    messages = []
    for route_cls in introspect.route_sets(app):
        if not issubclass(route_cls, JsonapiRouteBase) or not route_cls.search_fields:
            continue
        # the LIST schema of the route itself, not the one a package makes per user
        scope = QueryScope(
            f.source for f in JsonapiRouteBase.query_fields.__func__(route_cls) if f.can_filter
        )
        for field in route_cls.search_fields:
            name = str(field)
            if not scope.reaches(route_cls.model, name[1:] if name[:1] in LOOKUP_PREFIXES else name):
                messages.append(
                    Warning(
                        f'The search field {field!r} of the route set is not a field of its '
                        'LIST schema (or, through a relation, of the LIST schema of the '
                        'default route of the related model): the search leaves it out.',
                        hint='Add the field to `fields` of the route or remove it from '
                        '`search_fields`.',
                        obj=_qualname(route_cls),
                        id='bazis.W007',
                    )
                )
    return messages


def _qualname(cls) -> str:
    return f'{cls.__module__}.{cls.__qualname__}' if cls is not None else 'None'


@register()
def check_translation_conflicts(app_configs, **kwargs):
    """
    Two Bazis packages translate the same msgid differently: the catalog that comes first in
    LOCALE_PATHS wins, so the text depends on the packages installed and on their order.
    A msgid the project translates in its own `locale` is its choice.
    """
    import os

    from bazis.core.utils.locale import bazis_locale_paths, read_catalog

    packages = bazis_locale_paths()
    paths = [path for path in settings.LOCALE_PATHS if path in packages]
    project_locale = os.path.join(settings.BASE_DIR, 'locale')

    warnings = []
    for language, _name in settings.LANGUAGES:
        project = read_catalog(project_locale, language)
        translations = {}
        for path in paths:
            for msgid, msgstr in read_catalog(path, language).items():
                if msgid not in project:
                    translations.setdefault(msgid, []).append((packages[path], msgstr))
        for msgid, found in translations.items():
            if len({msgstr for _package, msgstr in found}) > 1:
                texts = ', '.join(f'{package} "{msgstr}"' for package, msgstr in found)
                warnings.append(
                    Warning(
                        f'"{msgid}" is translated into {language} differently by the Bazis '
                        f'packages: {texts}; the first one wins.',
                        hint=(
                            f'Translate "{msgid}" in the locale of the project '
                            f'({project_locale}), or upgrade the packages.'
                        ),
                        id='bazis.W004',
                    )
                )
    return warnings


@register()
def check_translations_of_languages(app_configs, **kwargs):
    """
    A language of LANGUAGES (other than English, the language of the msgids) in which no
    catalog translates texts of an installed Bazis package: they stay in English.
    """
    from django.utils.translation import trans_real

    from bazis.core.utils.locale import bazis_locale_paths, catalog_languages, read_catalog

    packages = bazis_locale_paths(settings.INSTALLED_APPS)
    msgids = {
        path: {msgid for language in catalog_languages(path) for msgid in read_catalog(path, language)}
        for path in packages
    }

    warnings = []
    for language, _name in settings.LANGUAGES:
        if language.lower().split('-')[0] == 'en':
            continue
        try:
            translated = trans_real.translation(language)._catalog
        except OSError:
            translated = {}
        untranslated = sorted(
            f'{packages[path]} ({len(missing)})'
            for path in packages
            if (missing := [msgid for msgid in msgids[path] if msgid not in translated])
        )
        if untranslated:
            warnings.append(
                Warning(
                    f'The language {language} of LANGUAGES has no translation of texts of the '
                    f'Bazis packages {", ".join(untranslated)}: they stay in English.',
                    hint='Translate their msgids in the locale of the project, or remove the language.',
                    id='bazis.W005',
                )
            )
    return warnings
