"""Idempotency and deduplication (docs/spec/part1.md section 7.1)."""

from __future__ import annotations

from collections.abc import Callable

import httpx

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
    settings = settings_factory(public_mode=True, jwt_secret=secret, key_pepper=secret)
    async with api_client(settings, client_addr=("198.51.100.1", 1)) as (a, _):
        job_id = await _done(a)
        same_ip = await upload(a, BODY, "a.txt")
        assert same_ip.json()["job"]["id"] == job_id
    async with api_client(settings, client_addr=("198.51.100.2", 1)) as (b, _):
        other_ip = await upload(b, BODY, "a.txt")
        assert other_ip.status_code == 202
        assert other_ip.json()["deduplicated"] is False
        assert other_ip.json()["job"]["id"] != job_id


async def test_self_host_dedups_across_ips(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory()
    async with api_client(settings, client_addr=("198.51.100.1", 1)) as (a, _):
        job_id = await _done(a)
    async with api_client(settings, client_addr=("198.51.100.2", 1)) as (b, _):
        assert (await upload(b, BODY, "a.txt")).json()["job"]["id"] == job_id


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
