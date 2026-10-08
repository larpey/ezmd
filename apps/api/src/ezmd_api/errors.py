"""ezmd_api.errors: the error schema (docs/spec/part1.md section 7.5) and exception handlers.

Messages never carry stack traces, server paths, or engine internals; those are logged with the
request id instead.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("ezmd.api")

ERROR_STATUS: dict[str, int] = {
    "invalid_request": 400,
    "turnstile_required": 401,
    "turnstile_failed": 403,
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "method_not_allowed": 405,
    "job_not_ready": 409,
    "input_too_large": 413,
    "unsupported_media_type": 415,
    "url_blocked": 422,
    "platform_disabled": 422,
    "experimental_disabled": 422,
    "fetch_depth_exceeded": 422,
    "result_too_large": 422,
    "rate_limited": 429,
    "conversion_failed": 500,
    "internal_error": 500,
    "not_implemented": 501,
    "fetch_failed": 502,
    "queue_unavailable": 503,
    "timeout": 504,
}

DEFAULT_MESSAGES: dict[str, str] = {
    "invalid_request": "The request is invalid.",
    "unauthorized": "Authentication is required.",
    "forbidden": "You do not have access to this resource.",
    "not_found": "Not found.",
    "method_not_allowed": "Method not allowed.",
    "internal_error": "An internal error occurred.",
    "conversion_failed": "Conversion failed.",
    "experimental_disabled": "This input needs an experimental converter, which is disabled on this instance.",
    "fetch_depth_exceeded": "The input asked for too many nested fetches.",
    "result_too_large": "The conversion result exceeds the size limit.",
}

ERROR_DESCRIPTIONS: dict[str, str] = {
    "invalid_request": "Malformed body, unknown option, or invalid profile override.",
    "turnstile_required": "A Turnstile token is required for URL jobs on this instance.",
    "turnstile_failed": "The Turnstile token was rejected.",
    "unauthorized": "Missing or unknown API key, or bad fetch-node secret.",
    "forbidden": "The key or node may not do this (for example residential fetches).",
    "not_found": "Unknown job, attachment, or route.",
    "method_not_allowed": "Wrong HTTP method.",
    "job_not_ready": "The job has not reached the state this call needs.",
    "input_too_large": "Upload or fetched body over the caller's cap.",
    "unsupported_media_type": "Executable or unsupported input.",
    "url_blocked": "The URL (or a URL a converter asked for) failed the SSRF guard.",
    "platform_disabled": "The site is disabled by this instance's platform policy.",
    "experimental_disabled": "Only an experimental converter handles this input and experimental converters are off.",
    "fetch_depth_exceeded": "A converter asked for more nested fetches than ezmd.inputs.MAX_FETCH_DEPTH allows.",
    "result_too_large": "The converter's result exceeded EZMD_MAX_RESULT_BYTES.",
    "rate_limited": "Too many requests, jobs, or concurrent jobs; see Retry-After.",
    "conversion_failed": "Every converter in the chain failed.",
    "internal_error": "Unexpected server error (logged with the request id).",
    "not_implemented": "The format exists in the contract but is not built yet (docx).",
    "fetch_failed": "The URL could not be fetched.",
    "queue_unavailable": "The queue is down or the instance is at its active-job cap.",
    "timeout": "The conversion exceeded its time limit.",
}


def error_table_markdown() -> str:
    """The error-code table embedded in the OpenAPI description."""
    nl = chr(10)
    rows = ["| code | status | meaning |", "| --- | --- | --- |"]
    for code, status in ERROR_STATUS.items():
        rows.append(f"| `{code}` | {status} | {ERROR_DESCRIPTIONS.get(code, '')} |")
    return nl.join(rows)


_HTTP_STATUS_CODES: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "job_not_ready",
    413: "input_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
    501: "not_implemented",
    503: "queue_unavailable",
}


class ApiError(Exception):
    """Raise anywhere in a request to produce a 7.5-shaped response."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        status: int | None = None,
        detail: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.status = status or ERROR_STATUS.get(code, 500)
        self.message = message or DEFAULT_MESSAGES.get(code, code.replace("_", " ").capitalize() + ".")
        self.detail = detail or {}
        self.headers = headers or {}
        super().__init__(self.message)


def request_id_of(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def error_body(
    code: str, message: str, status: int, request_id: str, detail: dict[str, Any] | None = None, *, base_url: str = ""
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "status": status,
            "request_id": request_id,
            "detail": detail or {},
            "docs": f"{base_url.rstrip('/')}/docs/errors#{code}",
        }
    }


def _base_url(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    return str(getattr(settings, "public_url", "")) if settings is not None else ""


def error_response(request: Request, err: ApiError) -> JSONResponse:
    rid = request_id_of(request)
    body = error_body(err.code, err.message, err.status, rid, err.detail, base_url=_base_url(request))
    return JSONResponse(body, status_code=err.status, headers=err.headers)


async def _api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(request, exc)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, "invalid_request" if exc.status_code < 500 else "internal_error")
    headers = dict(exc.headers or {})
    return error_response(request, ApiError(code, status=exc.status_code, headers=headers))


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = []
    for e in exc.errors()[:20]:
        loc = ".".join(str(p) for p in e.get("loc", ()) if p != "body")
        fields.append({"field": loc, "problem": str(e.get("msg", ""))[:200]})
    return error_response(request, ApiError("invalid_request", "Request validation failed.", detail={"fields": fields}))


def install_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
