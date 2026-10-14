"""ezmd_api.auth: callers (client IP hash + optional API key), API keys, Turnstile, fetch-node auth
(docs/spec/part1.md section 7.4).

- API keys come from the `api_keys` table or the `keys.json` bootstrap file (`ezmd_api.keys`); both
  store only HMAC-SHA256(pepper, key). A key may restrict the client IP and User-Agent.
- Raw client IPs are never stored; `client_ip_hash` is a salted sha256.
- Turnstile is implemented but off unless `EZMD_TURNSTILE_SECRET` is set (or public mode demands it).
  A verified token yields a short-lived signed JWT cookie bound to the client IP hash and a nonce;
  it covers `CHALLENGE_MAX_USES` further URL jobs (counted per nonce in the state backend, so a
  copied cookie cannot be replayed beyond that) until it expires (docs/spec/part4.md 4.13).
  Siteverify goes to `EZMD_TURNSTILE_VERIFY_URL`; the compose API has no egress and uses Caddy's
  fixed-upstream relay (D-0044). An unreachable or misconfigured siteverify is `turnstile_unavailable`
  (503, logged), never a silent `turnstile_failed`.
- Fetch nodes need `Authorization: Bearer <EZMD_FETCH_NODE_SECRET>` and a source address inside
  `EZMD_FETCH_NODE_CIDR`; both checks are required.
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

from ezmd_api.errors import ApiError
from ezmd_api.keys import (
    KeyRecord,
    create_api_key,
    generate_api_key,
    hash_api_key,
    lookup_api_key,
)
from ezmd_api.settings import TURNSTILE_VERIFY_URL, Settings
from ezmd_api.util import keyed_hash

__all__ = [
    "TURNSTILE_VERIFY_URL",
    "Caller",
    "CallerDep",
    "KeyRecord",
    "TurnstileUnavailable",
    "create_api_key",
    "generate_api_key",
    "get_caller",
    "hash_api_key",
    "lookup_api_key",
]

log = logging.getLogger("ezmd.api.auth")

CHALLENGE_COOKIE = "ezmd_challenge"
CHALLENGE_HEADER = "x-ezmd-challenge"
CHALLENGE_MAX_USES = 5
SITEVERIFY_CONFIG_ERRORS = frozenset({"missing-input-secret", "invalid-input-secret"})
"""Siteverify error codes that mean this instance is misconfigured, not that the visitor failed."""
"""URL jobs one challenge JWT may cover (docs/spec/part4.md: "good for up to 5 convert calls")."""
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


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def client_ip(request: Request, settings: Settings) -> str:
    """The peer address, or the proxy header value when the peer is a trusted proxy.

    `request.client.host` must be the real TCP peer: uvicorn runs with `--no-proxy-headers` (with
    `--forwarded-allow-ips *` it would take the leftmost, client-supplied X-Forwarded-For entry).
    Only EZMD_TRUST_PROXY_HEADER is read, only from a peer inside EZMD_TRUSTED_PROXIES. The compose
    stack uses X-Real-IP, which Caddy overwrites with its trusted_proxies-aware {client_ip}. A
    list-valued header is walked right to left past trusted hops; an unparsable value is ignored.
    """
    peer = request.client.host if request.client else "0.0.0.0"  # noqa: S104 - placeholder, never bound
    header = settings.trust_proxy_header.strip().lower()
    if not header or not _in_networks(peer, settings.trusted_proxies):
        return peer
    hops = [h.strip() for h in request.headers.get(header, "").split(",") if h.strip()]
    if not hops or not all(_valid_ip(h) for h in hops):
        return peer
    for hop in reversed(hops):
        if not _in_networks(hop, settings.trusted_proxies):
            return hop
    return hops[0]


def hash_ip(settings: Settings, ip: str) -> str:
    return keyed_hash(settings.ip_salt, ip)


def get_caller(request: Request) -> Caller:
    """FastAPI dependency: who is calling. Rejects unknown keys; enforces EZMD_REQUIRE_API_KEY."""
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


def challenge_nonce(settings: Settings, token: str, ip_hash: str) -> str | None:
    """The nonce of a valid, unexpired challenge JWT issued to `ip_hash`, else None."""
    try:
        claims = jwt.decode(
            token, _jwt_key(settings), algorithms=["HS256"], options={"require": ["exp", "sub", "nonce"]}
        )
    except jwt.PyJWTError:
        return None
    if not hmac.compare_digest(str(claims.get("sub", "")), ip_hash):
        return None
    nonce = claims.get("nonce")
    return nonce if isinstance(nonce, str) and nonce else None


def check_challenge_jwt(settings: Settings, token: str, ip_hash: str) -> bool:
    return challenge_nonce(settings, token, ip_hash) is not None


def _spend_challenge(request: Request, settings: Settings, nonce: str) -> bool:
    """Count one use of the challenge `nonce`; False once it has covered CHALLENGE_MAX_USES jobs."""
    state = request.app.state.services.state
    uses = int(state.gauge_incr(f"challenge:{nonce}", settings.turnstile_jwt_ttl_s + 5))
    return uses <= CHALLENGE_MAX_USES


class TurnstileUnavailable(Exception):
    """Siteverify could not give an answer about the token (unreachable, bad reply, or our secret rejected)."""


def verify_turnstile(settings: Settings, token: str, remote_ip: str) -> bool:
    """Server-side verification with Cloudflare siteverify. False means Cloudflare rejected the token.

    Raises TurnstileUnavailable (logged at ERROR) when no verdict was possible, so the caller can answer
    503 instead of blaming the visitor. Fails closed either way: no verdict never admits a request."""
    if not settings.turnstile_enabled or not token or len(token) > 4096:
        return False
    url = settings.turnstile_verify_url
    data = {"secret": settings.turnstile_secret.get_secret_value(), "response": token, "remoteip": remote_ip}
    try:
        resp = httpx.post(url, data=data, timeout=10.0)
    except httpx.HTTPError as e:
        log.error("turnstile siteverify failed: %s (%s)", type(e).__name__, url)
        raise TurnstileUnavailable from None
    try:
        # Cloudflare answers some verdicts (a bad secret) with HTTP 400 and a JSON body, so read any status.
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
        log.error("turnstile siteverify answered HTTP %s without a verdict (%s)", resp.status_code, url)
        raise TurnstileUnavailable
    if payload.get("success") is True:
        return True
    codes = [str(c) for c in payload.get("error-codes", []) if isinstance(c, str)][:5]
    if set(codes) & SITEVERIFY_CONFIG_ERRORS:
        log.error("turnstile siteverify rejected this instance's secret: %s", ",".join(codes))
        raise TurnstileUnavailable
    return False


def require_url_challenge(request: Request, caller: Caller, token: str | None) -> str | None:
    """Enforce Turnstile for URL inputs. Returns a fresh challenge JWT to set as a cookie, or None."""
    settings = _settings(request)
    if caller.api_key is not None or not settings.turnstile_required:
        return None
    existing = request.headers.get(CHALLENGE_HEADER) or request.cookies.get(CHALLENGE_COOKIE)
    nonce = challenge_nonce(settings, existing, caller.ip_hash) if existing else None
    if nonce is not None and _spend_challenge(request, settings, nonce):
        return None
    if not token:
        raise ApiError("turnstile_required", "URL inputs require a Turnstile token on this instance.")
    verifier = getattr(request.app.state, "turnstile_verifier", verify_turnstile)
    try:
        verified = verifier(settings, token, client_ip(request, settings))
    except TurnstileUnavailable:
        raise ApiError(
            "turnstile_unavailable",
            "The challenge service cannot be reached right now. Try again shortly.",
            headers={"Retry-After": "30"},
        ) from None
    if not verified:
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
    # Judged on the proxy-reported client address (Caddy also gates the path on its own remote_ip).
    if not _in_networks(client_ip(request, settings), settings.fetch_node_cidr):
        raise ApiError("forbidden", "Fetch-node requests must arrive from the fetch-node network.")
