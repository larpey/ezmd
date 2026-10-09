"""Client-IP derivation behind Caddy (and Cloudflare in front of Caddy).

uvicorn runs with --no-proxy-headers, so request.client.host is the real TCP peer. The app trusts
exactly one header (EZMD_TRUST_PROXY_HEADER, X-Real-IP in compose, set by Caddy from its own
trusted_proxies-aware {client_ip}) and only when that peer is inside EZMD_TRUSTED_PROXIES.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from starlette.requests import Request

from ezmd_api.auth import client_ip
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload

INTERNAL = "172.16.0.0/12,10.0.0.0/8,192.168.0.0/16"
CADDY_PEER = "172.18.0.5"


def _request(peer: str, headers: dict[str, str]) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 40000),
    }
    return Request(scope)


@pytest.fixture
def proxied(settings_factory: Callable[..., Settings]) -> Settings:
    return settings_factory(trust_proxy_header="X-Real-IP", trusted_proxies=INTERNAL)


def test_untrusted_peer_spoofed_headers_ignored(proxied: Settings) -> None:
    req = _request("203.0.113.9", {"X-Real-IP": "198.51.100.1", "X-Forwarded-For": "198.51.100.2"})
    assert client_ip(req, proxied) == "203.0.113.9"


def test_trusted_proxy_header_honored(proxied: Settings) -> None:
    req = _request(CADDY_PEER, {"X-Real-IP": "198.51.100.1"})
    assert client_ip(req, proxied) == "198.51.100.1"


def test_forwarded_for_ignored_when_x_real_ip_is_the_trusted_header(proxied: Settings) -> None:
    """A client-supplied X-Forwarded-For that Caddy passes through never decides the IP."""
    req = _request(CADDY_PEER, {"X-Real-IP": "198.51.100.1", "X-Forwarded-For": "6.6.6.6, 198.51.100.1"})
    assert client_ip(req, proxied) == "198.51.100.1"


def test_garbage_header_value_falls_back_to_peer(proxied: Settings) -> None:
    req = _request(CADDY_PEER, {"X-Real-IP": "not-an-ip"})
    assert client_ip(req, proxied) == CADDY_PEER


def test_no_header_configured_uses_peer(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(trusted_proxies=INTERNAL)
    req = _request(CADDY_PEER, {"X-Real-IP": "198.51.100.1"})
    assert client_ip(req, settings) == CADDY_PEER


async def test_spoofed_header_cannot_evade_rate_limit(settings_factory: Callable[..., Settings]) -> None:
    """End to end: an untrusted peer rotating X-Real-IP / X-Forwarded-For stays one rate-limit bucket."""
    settings = settings_factory(anon_ratelimit_max=1, trust_proxy_header="X-Real-IP", trusted_proxies=INTERNAL)
    async with api_client(settings, client_addr=("203.0.113.5", 1)) as (client, _):
        first = await upload(client, b"x\n", "a.txt", headers={"X-Real-IP": "198.51.100.1"})
        assert first.status_code == 202
        spoofed = {"X-Real-IP": "198.51.100.2", "X-Forwarded-For": "198.51.100.3"}
        assert (await upload(client, b"y\n", "b.txt", headers=spoofed)).status_code == 429


async def test_trusted_proxy_header_splits_rate_limit_buckets(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(anon_ratelimit_max=1, trust_proxy_header="X-Real-IP", trusted_proxies=INTERNAL)
    async with api_client(settings, client_addr=(CADDY_PEER, 1)) as (client, _):
        assert (await upload(client, b"x\n", "a.txt", headers={"X-Real-IP": "198.51.100.1"})).status_code == 202
        assert (await upload(client, b"y\n", "b.txt", headers={"X-Real-IP": "198.51.100.2"})).status_code == 202
        assert (await upload(client, b"z\n", "c.txt", headers={"X-Real-IP": "198.51.100.1"})).status_code == 429


def _fetch_node_request(settings: Settings, peer: str, real_ip: str | None) -> Request:
    from types import SimpleNamespace

    headers = {"Authorization": "Bearer " + "s" * 20}
    if real_ip is not None:
        headers["X-Real-IP"] = real_ip
    req = _request(peer, headers)
    req.scope["app"] = SimpleNamespace(state=SimpleNamespace(settings=settings))
    return req


def test_fetch_node_cidr_judged_on_proxy_reported_ip(settings_factory: Callable[..., Settings]) -> None:
    """Behind Caddy the TCP peer is Caddy; the fetch-node CIDR check uses Caddy's X-Real-IP."""
    from ezmd_api.auth import require_fetch_node
    from ezmd_api.errors import ApiError

    settings = settings_factory(trust_proxy_header="X-Real-IP", trusted_proxies=INTERNAL, fetch_node_secret="s" * 20)
    require_fetch_node(_fetch_node_request(settings, CADDY_PEER, "100.64.1.2"))
    with pytest.raises(ApiError):
        require_fetch_node(_fetch_node_request(settings, CADDY_PEER, "203.0.113.9"))
    with pytest.raises(ApiError):  # an untrusted peer cannot claim a Tailscale address
        require_fetch_node(_fetch_node_request(settings, "203.0.113.9", "100.64.1.2"))
