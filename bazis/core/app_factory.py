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
Application factory and singleton holder for the Bazis project.

Tags: RAG, EXPORT
"""

import importlib
import logging
import sys
import types


_STATE_KEY = 'bazis.core._app_singleton'
_state = sys.modules.get(_STATE_KEY)
if _state is None:
    _state = types.SimpleNamespace(app=None, initializing=False, initialized=False)
    sys.modules[_STATE_KEY] = _state


def get_app_base():
    if _state.app is None:
        _state.app = _create_app_base()
    return _state.app


def ensure_app_initialized():
    app = get_app_base()
    if not _state.initialized and not _state.initializing:
        _state.initializing = True
        try:
            _initialize_app(app)
            _state.initialized = True
        finally:
            _state.initializing = False
    return app


def get_app():
    return ensure_app_initialized()


def _create_app_base():
    # ruff: noqa: E402
    import os
    import sys as _sys

    import django

    _sys.path.append(os.getcwd())
    django.setup()

    from django.conf import settings

    from fastapi import FastAPI

    LOG = logging.getLogger() # noqa: N806

    if BAZIS_APP_MODULE := getattr(settings, 'BAZIS_APP_MODULE', None): # noqa: N806
        app_module = importlib.import_module(BAZIS_APP_MODULE)
        app = app_module.app
    else:
        LOG.info('Custom application not found. Default will be created')
        if settings.DEBUG:
            app = FastAPI(
                openapi_url='/api/openapi.json',
                docs_url='/api/swagger/',
                redoc_url='/api/redoc/',
                swagger_ui_oauth2_redirect_url='/api/swagger/oauth2-redirect',
                swagger_ui_parameters={'defaultModelsExpandDepth': 0},
            )
        else:
            app = FastAPI(
                openapi_url=None,
                docs_url=None,
                redoc_url=None,
                swagger_ui_oauth2_redirect_url=None,
                swagger_ui_parameters={'defaultModelsExpandDepth': 0},
            )

    return app


def _initialize_app(app): # noqa: C901
    # ruff: noqa: E402
    import os
    import re
    import traceback
    from urllib.parse import unquote, urlsplit

    from django.conf import settings
    from django.utils.translation import get_language, to_locale

    from fastapi import Request
    from fastapi.encoders import jsonable_encoder
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import RedirectResponse, Response

    from starlette.concurrency import run_in_threadpool
    from starlette.exceptions import HTTPException
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.responses import JSONResponse
    from starlette.staticfiles import StaticFiles
    from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT

    from bazis.core.i18n import LanguageMiddleware, expand_lang
    from bazis.core.utils.functools import get_attr
    from bazis.core.utils.orm import close_old_connections

    from .errors import JsonApiBazisException, SchemaError, SchemaErrors, SchemaErrorSource

    #: the media files shown inline when the application serves them (DEBUG)
    MEDIA_INLINE = re.compile(r'\.(png|jpe?g|gif|webp|avif|bmp)$', re.IGNORECASE)  # noqa: N806

    async def files_response(
        request: Request, path: str, url: str, root: str, hosts: tuple[str, ...], setting: str
    ) -> Response:
        """
        The files under `url` (MEDIA_URL, STATIC_URL): a redirect to the first configured
        host that is not the application itself (a redirect to itself would loop); without
        one, in DEBUG, the file from `root`; otherwise 404 that names the missing setting.
        A redirect loops only to the URL of the request itself: the target is compared
        with it by host, port (80 and 443 are the defaults) and path, whatever the scheme
        (behind a proxy that terminates TLS the request is http while the host is https).
        """

        def place(parts) -> tuple:
            port = None if parts.port in (80, 443) else parts.port
            return (parts.hostname or '').lower(), port, unquote(parts.path)

        own_place = place(request.url)
        for host in hosts:
            if not host:
                continue
            target = f'{host.rstrip("/")}{url}{path}'
            if place(urlsplit(target)) != own_place:
                return RedirectResponse(url=target)
        if not settings.DEBUG:
            raise HTTPException(
                status_code=404,
                detail=(
                    f'{url} is not served by the application without DEBUG: set {setting} '
                    f'or serve {url} by the web server'
                ),
            )
        # development only: StaticFiles keeps the path inside `root` and answers 404 for a
        # missing file
        return await StaticFiles(directory=root, check_dir=False).get_response(path, request.scope)

    @app.get(f'{settings.MEDIA_URL}{{path:path}}')
    async def redirect_media(request: Request, path: str):
        response = await files_response(
            request,
            path,
            settings.MEDIA_URL,
            settings.MEDIA_ROOT,
            (settings.MEDIA_HOST_URL, settings.ADMIN_HOST_URL),
            'BS_MEDIA_HOST_URL',
        )
        if not isinstance(response, RedirectResponse):
            # the media are the files the clients upload: an HTML page or an SVG image would
            # run its scripts on the origin of the application, so only raster images are
            # shown inline (the headers bazis-uploadable asks the media host for)
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Content-Security-Policy'] = 'sandbox'
            if not MEDIA_INLINE.search(path):
                response.headers['Content-Disposition'] = 'attachment'
        return response

    @app.get(f'{settings.STATIC_URL}{{path:path}}')
    async def redirect_static(request: Request, path: str):
        return await files_response(
            request,
            path,
            settings.STATIC_URL,
            settings.STATIC_ROOT,
            (settings.ADMIN_HOST_URL,),
            'BS_ADMIN_HOST_URL',
        )

    class CloseOldConnectionsMiddleware:
        """
        Middleware that checks and closes dropped connections to maintain database
        connection integrity.
        """

        def __init__(self, app) -> None:
            """
            Initializes the CloseOldConnectionsMiddleware with the given application
            instance.
            """
            self.app = app

        async def __call__(self, scope, receive, send) -> None:
            """
            Executes the middleware, ensuring old connections are closed before and after
            handling the request.
            """
            await run_in_threadpool(close_old_connections)
            try:
                await self.app(scope, receive, send)
            finally:
                await run_in_threadpool(close_old_connections)

    app.add_middleware(CloseOldConnectionsMiddleware)

    app.add_middleware(LanguageMiddleware)

    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CSRF_TRUSTED_ORIGINS,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.router.get('/api/schemas.json')
    async def get_api_schemas(request: Request):
        """
        Fetches the API schemas for the current language and redirects to the
        corresponding JSON schema file.
        """
        for lang in expand_lang(to_locale(get_language())):
            lang_path = os.path.join(settings.STATIC_ROOT, f'schemas_{lang}.json')
            if os.path.exists(lang_path):
                lang_path_dt = os.path.getmtime(lang_path)
                return RedirectResponse(
                    f'{settings.STATIC_URL}schemas_{lang}.json?_h={lang_path_dt}'
                )

    @app.router.get('/api/healthcheck')
    async def healthcheck(request: Request):
        """
        Returns an empty response to indicate that the application is healthy.
        """
        return Response('')

    def get_source_from_loc(
        loc: list | tuple | None, _id: str = None, _type: str = None
    ) -> SchemaErrorSource | None:
        """
        Generates a SchemaErrorSource object from the given location, ID, and type
        information.
        """
        attrs = {}

        if _id:
            attrs['id'] = str(_id)
        if _type:
            attrs['type'] = _type

        if loc:
            loc = [str(x) for x in loc]
            if loc[0] == 'path':
                attrs['parameter'] = '/'.join([''] + loc[1:])
            else:
                if loc[0] == 'body':
                    loc = loc[1:]
                attrs['pointer'] = '/'.join([''] + loc)

        if not attrs:
            return None

        return SchemaErrorSource(**attrs)

    def exc_encoder(
        errs: list[SchemaError],
        status: int,
        cookies: list[tuple[str, str, int]] = None,
        headers: dict[str, str] | None = None,
    ):
        """
        Encodes a list of SchemaError objects into a JSON response with the specified
        status and optional cookies.
        """
        response = JSONResponse(
            jsonable_encoder(SchemaErrors(errors=errs), exclude_unset=True, exclude_none=True),
            status_code=status,
            headers=headers,
        )

        if cookies:
            for cookie_name, cookie_value, cookie_age in cookies:
                response.set_cookie(key=cookie_name, value=cookie_value, max_age=cookie_age)

        return response

    @app.exception_handler(JsonApiBazisException)
    async def json_api_bazis_exception_handler(
        request: Request, exc: JsonApiBazisException
    ) -> JSONResponse:
        """
        Handles JsonApiBazisException by converting it to a JSONAPI-compliant JSONResponse.
        :param request: The current request object.
        :param exc: The exception object.
        :return: JSONResponse.
        """

        def get_item_id(err):
            """
            Retrieves the ID of the item associated with the error, if available.
            """
            if not err.item:
                return None
            return err.item.id

        def get_item_type(err):
            """
            Retrieves the resource label of the item associated with the error, if
            available.
            """
            if not err.item:
                return None
            return err.item.get_resource_label()

        return exc_encoder(
            [
                SchemaError(
                    status=err.status,
                    code=err.code,
                    title=str(err.title) if err.title else None,
                    detail=str(err.detail) if err.detail else None,
                    source=get_source_from_loc(
                        err.loc, _id=get_item_id(err), _type=get_item_type(err)
                    ),
                    meta=err.meta,
                )
                for err in exc.errors
            ],
            exc.status,
            exc.cookies,
        )

    @app.exception_handler(RequestValidationError)
    async def json_api_request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Handles RequestValidationError by converting it to a JSONAPI-compliant JSONResponse.
        :param request: The current request object.
        :param exc: The exception object.
        :return: JSONResponse.
        """
        if any(tuple(err.get('loc') or ()) == ('path', 'item_id') for err in exc.errors()):
            # an id in the path that cannot be a primary key (the routes of an item type it
            # with the primary key) is an item that does not exist, as on the routes that
            # do not type it (`get_queryset_for_item`)
            return await json_api_http_exception_handler(
                request, HTTPException(status_code=404, detail='Item not found')
            )
        return exc_encoder(
            [
                SchemaError(
                    status=HTTP_422_UNPROCESSABLE_CONTENT,
                    code='ERR_VALIDATE',
                    title=err['type'],
                    detail=err['msg'],
                    source=get_source_from_loc(
                        err.get('loc'),
                        _id=get_attr(err, 'ctx._id'),
                        _type=get_attr(err, 'ctx._type'),
                    ),
                )
                for err in exc.errors()
            ],
            HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(HTTPException)
    async def json_api_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """
        Handles common HTTP exceptions by converting them to a JSONAPI-compliant JSONResponse.
        The handler is registered for the Starlette base class, so it also covers the errors
        raised by routing itself (404 for an unknown path, 405 for a wrong method), not only
        the FastAPI HTTPException raised by endpoints.
        :param request: The current request object.
        :param exc: The exception object.
        :return: JSONResponse.
        """
        meta = {}

        headers = getattr(exc, 'headers', None)
        if headers:
            meta.update({'headers': getattr(exc, 'headers', None)})

        meta = meta or None

        return exc_encoder(
            [
                SchemaError(
                    status=exc.status_code,
                    code=getattr(exc, 'code', None),
                    detail=str(exc.detail) if exc.detail else None,
                    meta=meta,
                    traceback=''.join(traceback.format_exception(exc))
                    if settings.DEBUG
                    else None,
                )
            ],
            exc.status_code,
            headers=headers,
        )

    @app.exception_handler(500)
    async def json_api_http_500_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:  # noqa: F811
        """
        Handles generic exceptions by converting them to a JSONAPI-compliant JSONResponse.
        :param request: The current request object.
        :param exc: The exception object.
        :return: JSONResponse.
        """
        return exc_encoder(
            [
                SchemaError(
                    status=500,
                    detail=traceback.format_exc() if settings.DEBUG else None,
                )
            ],
            500,
        )

    from fastapi.routing import iter_route_contexts

    from bazis.core.router import router
    from bazis.core.routing import BazisRoute

    router.routes_cast(BazisRoute)
    app.include_router(router)

    # FastAPI builds the routes of included routers lazily, on the first request.
    # Building Bazis routes involves generating JSON:API schemas, so they are built at
    # startup: the first request is not delayed and declaration errors surface early.
    for _ in iter_route_contexts(app.router.routes):
        pass
