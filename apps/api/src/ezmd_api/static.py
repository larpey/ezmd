"""ezmd_api.static: serve the built web UI (`apps/web/dist`) at `/` with an SPA fallback.

Hashed assets under `assets/` are cached for a year (immutable); everything else, including the
`index.html` fallback, is `no-cache`. API and reserved operator paths (`/v1`, `/admin`, `/metrics`, ...)
never fall through to the SPA: unknown ones answer 404, so an unmounted admin or metrics route is not
mistaken for a live page (docs/spec/part4.md 4.14.5 item 7).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response

from ezmd_api.errors import ApiError

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
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

    # Registered for every method so unknown API paths answer 404 (not 405) through this catch-all.
    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def spa(path: str, request: Request) -> Response:
        if request.method not in ("GET", "HEAD") or is_reserved(path):
            raise ApiError("not_found", "Not found.")
        target = _resolve(root, path) if path else None
        if target is not None:
            media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            cache = IMMUTABLE if path.startswith("assets/") else NO_CACHE
            return FileResponse(target, media_type=media_type, headers={"Cache-Control": cache})
        if Path(path).suffix and not path.endswith(".html"):
            raise ApiError("not_found", "Not found.")
        return FileResponse(index, media_type="text/html; charset=utf-8", headers={"Cache-Control": NO_CACHE})

    return True
