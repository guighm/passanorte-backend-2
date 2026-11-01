"""Unified error handling for every failure path (spec 005, FR-005, Q1).

Three handlers convert all error outputs to the single ``ApiError`` shape:

1. ``RequestValidationError`` → 422 ``validation_error`` with one detail per
   offending key — ``key`` carries the key AS RECEIVED (a value: exempt from
   the casing convention); nested body locations join with ``.``.
2. ``StarletteHTTPException`` → status-preserving taxonomy per
   ``contracts/camelcase-json.md`` §2 (single source of truth).
3. Unhandled ``Exception`` → 500 ``internal_error`` with a generic message —
   internals never leak (constitution I/II).

Registered once in ``main.py`` via ``register_error_handlers``; probe apps in
tests reuse the same entry point.
"""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from passanorte_back.core.schemas import ApiError, ApiErrorKeyDetails

# errorCode ↔ status taxonomy — source of truth: contracts/camelcase-json.md §2
_ERROR_CODE_BY_STATUS: dict[int, str] = {
    401: "authentication_failed",
    403: "authorization_failed",
    404: "resource_not_found",
    409: "conflict",
}

_GENERIC_500_MESSAGE = "Internal server error."  # never include error details
_GENERIC_4XX_MESSAGE = "Request failed."


def _body_location_key(location: tuple[Any, ...]) -> str:
    """Render a validation error location as the offending key path.

    Drops the leading ``('body',)`` container and joins nested segments:
    ``(body, profile, first_name)`` → ``profile.first_name``. The result is
    a value (the key as received), so underscores are not violations.
    """
    parts = [str(part) for part in location if str(part) != "body"]
    return ".".join(parts) if parts else "body"


def _validation_details(exc: RequestValidationError) -> list[ApiErrorKeyDetails]:
    return [
        ApiErrorKeyDetails(key=_body_location_key(error.get("loc") or ()), message=error["msg"])
        for error in exc.errors()
    ]


def _error_response(status_code: int, error_code: str, message: str, details=None) -> JSONResponse:  # noqa: ANN001
    payload = ApiError(errorCode=error_code, message=message, details=details or [])
    return JSONResponse(status_code=status_code, content=payload.model_dump(by_alias=True))


def register_error_handlers(app: FastAPI) -> None:
    """Attach the unified error handlers to an app (used by main + probes)."""

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request, exc: RequestValidationError) -> JSONResponse:  # noqa: ANN001, ARG001
        return _error_response(
            422,
            "validation_error",
            "Request body is invalid.",
            _validation_details(exc),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ANN001, ARG001
        status = exc.status_code
        error_code = _ERROR_CODE_BY_STATUS.get(
            status, "request_error" if status < 500 else "internal_error"
        )
        message = exc.detail if isinstance(exc.detail, str) else _GENERIC_4XX_MESSAGE
        return _error_response(status, error_code, message)

    @app.exception_handler(HTTPException)
    async def handle_fastapi_http_exception(request, exc: HTTPException) -> JSONResponse:  # noqa: ANN001, ARG001
        status = exc.status_code
        error_code = _ERROR_CODE_BY_STATUS.get(
            status, "request_error" if status < 500 else "internal_error"
        )
        message = exc.detail if isinstance(exc.detail, str) else _GENERIC_4XX_MESSAGE
        return _error_response(status, error_code, message)

    @app.exception_handler(Exception)
    async def handle_unhandled(request, exc: Exception) -> JSONResponse:  # noqa: ANN001, ARG001
        return _error_response(500, "internal_error", _GENERIC_500_MESSAGE)
