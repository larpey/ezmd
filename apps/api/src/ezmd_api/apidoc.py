"""ezmd_api.apidoc: OpenAPI helpers: per-route error responses, tags, and security schemes.

`errors(...)` turns the error codes a route can return into FastAPI `responses` entries that point at
the 7.5 `ErrorResponse` schema, grouped by HTTP status with the codes listed in the description.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ezmd_api.errors import ERROR_DESCRIPTIONS, ERROR_STATUS
from ezmd_api.schemas import ErrorResponse

API_KEY_SCHEME = "ApiKey"
FETCH_NODE_SCHEME = "FetchNodeBearer"

TAGS: list[dict[str, str]] = [
    {"name": "convert", "description": "Create conversion jobs from uploads or URLs."},
    {"name": "jobs", "description": "Job state, server-sent events, results, attachments, supply, and purge."},
    {"name": "meta", "description": "Capabilities, the warning code registry, liveness, and readiness."},
    {
        "name": "fetch-node",
        "description": "Residential fetch-node protocol. Mounted only when EZMD_FETCH_NODE_SECRET is set.",
    },
]

SECURITY_SCHEMES: dict[str, dict[str, Any]] = {
    API_KEY_SCHEME: {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Optional API key (`ak_<env>_...`). Keyed callers get the key's limits and skip Turnstile.",
    },
    FETCH_NODE_SCHEME: {
        "type": "http",
        "scheme": "bearer",
        "description": "EZMD_FETCH_NODE_SECRET; requests must also come from EZMD_FETCH_NODE_CIDR.",
    },
}

OPTIONAL_API_KEY: list[dict[str, list[str]]] = [{}, {API_KEY_SCHEME: []}]
FETCH_NODE_AUTH: list[dict[str, list[str]]] = [{FETCH_NODE_SCHEME: []}]
NO_AUTH: list[dict[str, list[str]]] = []

COMMON = ("invalid_request", "internal_error")
"""Every route can return these (validation errors and the last-resort handler)."""


def errors(*codes: str) -> dict[int | str, dict[str, Any]]:
    """FastAPI `responses` for the given error codes plus COMMON."""
    by_status: dict[int, list[str]] = defaultdict(list)
    for code in (*codes, *COMMON):
        status = ERROR_STATUS[code]
        if code not in by_status[status]:
            by_status[status].append(code)
    out: dict[int | str, dict[str, Any]] = {}
    for status in sorted(by_status):
        lines = [f"`{c}`: {ERROR_DESCRIPTIONS.get(c, c)}" for c in by_status[status]]
        out[status] = {"model": ErrorResponse, "description": " ".join(lines)}
    return out


def rate_limit_headers() -> dict[str, dict[str, Any]]:
    return {
        name: {"description": text, "schema": {"type": "integer"}}
        for name, text in (
            ("X-RateLimit-Limit", "Requests allowed in the most restrictive window checked"),
            ("X-RateLimit-Remaining", "Requests left in that window"),
            ("X-RateLimit-Reset", "Unix time when the window resets"),
        )
    }
