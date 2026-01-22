# ruff: noqa: N806

import re
from contextvars import ContextVar

from django.conf import settings
from django.utils import translation
from django.utils.translation import trans_real

from starlette.datastructures import QueryParams


CTX_TRANS = ContextVar('CTX_LANG', default=None)


class LanguageMiddleware:
    """
    Middleware to handle language settings based on query parameters, headers, or
    default settings.

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
        lang = None

        if 'query_string' in scope:
            query_string = scope['query_string']

            if isinstance(query_string, bytes):
                query_string = query_string.decode()

            query_params = QueryParams(query_string)
            if 'lang' in query_params:
                lang = query_params['lang']

        if lang is None and 'headers' in scope:
            language_header = dict(scope['headers']).get(b'accept-language')
            if language_header:
                if isinstance(language_header, bytes):
                    language_header = language_header.decode()
                lang = language_header.split(',')[0]

        if lang is None or lang not in [l_code for l_code, l_name in settings.LANGUAGES]:
            lang = settings.LANGUAGE_CODE

        lang = re.split(r'[-_]', lang)[0]

        translation.activate(lang)

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
