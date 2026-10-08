"""Meta routes: /v1/capabilities, /healthz, /readyz (docs/spec/part1.md section 7.3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from intomd_api import __version__
from intomd_api.rendering import FORMATS, PROFILES
from intomd_api.routes.common import services_of

router = APIRouter(tags=["meta"])

RESIDENTIAL_PLATFORMS = ["youtube", "tiktok", "instagram", "x"]


def _converters() -> list[dict[str, Any]]:
    from intomd.registry import default_registry

    out: list[dict[str, Any]] = []
    for reg in default_registry().registrations():
        conv = reg.converter
        out.append(
            {
                "id": conv.id,
                "family": conv.family,
                "mimes": list(conv.mimes),
                "experimental": bool(conv.experimental),
                "loaded": reg.import_error is None,
                "extras": list(conv.requires_extras),
            }
        )
    return sorted(out, key=lambda c: str(c["id"]))


@router.get("/v1/capabilities", summary="Converters, profiles, formats, limits, fetch-node status")
def capabilities(request: Request) -> dict[str, Any]:
    services = services_of(request)
    s = services.settings
    return {
        "version": __version__,
        "converters": _converters(),
        "profiles": list(PROFILES),
        "formats": list(FORMATS),
        "limits": {
            "max_upload_bytes": s.max_upload_bytes,
            "max_url_bytes": s.max_url_bytes,
            "max_audio_seconds": s.anon_max_duration_s,
            "max_pages": s.anon_max_pages,
            "retention_hours": s.retention_hours,
        },
        "fetch_node_online": bool(s.fetch_node_secret is not None and services.state.nodes_online()),
        "residential_platforms": RESIDENTIAL_PLATFORMS if s.fetch_node_secret is not None else [],
        "public_mode": s.public_mode,
        "turnstile_site_key": s.turnstile_sitekey or None,
        "challenge": "turnstile" if s.turnstile_sitekey and s.turnstile_enabled else None,
    }


@router.get("/healthz", summary="Liveness")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness: database, Redis, and a live worker")
def readyz(request: Request) -> JSONResponse:
    services = services_of(request)
    checks = {
        "database": services.db.ping(),
        "state": services.state.ping(),
        "workers": services.queue.workers_alive(),
    }
    ready = all(checks.values())
    body = {"status": "ready" if ready else "not_ready", "checks": checks}
    return JSONResponse(body, status_code=200 if ready else 503)
