"""Meta routes: /v1/capabilities, /v1/warnings, /healthz, /readyz (docs/spec/part1.md section 7.3)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from intomd_api import __version__
from intomd_api.apidoc import NO_AUTH, errors
from intomd_api.rendering import FORMATS, PROFILES
from intomd_api.routes.common import services_of
from intomd_api.schemas import CapabilitiesOut, HealthOut, ReadyOut, WarningCodeOut, WarningsOut

router = APIRouter(tags=["meta"])

RESIDENTIAL_PLATFORMS = ["youtube", "tiktok", "instagram", "x"]
_PUBLIC = {"security": NO_AUTH}


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


@router.get(
    "/v1/capabilities",
    response_model=CapabilitiesOut,
    operation_id="getCapabilities",
    summary="Converters, profiles, formats, limits, fetch-node status",
    description=(
        "Lists every registered converter (including ones whose optional extra is missing, with `loaded: false`), "
        "the output profiles and formats, the anonymous limits, and whether a residential fetch node is online. "
        "The web UI reads this on load."
    ),
    responses=errors(),
    openapi_extra=_PUBLIC,
)
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


@lru_cache(maxsize=1)
def warning_registry() -> WarningsOut:
    """Every canonical warning code with its default severity, description, suggestion, and aliases."""
    from intomd.warnings.codes import ALIASES, CODES

    aliases: dict[str, list[str]] = {}
    for alias, kind in ALIASES.items():
        aliases.setdefault(kind.value, []).append(alias)
    rows = [
        WarningCodeOut(
            code=spec.code.value,
            severity=spec.severity,
            family=spec.family,
            description=spec.description,
            suggestion=spec.suggestion,
            truncates=spec.truncates,
            aliases=sorted(aliases.get(spec.code.value, [])),
        )
        for spec in sorted(CODES.values(), key=lambda sp: sp.code.value)
    ]
    return WarningsOut(warnings=rows)


@router.get(
    "/v1/warnings",
    response_model=WarningsOut,
    operation_id="listWarningCodes",
    summary="The warning code registry",
    description=(
        "Every warning code a conversion can emit, with its default severity, a description, a suggested action, "
        "whether it means content was truncated, and the retired spellings (aliases) that normalize to it. "
        "`JobOut.warnings`, SSE `warning` events, and the sidecar use these codes."
    ),
    responses=errors(),
    openapi_extra=_PUBLIC,
)
def list_warnings() -> JSONResponse:
    body = warning_registry().model_dump(mode="json")
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@router.get(
    "/healthz",
    response_model=HealthOut,
    operation_id="healthz",
    summary="Liveness",
    description="200 whenever the process is serving requests. Does not check dependencies.",
    responses=errors(),
    openapi_extra=_PUBLIC,
)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/readyz",
    response_model=ReadyOut,
    operation_id="readyz",
    summary="Readiness: database, Redis, and a live worker",
    description="200 when the database and state backend answer and a worker heartbeated in the last 60 s; else 503.",
    responses={**errors(), 503: {"model": ReadyOut, "description": "A dependency is down; `checks` says which."}},
    openapi_extra=_PUBLIC,
)
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
