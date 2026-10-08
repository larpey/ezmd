"""intomd_api.main: the FastAPI app factory (docs/spec/part1.md sections 7 and 8.4).

Run with `uvicorn intomd_api.main:app` (uses env settings) or call `serve(host, port)`, which is
what `intomd serve` uses; it defaults to the inline queue when INTOMD_QUEUE is unset.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from intomd_api import __version__
from intomd_api.apidoc import SECURITY_SCHEMES, TAGS
from intomd_api.errors import error_body, error_table_markdown, install_handlers
from intomd_api.logs import configure_logging
from intomd_api.options import link_options_schema
from intomd_api.purge import Scheduler
from intomd_api.ratelimit import rate_headers
from intomd_api.routes import convert, fetch_node, jobs, meta, metrics
from intomd_api.schemas import EXTRA_SCHEMA_MODELS
from intomd_api.services import Services, build_services
from intomd_api.settings import Settings
from intomd_api.static import mount_static
from intomd_api.util import new_request_id

log = logging.getLogger("intomd.api")

_NL2 = chr(10) * 2
_DESCRIPTION_HEAD = (
    "Convert anything to LLM-ready Markdown."
    + _NL2
    + "Create a job with `POST /v1/convert` (multipart upload or JSON URL), follow it with "
    + "`GET /v1/jobs/{job_id}/events` (SSE) or by polling `GET /v1/jobs/{job_id}`, then fetch "
    + "`GET /v1/jobs/{job_id}/result`. The job id is the capability; jobs created with an API key "
    + "also require that key. Every response carries `X-Request-Id`; every error uses the schema below."
    + _NL2
    + "## Error codes"
    + _NL2
)

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; img-src 'self' data: blob:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
EXPOSED_HEADERS = [
    "X-Request-Id",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "Retry-After",
    "X-Markdown-Tokens",
    "X-Intomd-Truncated",
    "X-Intomd-Warnings",
    "X-Intomd-Injection-Risk",
    "X-Intomd-Job",
]
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class EdgeMiddleware:
    """Outermost ASGI middleware: request id, security headers, rate-limit headers, access log, and
    a last-resort 500 in the 7.5 schema (so even crashes carry the headers and never leak internals)."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for k, v in scope.get("headers", []):
            if k == b"x-request-id":
                incoming = v.decode("latin-1")
        request_id = incoming if _CLIENT_REQUEST_ID.match(incoming) else new_request_id()
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        started = time.monotonic()
        status_holder = {"status": 500, "started": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["started"] = True
                status_holder["status"] = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                present = {k.lower() for k, _ in headers}
                extra: dict[str, str] = {"X-Request-Id": request_id, **SECURITY_HEADERS}
                rl = state.get("ratelimit")
                if rl is not None:
                    extra.update(rate_headers(rl))
                for name, value in extra.items():
                    if name.lower().encode() not in present:
                        headers.append((name.lower().encode(), value.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("unhandled error", extra={"request_id": request_id, "path": scope.get("path", "")})
            if status_holder["started"]:
                raise
            await self._internal_error(send_wrapper, request_id)
        finally:
            log.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_holder["status"],
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                },
            )

    async def _internal_error(self, send: Send, request_id: str) -> None:
        import json

        payload = error_body(
            "internal_error", "An internal error occurred.", 500, request_id, base_url=self.settings.public_url
        )
        body = json.dumps(payload).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})


def create_app(settings: Settings | None = None, *, redis_client: Any = None) -> FastAPI:
    """Build the app. `redis_client` lets tests inject fakeredis."""
    settings = settings or Settings()
    configure_logging(settings)
    services = build_services(settings, redis_client=redis_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services.db.ensure_schema()
        scheduler = Scheduler(services) if settings.scheduler_enabled else None
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.stop()
            services.close()

    app = FastAPI(
        title="intomd API",
        version=__version__,
        description=_DESCRIPTION_HEAD + error_table_markdown(),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        openapi_tags=TAGS,
        license_info={"name": "Apache-2.0", "identifier": "Apache-2.0"},
        contact={"name": "intomd", "url": settings.public_url},
        servers=[{"url": settings.public_url, "description": "This instance"}],
    )
    app.state.settings = settings
    app.state.services = services
    install_handlers(app)
    app.include_router(meta.router)
    app.include_router(convert.router)
    app.include_router(jobs.router)
    if settings.fetch_node_secret is not None:
        app.include_router(fetch_node.router)
    if settings.metrics_token is not None:
        app.include_router(metrics.router)
    mount_static(app, settings.web_dist)
    _extend_openapi(app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key", "Last-Event-ID", "X-Intomd-Challenge"],
            expose_headers=EXPOSED_HEADERS,
            allow_credentials=False,
            max_age=600,
        )
    app.add_middleware(EdgeMiddleware, settings=settings)
    return app


def _extend_openapi(app: FastAPI) -> None:
    """Add the models that are only referenced from hand-written request bodies (multipart/JSON
    routes parse their bodies themselves) to `components.schemas`."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        schema.setdefault("components", {})["securitySchemes"] = SECURITY_SCHEMES
        components = schema["components"].setdefault("schemas", {})
        for model in EXTRA_SCHEMA_MODELS:
            js = model.model_json_schema(ref_template="#/components/schemas/{model}")
            components.update(js.pop("$defs", {}))
            components[model.__name__] = js
        link_options_schema(components)
        _drop_fastapi_validation_responses(schema)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def _drop_fastapi_validation_responses(schema: dict[str, Any]) -> None:
    """Request validation errors are 400 `invalid_request` here (errors.install_handlers), so FastAPI's
    automatic 422 HTTPValidationError responses are wrong; drop them and their component schemas."""
    marker = "#/components/schemas/HTTPValidationError"
    for ops in schema.get("paths", {}).values():
        for op in ops.values():
            resp = op.get("responses", {}).get("422")
            if resp and resp.get("content", {}).get("application/json", {}).get("schema", {}).get("$ref") == marker:
                del op["responses"]["422"]
    components = schema.get("components", {}).get("schemas", {})
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)


def services_of(app: FastAPI) -> Services:
    services: Services = app.state.services
    return services


def serve(host: str = "127.0.0.1", port: int = 8000, *, settings: Settings | None = None) -> None:
    """Run the API with uvicorn. Without INTOMD_QUEUE in the environment this uses the inline queue,
    so `intomd serve` works on a laptop without Redis."""
    import uvicorn

    if settings is None:
        settings = Settings()
        if "INTOMD_QUEUE" not in os.environ:
            settings = settings.model_copy(update={"queue": "inline"})
    uvicorn.run(create_app(settings), host=host, port=port, proxy_headers=False, server_header=False)


def __getattr__(name: str) -> Any:
    """`intomd_api.main:app` is built lazily so importing this module never reads the environment."""
    if name == "app":
        built = create_app()
        globals()["app"] = built
        return built
    raise AttributeError(name)
