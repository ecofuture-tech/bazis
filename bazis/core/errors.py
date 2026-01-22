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

from collections.abc import Sequence
from typing import Any

from django.utils.translation import gettext_lazy as _

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError

from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_422_UNPROCESSABLE_ENTITY,
)

from pydantic import BaseModel, ValidationError


class JsonApiHttpException(HTTPException):
    """
    Custom HTTP exception class for JSON API errors. Provides a base structure for
    other specific HTTP exceptions.

    Tags: RAG, EXPORT
    """

    status = HTTP_400_BAD_REQUEST
    code = 'ERR_REQUEST'
    title = _('Request error')

    def __init__(
        self,
        status_code: int = None,
        detail: Any = None,
        code: str = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        """
        Initializes the JsonApiHttpException with a status code, detail message, error
        code, and optional headers.
        """
        self.code = code or self.code
        super().__init__(
            status_code=status_code or self.status, detail=detail or self.title, headers=headers
        )


class JsonApi401Exception(JsonApiHttpException):
    """
    HTTP 401 Unauthorized exception for JSON API. Indicates that the request
    requires user authentication.

    Tags: RAG, EXPORT
    """

    status = HTTP_401_UNAUTHORIZED
    code = 'ERR_UNAUTHORIZED'
    title = _('Permission denied: check token')


class JsonApi403Exception(JsonApiHttpException):
    """
    HTTP 403 Forbidden exception for JSON API. Indicates that the server understood
    the request but refuses to authorize it.

    Tags: RAG, EXPORT
    """

    status = HTTP_403_FORBIDDEN
    code = 'ERR_FORBIDDEN'
    title = _('Permission denied: check access')


class JsonApiRequestValidationError(RequestValidationError):
    """
    HTTP 422 Unprocessable Entity exception for JSON API. Raised when there is a
    validation error in the request.
    """

    status = HTTP_422_UNPROCESSABLE_ENTITY
    code = 'ERR_VALIDATE'
    title = _('Validation error')


class JsonApiBazisError(Exception):
    """
    Custom exception class for handling detailed validation errors in JSON API.
    Includes status, code, title, and optional metadata.

    Tags: RAG, EXPORT
    """

    status: str | int = HTTP_422_UNPROCESSABLE_ENTITY
    code: str = 'ERR_VALIDATE'
    title: str = _('Validation error')
    meta_schema: type[BaseModel] = None

    def __init__(
        self,
        detail: str,
        meta_data: dict = None,
        loc: tuple[int | str, ...] = None,
        *,
        code: str = None,
        title: str = None,
        status: str | int = None,
        item=None,
    ) -> None:
        """
        Initializes the JsonApiBazisError with a detail message, optional metadata,
        location, code, title, status, and item.
        """
        self.detail = detail
        self.loc = loc
        self.code = code or self.code
        self.title = title or self.title
        self.status = status or self.status
        self.item = item
        if self.meta_schema:
            self.meta = self.meta_schema.model_validate(jsonable_encoder(meta_data)).model_dump()
        else:
            self.meta = jsonable_encoder(meta_data)


class JsonApiBazisException(Exception):  # noqa: N818
    """
    Custom exception class for handling multiple JsonApiBazisError instances.
    Includes status and optional cookies.

    Tags: RAG, EXPORT
    """

    status: str | int = HTTP_400_BAD_REQUEST
    cookies: list[tuple[str, str, int]] = None

    def __init__(
        self,
        errors: list[JsonApiBazisError] | JsonApiBazisError,
        status: str | int = None,
        cookies: list[tuple[str, str, int]] = None,
    ) -> None:
        """
        Initializes the JsonApiBazisException with a list of errors, optional status,
        and optional cookies.
        """
        self.errors = errors if isinstance(errors, Sequence) else [errors]
        self.status = status or self.status
        self.cookies = cookies

    @classmethod
    def from_validation_error(
        cls, exc: ValidationError, *, loc: tuple[int | str, ...] = None, item=None
    ):
        """
        Class method to create a JsonApiBazisException from a Pydantic ValidationError.
        Converts each validation error into a JsonApiBazisError.
        """
        return cls(
            [
                JsonApiBazisError(
                    title=err['type'],
                    detail=err['msg'],
                    loc=(loc or tuple()) + err.get('loc'),
                    item=item,
                )
                for err in exc.errors()
            ]
        )


class SchemaErrorSource(BaseModel):
    """
    Data model representing the source of a schema error. Includes pointer,
    parameter, id, and type fields.

    Tags: RAG, EXPORT
    """

    pointer: str | None = None
    parameter: str | None = None
    id: str | None = None
    type: str | None = None


class SchemaError(BaseModel):
    """
    Data model representing a schema error. Includes status, title, code, detail,
    source, meta, and optional traceback.

    Tags: RAG, EXPORT
    """

    status: int  # 400 401 403 404 422 500
    title: str | None = None
    code: str | None = None
    detail: str | None = None
    source: SchemaErrorSource | None = None
    meta: dict[str, Any] | None = None
    traceback: str | None = None


class SchemaErrors(BaseModel):
    """
    Data model representing a collection of schema errors. Contains a list of
    SchemaError instances.

    Tags: RAG, EXPORT
    """

    errors: list[SchemaError]
