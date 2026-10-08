"""Fetch-node routes (docs/spec/part1.md 7.3, 7.4): absent without a secret, bearer + CIDR required,
claim tokens bound to one job."""

from __future__ import annotations

from pathlib import Path

import pytest

from intomd_api.testing import api_client, make_settings, use_in_process_isolation, wait_for_state

SECRET = "fetch-node-secret-0123456789"
AUTH = {"Authorization": f"Bearer {SECRET}"}
CLAIM = {"node_id": "pi-home-1", "capabilities": ["yt-dlp", "ffmpeg"], "max_duration_seconds": 10800}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    use_in_process_isolation(monkeypatch)


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
    settings = make_settings(tmp_path / "data", fetch_node_secret=SECRET, fetch_node_cidr="127.0.0.0/8")
    async with api_client(settings) as (client, _):
        assert (await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)).status_code == 204
        caps = (await client.get("/v1/capabilities")).json()
        assert caps["fetch_node_online"] is True
        created = await client.post(
            "/v1/convert", json={"url": "https://www.example.com/watch?v=abc", "prefer_residential": True}
        )
        job_id = created.json()["job"]["id"]
        claim = await client.post("/v1/fetch-node/claim", json=CLAIM, headers=AUTH)
        assert claim.status_code == 200, claim.text
        body = claim.json()
        assert body["job_id"] == job_id
        assert body["claim_token"].startswith("ct_")
        assert body["url"] == "https://www.example.com/watch?v=abc"
        assert body["upload_url"] == "/v1/fetch-node/upload"
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
    settings = make_settings(tmp_path / "data", fetch_node_secret=SECRET, fetch_node_cidr="127.0.0.0/8")
    async with api_client(settings) as (client, _):
        payload = {"url": "https://www.example.com/v/1", "prefer_residential": True}
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
