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

    LOG = logging.getLogger()

    if BAZIS_APP_MODULE := getattr(settings, 'BAZIS_APP_MODULE', None):
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


def _initialize_app(app):
    # ruff: noqa: E402
    import os
    import traceback

    from django.conf import settings
    from django.utils.translation import get_language, to_locale

    from fastapi import Request
    from fastapi.encoders import jsonable_encoder
    from fastapi.exceptions import HTTPException, RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import RedirectResponse, Response

    from starlette.concurrency import run_in_threadpool
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.responses import JSONResponse
    from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

    from bazis.core.i18n import LanguageMiddleware, expand_lang
    from bazis.core.utils.functools import get_attr
    from bazis.core.utils.orm import close_old_connections

    from .errors import JsonApiBazisException, SchemaError, SchemaErrors, SchemaErrorSource

    @app.get(f'{settings.MEDIA_URL}{{path:path}}')
    async def redirect_media(path: str):
        if settings.MEDIA_HOST_URL:
            return RedirectResponse(url=f'{settings.MEDIA_HOST_URL}{settings.MEDIA_URL}{path}')
        return RedirectResponse(url=f'{settings.ADMIN_HOST_URL}{settings.MEDIA_URL}{path}')

    @app.get(f'{settings.STATIC_URL}{{path:path}}')
    async def redirect_static(path: str):
        return RedirectResponse(url=f'{settings.ADMIN_HOST_URL}{settings.STATIC_URL}{path}')

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
            await self.app(scope, receive, send)
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
        errs: list[SchemaError], status: int, cookies: list[tuple[str, str, int]] = None
    ):
        """
        Encodes a list of SchemaError objects into a JSON response with the specified
        status and optional cookies.
        """
        response = JSONResponse(
            jsonable_encoder(SchemaErrors(errors=errs), exclude_unset=True, exclude_none=True),
            status_code=status,
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
        return exc_encoder(
            [
                SchemaError(
                    status=HTTP_422_UNPROCESSABLE_ENTITY,
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
            HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(HTTPException)
    async def json_api_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """
        Handles common HTTP exceptions by converting them to a JSONAPI-compliant JSONResponse.
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
                    detail=str(exc.detail) if exc.detail else None,
                    meta=meta,
                    traceback=''.join(traceback.format_exception(exc))
                    if settings.DEBUG
                    else None,
                )
            ],
            exc.status_code,
        )

    @app.exception_handler(500)
    async def json_api_http_exception_handler(
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

    from bazis.core.router import router
    from bazis.core.routing import BazisRoute

    router.routes_cast(BazisRoute)
    app.include_router(router)

    def uvicorn_start(
        host: str = '0.0.0.0',
        port: int = settings.APP_PORT,
        reload: bool = True,
        reload_includes: list[str] = None,
        reload_dirs: list[str] = None,
    ):
        """
        Starts the Uvicorn server with the specified host, port, and reload settings.
        """
        import uvicorn

        DJANGO_SETTINGS_MODULE = os.environ.get('DJANGO_SETTINGS_MODULE')  # noqa: N806
        if not DJANGO_SETTINGS_MODULE:
            raise RuntimeError('DJANGO_SETTINGS_MODULE environment variable is not set.')

        app_path = DJANGO_SETTINGS_MODULE.split('.')[0] + '.main:app'

        uvicorn.run(
            app_path,
            host=host,
            port=port,
            reload=reload,
            reload_includes=reload_includes,
            reload_dirs=reload_dirs or settings.BAZIS_APP_RELOAD_DIRS,
        )

    app.uvicorn_start = uvicorn_start
