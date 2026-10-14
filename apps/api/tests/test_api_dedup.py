"""Idempotency and deduplication (docs/spec/part1.md section 7.1)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload, wait_for_state

BODY = b"Dedup me please.\n"


async def _done(client: httpx.AsyncClient, data: bytes = BODY, **kw: object) -> str:
    r = await upload(client, data, "a.txt", **kw)  # type: ignore[arg-type]
    assert r.status_code == 202, r.text
    job_id = str(r.json()["job"]["id"])
    headers = kw.get("headers")
    assert (await wait_for_state(client, job_id, headers=headers))["state"] == "done"  # type: ignore[arg-type]
    return job_id


async def test_dedup_returns_same_job(client: httpx.AsyncClient) -> None:
    job_id = await _done(client)
    again = await upload(client, BODY, "renamed.txt")
    assert again.status_code == 200
    assert again.json()["deduplicated"] is True
    assert again.json()["job"]["id"] == job_id


async def test_dedup_respects_options_and_profile(client: httpx.AsyncClient) -> None:
    job_id = await _done(client)
    other = await upload(client, BODY, "a.txt", options={"profile": "compact"})
    assert other.status_code == 202
    assert other.json()["job"]["id"] != job_id
    other2 = await upload(client, BODY, "a.txt", options={"max_pages": 5})
    assert other2.json()["job"]["id"] != job_id


async def test_idempotency_key(client: httpx.AsyncClient) -> None:
    first = await upload(client, b"one\n", "a.txt", headers={"Idempotency-Key": "abc-123"})
    second = await upload(client, b"different body\n", "b.txt", headers={"Idempotency-Key": "abc-123"})
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    third = await upload(client, b"one\n", "a.txt", headers={"Idempotency-Key": "other"})
    assert third.json()["job"]["id"] != first.json()["job"]["id"]


async def test_public_mode_no_dedup_across_ips(settings_factory: Callable[..., Settings]) -> None:
    secret = "x" * 32
    settings = settings_factory(public_mode=True, jwt_secret=secret, key_pepper=secret, turnstile_secret="ts-secret")
    async with api_client(settings, client_addr=("198.51.100.1", 1)) as (a, _):
        job_id = await _done(a)
        same_ip = await upload(a, BODY, "a.txt")
        assert same_ip.json()["job"]["id"] == job_id
    async with api_client(settings, client_addr=("198.51.100.2", 1)) as (b, _):
        other_ip = await upload(b, BODY, "a.txt")
        assert other_ip.status_code == 202
        assert other_ip.json()["deduplicated"] is False
        assert other_ip.json()["job"]["id"] != job_id


async def test_self_host_never_dedups_anonymous_callers_across_ips(settings_factory: Callable[..., Settings]) -> None:
    """F2 (D-0061): with public mode off, anonymous B got anonymous A's job id and filename back, and the id
    is the capability (B could read or DELETE A's job). Anonymous dedup is scoped to the client IP hash."""
    settings = settings_factory()
    async with api_client(settings, client_addr=("198.51.100.1", 1)) as (a, _):
        r = await upload(a, BODY, "secret-plan.txt")
        job_id = r.json()["job"]["id"]
        assert (await wait_for_state(a, job_id))["state"] == "done"
        assert (await upload(a, BODY, "again.txt")).json()["job"]["id"] == job_id  # same caller still dedups
    async with api_client(settings, client_addr=("198.51.100.2", 1)) as (b, _):
        other = await upload(b, BODY, "mine.txt")
        assert other.status_code == 202
        assert other.json()["deduplicated"] is False
        assert other.json()["job"]["id"] != job_id
        assert "secret-plan" not in other.text


async def test_self_host_url_dedup_is_per_ip(
    settings_factory: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    from ezmd.core import netguard
    from ezmd.core.netguard import FetchResult

    def fetch(url: str, **kwargs: object) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            headers={"content-type": "text/plain"},
            body=b"public page\n",
            resolved_ip="93.184.216.34",
            redirects=[],
            duration_seconds=0.01,
        )

    monkeypatch.setattr(netguard, "fetch", fetch)
    settings = settings_factory()
    payload = {"url": "https://example.com/page.txt"}
    async with api_client(settings, client_addr=("198.51.100.1", 1)) as (a, _):
        job_id = (await a.post("/v1/convert", json=payload)).json()["job"]["id"]
        assert (await wait_for_state(a, job_id))["state"] == "done"
    async with api_client(settings, client_addr=("198.51.100.2", 1)) as (b, _):
        assert (await b.post("/v1/convert", json=payload)).json()["job"]["id"] != job_id


async def test_dedup_never_crosses_api_keys(settings_factory: Callable[..., Settings]) -> None:
    from ezmd_api.auth import create_api_key

    async with api_client(settings_factory()) as (client, app):
        services = app.state.services
        k1, _ = create_api_key(services.db, services.settings, "one", env="test")
        k2, _ = create_api_key(services.db, services.settings, "two", env="test")
        job_id = await _done(client, headers={"X-API-Key": k1})
        other = await upload(client, BODY, "a.txt", headers={"X-API-Key": k2})
        assert other.status_code == 202
        assert other.json()["job"]["id"] != job_id
        anon = await upload(client, BODY, "a.txt")
        assert anon.json()["job"]["id"] != job_id
        # The job is bound to its key: other keys and anonymous callers cannot see it.
        assert (await client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": k2})).status_code == 404
        assert (await client.get(f"/v1/jobs/{job_id}")).status_code == 404
        assert (await client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": k1})).status_code == 200
