"""URL inputs: SSRF pre-check, Turnstile, fetch queue, residential routing, needs_user_action + supply."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from intomd_api.purge import reap_residential
from intomd_api.settings import Settings
from intomd_api.testing import api_client, wait_for_state


def _fake_fetch(body: bytes, content_type: str = "text/plain") -> Callable[..., Any]:
    from intomd.core.netguard import FetchResult

    def fetch(url: str, **kwargs: Any) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            headers={"content-type": content_type},
            body=body,
            resolved_ip="93.184.216.34",
            redirects=[],
            duration_seconds=0.01,
        )

    return fetch


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest",
        "file:///etc/passwd",
        "http://user:pw@example.com/",
        "http://localhost:6379/",
        "http://100.100.100.100/",
    ],
)
async def test_blocked_urls_422(client: Any, url: str) -> None:
    r = await client.post("/v1/convert", json={"url": url})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "url_blocked"
    assert "pw" not in r.text


async def test_url_job_fetches_and_converts(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    from intomd.core import netguard

    monkeypatch.setattr(netguard, "fetch", _fake_fetch(b"Plain text from the web.\n"))
    r = await client.post(
        "/v1/convert", json={"url": "https://Example.com/notes.txt?utm_source=x#frag", "profile": "compact"}
    )
    assert r.status_code == 202, r.text
    job = r.json()["job"]
    assert job["queue"] == "fetch"
    assert job["input"]["kind"] == "url"
    body = await wait_for_state(client, job["id"])
    assert body["state"] == "done", body
    result = await client.get(f"/v1/jobs/{job['id']}/result")
    assert "Plain text from the web." in result.text
    # Normalized URL dedups (scheme/host case, tracking params, fragment).
    again = await client.post("/v1/convert", json={"url": "https://example.com/notes.txt", "profile": "compact"})
    assert again.status_code == 200 and again.json()["job"]["id"] == job["id"]


async def test_fetch_errors_map_to_codes(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    from intomd.core import netguard

    def blocked(url: str, **kwargs: Any) -> Any:
        raise netguard.UrlBlocked("resolves to 10.0.0.1", url=url)

    monkeypatch.setattr(netguard, "fetch", blocked)
    r = await client.post("/v1/convert", json={"url": "https://rebind.example.com/"})
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["state"] == "failed"
    assert body["error"]["code"] == "url_blocked"
    assert "10.0.0.1" not in str(body)


async def test_fetched_executable_rejected(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    from intomd.core import netguard

    elf = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8 + b"\x02\x00\x3e\x00\x01\x00\x00\x00" + b"\x00" * 200
    monkeypatch.setattr(netguard, "fetch", _fake_fetch(elf, "application/octet-stream"))
    r = await client.post("/v1/convert", json={"url": "https://example.com/tool"})
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["error"]["code"] == "unsupported_media_type"


async def test_turnstile_required_in_public_mode(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    from intomd.core import netguard

    monkeypatch.setattr(netguard, "fetch", _fake_fetch(b"hi\n"))
    secret = "s" * 32
    settings = settings_factory(public_mode=True, jwt_secret=secret, key_pepper=secret, turnstile_secret="ts-secret")
    async with api_client(settings) as (client, app):
        r = await client.post("/v1/convert", json={"url": "https://example.com/a.txt"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "turnstile_required"
        app.state.turnstile_verifier = lambda s, token, ip: token == "good"
        bad = await client.post("/v1/convert", json={"url": "https://example.com/a.txt", "turnstile_token": "bad"})
        assert bad.status_code == 403
        assert bad.json()["error"]["code"] == "turnstile_failed"
        ok = await client.post("/v1/convert", json={"url": "https://example.com/a.txt", "turnstile_token": "good"})
        assert ok.status_code == 202
        assert "intomd_challenge" in ok.headers.get("set-cookie", "")
        assert "httponly" in ok.headers["set-cookie"].lower()
        # The challenge cookie covers the next creation without a new token.
        again = await client.post("/v1/convert", json={"url": "https://example.com/b.txt"})
        assert again.status_code == 202


async def test_turnstile_off_by_default(client: Any) -> None:
    r = await client.post("/v1/convert", json={"url": "https://example.com/x"})
    assert r.status_code == 202


def _residential_policy(tmp_path: Path) -> Path:
    path = tmp_path / "platforms.toml"
    path.write_text("[hosts]" + chr(10) + '"video.example.com" = "residential_only"' + chr(10), encoding="utf-8")
    return path


async def test_anonymous_prefer_residential_is_ignored(client: Any) -> None:
    """D-0017 item 6: an anonymous caller cannot pick the home fetch node for a default-policy host."""
    r = await client.post("/v1/convert", json={"url": "https://www.example.com/watch?v=1", "prefer_residential": True})
    assert r.status_code == 202, r.text
    assert r.json()["job"]["queue"] == "fetch"


async def test_keyed_prefer_residential_needs_permission(settings_factory: Callable[..., Settings]) -> None:
    from intomd_api.auth import create_api_key

    async with api_client(settings_factory()) as (client, app):
        services = app.state.services
        plain, _ = create_api_key(services.db, services.settings, "plain", env="test")
        allowed, _ = create_api_key(services.db, services.settings, "home", env="test", residential_allowed=True)
        payload = {"url": "https://www.example.com/watch?v=2", "prefer_residential": True}
        denied = await client.post("/v1/convert", json=payload, headers={"X-API-Key": plain})
        assert denied.status_code == 403
        ok = await client.post("/v1/convert", json=payload, headers={"X-API-Key": allowed})
        assert ok.status_code == 202, ok.text
        assert ok.json()["job"]["queue"] == "fetch_residential"


async def test_residential_needs_user_action_then_supply(
    settings_factory: Callable[..., Settings], tmp_path: Path
) -> None:
    settings = settings_factory(residential_wait_seconds=0, platforms_file=_residential_policy(tmp_path))
    async with api_client(settings) as (client, app):
        payload = {"url": "https://video.example.com/watch?v=1"}
        r = await client.post("/v1/convert", json=payload)
        assert r.status_code == 202
        job = r.json()["job"]
        assert job["queue"] == "fetch_residential"
        assert job["state"] == "fetching"
        early_supply = await client.post(f"/v1/jobs/{job['id']}/supply", files={"file": ("a.txt", b"x", "text/plain")})
        assert early_supply.status_code == 409
        assert reap_residential(app.state.services) == 1
        body = (await client.get(f"/v1/jobs/{job['id']}")).json()
        assert body["state"] == "needs_user_action"
        assert body["needs_action"]["kind"] == "upload_file"
        assert body["needs_action"]["supply_url"] == f"/v1/jobs/{job['id']}/supply"
        events = await client.get(f"/v1/jobs/{job['id']}/events")
        assert "event: needs_user_action" in events.text
        supplied = await client.post(
            f"/v1/jobs/{job['id']}/supply", files={"file": ("transcript.txt", b"Supplied transcript.\n", "text/plain")}
        )
        assert supplied.status_code == 202, supplied.text
        assert supplied.json()["state"] == "queued"
        done = await wait_for_state(client, job["id"])
        assert done["state"] == "done", done
        result = await client.get(f"/v1/jobs/{job['id']}/result")
        assert "Supplied transcript." in result.text
