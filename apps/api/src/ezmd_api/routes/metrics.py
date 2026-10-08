"""GET /metrics: Prometheus text format (docs/spec/part4.md 4.10.5).

Mounted only when EZMD_METRICS_TOKEN is set, and every scrape must send
`Authorization: Bearer <EZMD_METRICS_TOKEN>`. Caddy also 404s /metrics at the public edge, so the
token is the second of two independent controls (docs/decisions/P1-T10.md). Not in the OpenAPI
document: it is an operator endpoint, documented in docs/api.md.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ezmd_api import metrics
from ezmd_api.errors import ApiError
from ezmd_api.routes.common import services_of

router = APIRouter()


def _authorized(request: Request) -> bool:
    token = services_of(request).settings.metrics_token
    if token is None:
        return False
    scheme, _, presented = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(presented.strip().encode(), token.get_secret_value().encode())


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    if not _authorized(request):
        raise ApiError("unauthorized", "Metrics require the metrics bearer token.")
    body = await run_in_threadpool(metrics.render, services_of(request))
    return Response(body, media_type=metrics.CONTENT_TYPE, headers={"Cache-Control": "no-store"})
