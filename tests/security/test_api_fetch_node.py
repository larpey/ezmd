"""Fetch-node routes (docs/spec/part1.md 7.3, 7.4): absent without a secret, bearer + CIDR required,
claim tokens bound to one job."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from intomd_api.routes import fetch_node
from intomd_api.settings import Settings
from intomd_api.testing import api_client, make_settings, use_in_process_isolation, wait_for_state

SECRET = "fetch-node-secret-0123456789"
AUTH = {"Authorization": f"Bearer {SECRET}"}
CLAIM = {"node_id": "pi-home-1", "capabilities": ["yt-dlp", "ffmpeg"], "max_duration_seconds": 10800}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    use_in_process_isolation(monkeypatch)
    monkeypatch.setattr(fetch_node, "RESOLVER", lambda host, port: ["93.184.216.34"])


def _node_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Fetch-node settings with a policy that makes video.example.com residential_only."""
    policy = tmp_path / "platforms.toml"
    policy.write_text("[hosts]" + chr(10) + '"video.example.com" = "residential_only"' + chr(10), encoding="utf-8")
    values: dict[str, Any] = {"fetch_node_secret": SECRET, "fetch_node_cidr": "127.0.0.0/8", "platforms_file": policy}
    values.update(overrides)
    return make_settings(tmp_path / "data", **values)


async def test_routes_absent_without_secret(tmp_path: Path) -> None:
    async with api_client(make_settings(tmp_path / "data")) as (client, app):
        for path in ("claim", "heartbeat", "upload", "fail"):
            r = await client.post(f"/v1/fetch-node/{path}", json={}, headers=AUTH)
            assert r.status_code == 404, path
        assert not any("/fetch-node/" in getattr(r, "path", "") for r in app.routes)


async def test_wrong_or_missing_secret_401(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data", fetch_node_secret=SECRET, fetch_node_cidr="127.0.0.0/8")
    async with api_client(settings) as (client, _):
        for headers in ({}, {"Authorization": "Bearer wrong-secret-xxxxxxxx"}, {"Authorization": SECRET}):
            r = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=headers)
            assert r.status_code == 401
            assert r.json()["error"]["code"] == "unauthorized"


async def test_right_secret_wrong_network_403(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data", fetch_node_secret=SECRET)  # default CIDR 100.64.0.0/10
    async with api_client(settings, client_addr=("203.0.113.1", 1)) as (client, _):
        r = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)
        assert r.status_code == 403
    async with api_client(settings, client_addr=("100.101.102.103", 1)) as (client, _):
        r = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)
        assert r.status_code == 204


async def test_claim_upload_flow(tmp_path: Path) -> None:
    async with api_client(_node_settings(tmp_path)) as (client, _):
        assert (await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)).status_code == 204
        caps = (await client.get("/v1/capabilities")).json()
        assert caps["fetch_node_online"] is True
        created = await client.post("/v1/convert", json={"url": "https://video.example.com/watch?v=abc"})
        job_id = created.json()["job"]["id"]
        claim = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)
        assert claim.status_code == 200, claim.text
        body = claim.json()
        assert body["job_id"] == job_id
        assert body["claim_token"].startswith("ct_")
        assert body["url"] == "https://video.example.com/watch?v=abc"
        assert body["upload_url"] == "/v1/fetch-node/upload"
        assert body["platform"] == "video.example.com"
        assert body["resolved_ip"] == "93.184.216.34"
        # The same job is not handed out twice while claimed.
        assert (await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)).status_code == 204
        hb = await client.post(
            "/v1/fetch-node/heartbeat", json={"node_id": "pi-home-1", "claim_token": body["claim_token"]}, headers=AUTH
        )
        assert hb.status_code == 204
        forged = await client.post(
            "/v1/fetch-node/upload",
            data={"claim_token": "ct_forgedforgedforged"},
            files={"media": ("a.txt", b"x", "text/plain")},
            headers=AUTH,
        )
        assert forged.status_code == 403
        up = await client.post(
            "/v1/fetch-node/upload",
            data={"claim_token": body["claim_token"], "meta": '{"title": "Clip"}'},
            files={"media": ("captions.txt", b"Residential transcript text.\n", "text/plain")},
            headers=AUTH,
        )
        assert up.status_code == 202, up.text
        done = await wait_for_state(client, job_id)
        assert done["state"] == "done", done
        reuse = await client.post(
            "/v1/fetch-node/fail", json={"claim_token": body["claim_token"], "reason_code": "x"}, headers=AUTH
        )
        assert reuse.status_code == 403


async def test_fail_returns_job_once_then_needs_user_action(tmp_path: Path) -> None:
    async with api_client(_node_settings(tmp_path)) as (client, _):
        payload = {"url": "https://video.example.com/v/1"}
        created = await client.post("/v1/convert", json=payload)
        job_id = created.json()["job"]["id"]
        for attempt in (1, 2):
            claim = (await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)).json()
            assert claim["job_id"] == job_id, attempt
            r = await client.post(
                "/v1/fetch-node/fail",
                json={"claim_token": claim["claim_token"], "reason_code": "bot_check"},
                headers=AUTH,
            )
            assert r.status_code == 204
        body = (await client.get(f"/v1/jobs/{job_id}")).json()
        assert body["state"] == "needs_user_action"
        assert "bot_check" in body["needs_action"]["reason"]


async def test_claim_rate_limited_per_node(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path / "data", fetch_node_secret=SECRET, fetch_node_cidr="127.0.0.0/8", fetch_node_claims_per_minute=2
    )
    async with api_client(settings) as (client, _):
        codes = [(await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)).status_code for _ in range(3)]
        assert codes == [204, 204, 429]


async def test_anonymous_prefer_residential_never_reaches_a_node(tmp_path: Path) -> None:
    """D-0017 item 6: anonymous prefer_residential on a default-policy host is ignored."""
    async with api_client(_node_settings(tmp_path)) as (client, _):
        created = await client.post(
            "/v1/convert", json={"url": "https://www.example.com/lan", "prefer_residential": True}
        )
        assert created.status_code == 202
        assert created.json()["job"]["queue"] != "fetch_residential"
        assert (await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)).status_code == 204


async def test_claim_fails_job_whose_host_now_resolves_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with api_client(_node_settings(tmp_path)) as (client, _):
        created = await client.post("/v1/convert", json={"url": "https://video.example.com/rebind"})
        job_id = created.json()["job"]["id"]
        monkeypatch.setattr(fetch_node, "RESOLVER", lambda host, port: ["192.168.1.10"])
        claim = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)
        assert claim.status_code == 204
        body = (await client.get(f"/v1/jobs/{job_id}")).json()
        assert body["state"] == "failed"
        assert body["error"]["code"] == "url_blocked"
        assert "192.168" not in str(body)


async def test_claim_without_dns_answer_has_null_ip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_dns(host: str, port: int) -> list[str]:
        raise OSError("no network")

    monkeypatch.setattr(fetch_node, "RESOLVER", no_dns)
    async with api_client(_node_settings(tmp_path)) as (client, _):
        created = await client.post("/v1/convert", json={"url": "https://video.example.com/x"})
        claim = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)
        assert claim.status_code == 200
        assert claim.json()["job_id"] == created.json()["job"]["id"]
        assert claim.json()["resolved_ip"] is None
        assert claim.json()["platform"] == "video.example.com"
