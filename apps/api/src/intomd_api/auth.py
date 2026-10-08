"""intomd_api.auth: callers (client IP hash + optional API key), API keys, Turnstile, fetch-node auth
(docs/spec/part1.md section 7.4).

- API keys come from the `api_keys` table or the `keys.json` bootstrap file (`intomd_api.keys`); both
  store only HMAC-SHA256(pepper, key). A key may restrict the client IP and User-Agent.
- Raw client IPs are never stored; `client_ip_hash` is a salted sha256.
- Turnstile is implemented but off unless `INTOMD_TURNSTILE_SECRET` is set (or public mode demands it).
  A verified token yields a short-lived signed JWT cookie so one solve covers one job creation.
- Fetch nodes need `Authorization: Bearer <INTOMD_FETCH_NODE_SECRET>` and a source address inside
  `INTOMD_FETCH_NODE_CIDR`; both checks are required.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, Request

from intomd_api.errors import ApiError
from intomd_api.keys import (
    KeyRecord,
    create_api_key,
    generate_api_key,
    hash_api_key,
    lookup_api_key,
)
from intomd_api.settings import Settings
from intomd_api.util import keyed_hash

__all__ = [
    "Caller",
    "CallerDep",
    "KeyRecord",
    "create_api_key",
    "generate_api_key",
    "get_caller",
    "hash_api_key",
    "lookup_api_key",
]

log = logging.getLogger("intomd.api.auth")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
CHALLENGE_COOKIE = "intomd_challenge"
CHALLENGE_HEADER = "x-intomd-challenge"
_EPHEMERAL_JWT_KEY = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class Caller:
    ip_hash: str
    api_key: KeyRecord | None = None

    @property
    def key_id(self) -> str | None:
        return self.api_key.id if self.api_key is not None else None

    @property
    def unlimited(self) -> bool:
        return bool(self.api_key is not None and self.api_key.unlimited)

    @property
    def identity(self) -> str:
        return f"key:{self.api_key.id}" if self.api_key is not None else f"ip:{self.ip_hash}"


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _in_networks(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.ip_network(c, strict=False) for c in cidrs)


def client_ip(request: Request, settings: Settings) -> str:
    """The peer address, or the proxy header value when the peer is a trusted proxy."""
    peer = request.client.host if request.client else "0.0.0.0"  # noqa: S104 - placeholder, never bound
    header = settings.trust_proxy_header.strip().lower()
    if not header or not _in_networks(peer, settings.trusted_proxies):
        return peer
    value = request.headers.get(header, "")
    if not value:
        return peer
    hops = [h.strip() for h in value.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _in_networks(hop, settings.trusted_proxies):
            return hop
    return hops[0] if hops else peer


def hash_ip(settings: Settings, ip: str) -> str:
    return keyed_hash(settings.ip_salt, ip)


def get_caller(request: Request) -> Caller:
    """FastAPI dependency: who is calling. Rejects unknown keys; enforces INTOMD_REQUIRE_API_KEY."""
    settings = _settings(request)
    ip = client_ip(request, settings)
    ip_hash = hash_ip(settings, ip)
    raw = request.headers.get("x-api-key")
    if raw:
        services = request.app.state.services
        record = lookup_api_key(services.db, settings, raw.strip(), services.keys)
        if record is None:
            raise ApiError("unauthorized", "The API key is invalid, revoked, or expired.")
        if not record.allows_ip(ip) or not record.allows_user_agent(request.headers.get("user-agent", "")):
            raise ApiError("forbidden", "This API key may not be used from this client.")
        return Caller(ip_hash=ip_hash, api_key=record)
    if settings.require_api_key:
        raise ApiError("unauthorized", "This instance requires an API key (X-API-Key header).")
    return Caller(ip_hash=ip_hash)


CallerDep = Annotated[Caller, Depends(get_caller)]


# ---------------------------------------------------------------------------
# Turnstile and the challenge JWT
# ---------------------------------------------------------------------------


def _jwt_key(settings: Settings) -> bytes:
    secret = settings.jwt_secret.get_secret_value()
    return secret.encode() if secret else _EPHEMERAL_JWT_KEY


def issue_challenge_jwt(settings: Settings, ip_hash: str) -> str:
    now = int(time.time())
    claims = {"sub": ip_hash, "iat": now, "exp": now + settings.turnstile_jwt_ttl_s, "nonce": secrets.token_hex(8)}
    return jwt.encode(claims, _jwt_key(settings), algorithm="HS256")


def check_challenge_jwt(settings: Settings, token: str, ip_hash: str) -> bool:
    try:
        claims = jwt.decode(token, _jwt_key(settings), algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return False
    return hmac.compare_digest(str(claims.get("sub", "")), ip_hash)


def verify_turnstile(settings: Settings, token: str, remote_ip: str) -> bool:
    """Server-side verification with Cloudflare siteverify. Network or protocol errors fail closed."""
    if not settings.turnstile_enabled or not token or len(token) > 4096:
        return False
    data = {"secret": settings.turnstile_secret.get_secret_value(), "response": token, "remoteip": remote_ip}
    try:
        resp = httpx.post(TURNSTILE_VERIFY_URL, data=data, timeout=10.0)
        return bool(resp.status_code == 200 and resp.json().get("success") is True)
    except (httpx.HTTPError, ValueError):
        log.warning("turnstile verification request failed")
        return False


def require_url_challenge(request: Request, caller: Caller, token: str | None) -> str | None:
    """Enforce Turnstile for URL inputs. Returns a fresh challenge JWT to set as a cookie, or None."""
    settings = _settings(request)
    if caller.api_key is not None or not settings.turnstile_required:
        return None
    existing = request.headers.get(CHALLENGE_HEADER) or request.cookies.get(CHALLENGE_COOKIE)
    if existing and check_challenge_jwt(settings, existing, caller.ip_hash):
        return None
    if not token:
        raise ApiError("turnstile_required", "URL inputs require a Turnstile token on this instance.")
    verifier = getattr(request.app.state, "turnstile_verifier", verify_turnstile)
    if not verifier(settings, token, client_ip(request, settings)):
        raise ApiError("turnstile_failed", "The Turnstile token could not be verified.")
    return issue_challenge_jwt(settings, caller.ip_hash)


# ---------------------------------------------------------------------------
# Fetch nodes
# ---------------------------------------------------------------------------


def require_fetch_node(request: Request) -> None:
    """FastAPI dependency for /v1/fetch-node/*: bearer secret AND source CIDR."""
    settings = _settings(request)
    secret = settings.fetch_node_secret
    auth = request.headers.get("authorization", "")
    scheme, _, presented = auth.partition(" ")
    if (
        secret is None
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(presented.strip().encode(), secret.get_secret_value().encode())
    ):
        raise ApiError("unauthorized", "Fetch-node authentication failed.")
    peer = request.client.host if request.client else ""
    if not _in_networks(peer, settings.fetch_node_cidr):
        raise ApiError("forbidden", "Fetch-node requests must arrive from the fetch-node network.")
