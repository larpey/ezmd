"""ezmd_api.static: serve the built web UI (`apps/web/dist`) at `/` with an SPA fallback.

Hashed assets under `assets/` are cached for a year (immutable); everything else, including the
`index.html` fallback, is `no-cache`, and misses are `no-store`. These are the only cache headers on
static paths (Caddy sets none). API and reserved operator paths (`/v1`, `/admin`, `/metrics`, ...)
never fall through to the SPA: unknown ones answer 404, so an unmounted admin or metrics route is not
mistaken for a live page (docs/internal/spec/part4.md 4.14.5 item 7). A wrong method on a real route answers
405 with `Allow`.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from starlette.routing import Match

from ezmd_api.errors import ApiError

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
NO_STORE = "no-store"
PROBE_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE")
# First path segments the SPA never claims (compared case-insensitively).
RESERVED_SEGMENTS = frozenset(
    {
        "v1",
        "v2",
        "api",
        "admin",
        "metrics",
        "healthz",
        "readyz",
        "livez",
        "openapi.json",
        "docs",
        "redoc",
        "mcp",
        "fetch-node",
        "internal",
        "debug",
        ".well-known",
    }
)


def is_reserved(path: str) -> bool:
    """True when `path` (no leading slash) starts with a reserved segment."""
    return path.split("/", 1)[0].lower() in RESERVED_SEGMENTS


def _not_found() -> ApiError:
    # Never cacheable: a CDN or browser must not keep a 404 for a hashed asset that a deploy adds later.
    return ApiError("not_found", "Not found.", headers={"Cache-Control": NO_STORE})


def default_web_dist() -> Path:
    return Path(__file__).resolve().parents[4] / "apps" / "web" / "dist"


def _resolve(root: Path, rel: str) -> Path | None:
    if "\x00" in rel or "\\" in rel:
        return None
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def mount_static(app: FastAPI, dist: Path | None) -> bool:
    root = (dist or default_web_dist()).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    # Registered for every method so unknown API paths answer 404 through this catch-all. Because it fully
    # matches every method, Starlette would pick it over a real route that only matches the path, so it
    # answers 405 itself for those (`_allowed_methods`).
    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def spa(path: str, request: Request) -> Response:
        if request.method not in ("GET", "HEAD") or is_reserved(path):
            allowed = _allowed_methods(request)
            if allowed:
                raise ApiError("method_not_allowed", headers={"Allow": ", ".join(allowed)})
            raise _not_found()
        target = _resolve(root, path) if path else None
        if target is not None:
            media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            cache = IMMUTABLE if path.startswith("assets/") else NO_CACHE
            return FileResponse(target, media_type=media_type, headers={"Cache-Control": cache})
        if Path(path).suffix and not path.endswith(".html"):
            raise _not_found()
        return FileResponse(index, media_type="text/html; charset=utf-8", headers={"Cache-Control": NO_CACHE})

    def _allowed_methods(request: Request) -> list[str]:
        """Methods another route serves on this path. Probed through `Route.matches` per method, because
        included routers do not expose their routes' `methods` on every FastAPI version."""
        others = [r for r in request.app.router.routes if getattr(r, "endpoint", None) is not spa]
        if not any(r.matches(request.scope)[0] == Match.PARTIAL for r in others):
            return []
        allowed = []
        for method in PROBE_METHODS:
            scope = {**request.scope, "method": method}
            if any(r.matches(scope)[0] == Match.FULL for r in others):
                allowed.append(method)
        return allowed

    return True
