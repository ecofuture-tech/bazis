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

# ruff: noqa: N806

from contextvars import ContextVar

from django.conf import settings
from django.utils import translation
from django.utils.translation import trans_real

from starlette.datastructures import Headers, QueryParams


CTX_TRANS = ContextVar('CTX_LANG', default=None)


def match_language(code: str) -> str | None:
    """
    The language of LANGUAGES of a language code: the same code or its base code (`ru` of
    `ru-RU` or `ru_RU`), case-insensitively; None if the project does not have it.
    """
    languages = {language.lower(): language for language, _name in settings.LANGUAGES}
    code = code.strip().lower().replace('_', '-')
    return languages.get(code) or languages.get(code.split('-')[0])


def request_language(query_lang: str | None, accept_language: str | None) -> str:
    """
    The language of a request: the query parameter `lang`, then the languages of the header
    `Accept-Language` by weight, the first one the project has (LANGUAGES); otherwise
    LANGUAGE_CODE (its base code when only that is in LANGUAGES).

    Tags: RAG, EXPORT
    """
    candidates = [query_lang] if query_lang else []
    if accept_language:
        candidates += [
            code
            for code, weight in trans_real.parse_accept_lang_header(accept_language)
            if code != '*' and weight > 0
        ]
    for code in candidates:
        if language := match_language(code):
            return language
    return match_language(settings.LANGUAGE_CODE) or settings.LANGUAGE_CODE


class LanguageMiddleware:
    """
    Activates the language of the request (`request_language`): the query parameter
    `lang`, then the header `Accept-Language`, matched against LANGUAGES by code or base
    code, otherwise LANGUAGE_CODE.

    Tags: RAG, EXPORT
    """

    def __init__(self, app) -> None:
        """
        Initialize the LanguageMiddleware with the given ASGI application.
        """
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        """
        ASGI callable to process the incoming request, determine the language, and
        activate the corresponding translation.
        """
        if scope['type'] in ('http', 'websocket'):
            query_lang = QueryParams(scope.get('query_string', b'')).get('lang')
            accept_language = Headers(scope=scope).get('accept-language')
        else:
            query_lang = accept_language = None

        translation.activate(request_language(query_lang, accept_language))

        await self.app(scope, receive, send)


class TransActive:
    """
    Custom context manager to handle thread-local language translation activation.
    """

    ctx_token = None

    @property
    def value(self):
        """
        Get the current active translation or the default language translation.
        """
        return CTX_TRANS.get() or trans_real.translation(settings.LANGUAGE_CODE)

    @value.setter
    def value(self, translation):
        """
        Set the current active translation in the context.
        """
        self.ctx_token = CTX_TRANS.set(translation)

    @value.deleter
    def value(self):
        """
        Reset the current active translation in the context.
        """
        if self.ctx_token:
            CTX_TRANS.reset(self.ctx_token)


trans_real._active = TransActive()


def expand_lang(loc):
    """
    Expand a locale name into a list of locale names that are progressively more specific.
    gettext._expand_lang
    """
    import locale

    loc = locale.normalize(loc)
    COMPONENT_CODESET = 1 << 0
    COMPONENT_TERRITORY = 1 << 1
    COMPONENT_MODIFIER = 1 << 2
    # split up the locale into its base components
    mask = 0
    pos = loc.find('@')
    if pos >= 0:
        modifier = loc[pos:]
        loc = loc[:pos]
        mask |= COMPONENT_MODIFIER
    else:
        modifier = ''
    pos = loc.find('.')
    if pos >= 0:
        codeset = loc[pos:]
        loc = loc[:pos]
        mask |= COMPONENT_CODESET
    else:
        codeset = ''
    pos = loc.find('_')
    if pos >= 0:
        territory = loc[pos:]
        loc = loc[:pos]
        mask |= COMPONENT_TERRITORY
    else:
        territory = ''
    language = loc
    ret = []
    for i in range(mask + 1):
        if not (i & ~mask):  # if all components for this combo exist ...
            val = language
            if i & COMPONENT_TERRITORY:
                val += territory
            if i & COMPONENT_CODESET:
                val += codeset
            if i & COMPONENT_MODIFIER:
                val += modifier
            ret.append(val)
    ret.reverse()
    return ret
