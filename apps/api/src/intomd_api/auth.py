"""intomd_api.auth: callers (client IP hash + optional API key), API keys, Turnstile, fetch-node auth
(docs/spec/part1.md section 7.4).

- API keys look like `ak_<env>_<22 base62>` and are stored only as HMAC-SHA256(pepper, key).
- Raw client IPs are never stored; `client_ip_hash` is a salted sha256.
- Turnstile is implemented but off unless `INTOMD_TURNSTILE_SECRET` is set (or public mode demands it).
  A verified token yields a short-lived signed JWT cookie so one solve covers one job creation.
- Fetch nodes need `Authorization: Bearer <INTOMD_FETCH_NODE_SECRET>` and a source address inside
  `INTOMD_FETCH_NODE_CIDR`; both checks are required.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, Request
from sqlalchemy import select

from intomd_api.db import ApiKeyRow, Database
from intomd_api.errors import ApiError
from intomd_api.settings import Settings
from intomd_api.util import as_utc, keyed_hash, random_base62, utcnow

log = logging.getLogger("intomd.api.auth")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
CHALLENGE_COOKIE = "intomd_challenge"
CHALLENGE_HEADER = "x-intomd-challenge"
_EPHEMERAL_JWT_KEY = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class Caller:
    ip_hash: str
    api_key: ApiKeyRow | None = None

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


def _pepper(settings: Settings) -> bytes:
    return (settings.key_pepper.get_secret_value() or "intomd-local-pepper").encode()


def hash_api_key(settings: Settings, key: str) -> str:
    return keyed_hash(_pepper(settings), key)


def generate_api_key(env: str = "live") -> str:
    return f"ak_{env}_{random_base62(16, 22)}"


def create_api_key(db: Database, settings: Settings, name: str, *, env: str = "live", **limits: Any) -> tuple[str, str]:
    """Create a key (for the `intomd keys create` CLI). Returns (plaintext key, key id). The plaintext
    is shown once and never stored."""
    key = generate_api_key(env)
    key_id = "key_" + random_base62(12, 17)
    families = limits.pop("allowed_families", None)
    row = ApiKeyRow(id=key_id, name=name[:128], key_hash=hash_api_key(settings, key), **limits)
    if families is not None:
        row.allowed_families = json.dumps(list(families))
    with db.session() as s:
        s.add(row)
    return key, key_id


def lookup_api_key(db: Database, settings: Settings, key: str) -> ApiKeyRow | None:
    digest = hash_api_key(settings, key)
    with db.session() as s:
        row = s.execute(select(ApiKeyRow).where(ApiKeyRow.key_hash == digest)).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at is not None and as_utc(row.expires_at) <= utcnow():
        return None
    return row


def get_caller(request: Request) -> Caller:
    """FastAPI dependency: who is calling. Rejects unknown keys; enforces INTOMD_REQUIRE_API_KEY."""
    settings = _settings(request)
    ip_hash = hash_ip(settings, client_ip(request, settings))
    raw = request.headers.get("x-api-key")
    if raw:
        row = lookup_api_key(request.app.state.services.db, settings, raw.strip())
        if row is None:
            raise ApiError("unauthorized", "The API key is invalid, revoked, or expired.")
        return Caller(ip_hash=ip_hash, api_key=row)
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
