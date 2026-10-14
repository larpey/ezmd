"""Turnstile siteverify: the configured verify URL, explicit failure when it cannot be reached (D-0044)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from ezmd_api import auth
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
SECRET = "s" * 32


class _Resp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def _public(settings_factory: Callable[..., Settings], **extra: Any) -> Settings:
    return settings_factory(
        public_mode=True, jwt_secret=SECRET, key_pepper=SECRET, turnstile_secret="ts-secret", **extra
    )


def test_verify_posts_to_the_configured_url(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    seen: list[str] = []

    def post(url: str, **kwargs: Any) -> _Resp:
        seen.append(url)
        return _Resp(200, {"success": True})

    monkeypatch.setattr(httpx, "post", post)
    relay = "http://caddy:9180/turnstile/v0/siteverify"
    assert auth.verify_turnstile(_public(settings_factory, turnstile_verify_url=relay), "tok", "203.0.113.9")
    assert auth.verify_turnstile(_public(settings_factory), "tok", "203.0.113.9")
    assert seen == [relay, auth.TURNSTILE_VERIFY_URL]


def test_rejected_token_is_a_plain_false(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: _Resp(200, {"success": False, "error-codes": ["invalid-input-response"]})
    )
    assert auth.verify_turnstile(_public(settings_factory), "tok", "203.0.113.9") is False


@pytest.mark.parametrize(
    "behaviour",
    ["connect_error", "http_500", "not_json", "bad_secret"],
)
def test_unreachable_or_misconfigured_siteverify_raises(
    behaviour: str,
    monkeypatch: pytest.MonkeyPatch,
    settings_factory: Callable[..., Settings],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def post(url: str, **kwargs: Any) -> _Resp:
        if behaviour == "connect_error":
            raise httpx.ConnectError("no route to host")
        if behaviour == "http_500":
            return _Resp(500, {})
        if behaviour == "not_json":
            resp = _Resp(200, None)
            resp.json = lambda: (_ for _ in ()).throw(ValueError("not json"))  # type: ignore[method-assign]
            return resp
        return _Resp(200, {"success": False, "error-codes": ["invalid-input-secret"]})

    monkeypatch.setattr(httpx, "post", post)
    with caplog.at_level(logging.ERROR, logger="ezmd.api.auth"), pytest.raises(auth.TurnstileUnavailable):
        auth.verify_turnstile(_public(settings_factory), "tok", "203.0.113.9")
    assert any(r.levelno >= logging.ERROR for r in caplog.records), "the operator must see why"
    assert "ts-secret" not in caplog.text


async def test_unreachable_siteverify_is_a_503_not_a_silent_deny(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    def post(url: str, **kwargs: Any) -> _Resp:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", post)
    async with api_client(_public(settings_factory)) as (client, _app):
        r = await client.post("/v1/convert", json={"url": "https://example.com/a.txt", "turnstile_token": "tok"})
    assert r.status_code == 503, r.text
    body = r.json()["error"]
    assert body["code"] == "turnstile_unavailable"
    assert r.headers["retry-after"]


def test_compose_routes_siteverify_through_the_caddy_relay() -> None:
    """The API stays off the egress network; it reaches siteverify only through Caddy's fixed-upstream relay."""
    services = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    api = services["api"]
    assert "egress" not in api["networks"]
    url = str(api["environment"]["EZMD_TURNSTILE_VERIFY_URL"])
    assert "http://caddy:9180/turnstile/v0/siteverify" in url
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    relay = caddy.split("http://:9180 {", 1)[1].split("\n}\n", 1)[0]
    assert "reverse_proxy https://challenges.cloudflare.com" in relay
    assert "path /turnstile/v0/siteverify" in relay
    assert "method POST" in relay
    assert "header_up Host challenges.cloudflare.com" in relay
    # Never published on the host.
    assert not any("9180" in str(p) for p in services["caddy"]["ports"])
