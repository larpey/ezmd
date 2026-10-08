"""Size caps, rate limits, admission control."""

from __future__ import annotations

from collections.abc import Callable

from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload, wait_for_state


async def test_413_over_cap_streaming(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_max_upload_mb=1)) as (client, _):
        limit = 1024 * 1024
        r = await upload(client, b"a" * (limit + 1), "big.txt")
        assert r.status_code == 413
        err = r.json()["error"]
        assert err["code"] == "input_too_large"
        assert err["detail"]["limit_bytes"] == limit
        assert err["detail"]["received_bytes"] > limit
        ok = await upload(client, b"a" * limit, "edge.txt")
        assert ok.status_code == 202


async def test_413_on_declared_content_length(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_max_upload_mb=1)) as (client, _):
        r = await client.post(
            "/v1/convert",
            content=b"--x--\r\n",
            headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(50 * 1024 * 1024)},
        )
        assert r.status_code == 413


async def test_429_with_headers(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_ratelimit_max=2, anon_ratelimit_window_s=60)) as (client, _):
        first = await upload(client, b"one\n", "1.txt")
        assert first.status_code == 202
        assert first.headers["x-ratelimit-limit"] == "2"
        assert first.headers["x-ratelimit-remaining"] == "1"
        assert int(first.headers["x-ratelimit-reset"]) > 0
        await upload(client, b"two\n", "2.txt")
        third = await upload(client, b"three\n", "3.txt")
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "rate_limited"
        assert third.headers["x-ratelimit-remaining"] == "0"
        assert int(third.headers["retry-after"]) >= 1


async def test_rate_limit_is_per_client_ip(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(anon_ratelimit_max=1)
    async with api_client(settings, client_addr=("203.0.113.5", 1)) as (a, _):
        assert (await upload(a, b"x\n", "a.txt")).status_code == 202
        assert (await upload(a, b"y\n", "b.txt")).status_code == 429
    async with api_client(settings, client_addr=("203.0.113.6", 1)) as (b, _):
        assert (await upload(b, b"z\n", "c.txt")).status_code == 202


async def test_result_fetch_rate_limited(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_result_ratelimit_max=1)) as (client, _):
        r = await upload(client, b"hello\n", "a.txt")
        job_id = r.json()["job"]["id"]
        await wait_for_state(client, job_id)
        assert (await client.get(f"/v1/jobs/{job_id}/result")).status_code == 200
        limited = await client.get(f"/v1/jobs/{job_id}/result")
        assert limited.status_code == 429
        assert "retry-after" in limited.headers


async def test_concurrency_admission(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_concurrency=1)) as (client, app):
        services = app.state.services
        r = await upload(client, b"first\n", "a.txt")
        job_id = r.json()["job"]["id"]
        await wait_for_state(client, job_id)
        services.jobs.update(job_id, state="converting")  # simulate a still-running job
        busy = await upload(client, b"second\n", "b.txt")
        assert busy.status_code == 429
        assert busy.json()["error"]["detail"]["concurrent_limit"] == 1


async def test_global_cap_returns_queue_unavailable(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(max_active_jobs=1)) as (client, app):
        r = await upload(client, b"first\n", "a.txt")
        job_id = r.json()["job"]["id"]
        await wait_for_state(client, job_id)
        app.state.services.jobs.update(job_id, state="converting")
        busy = await upload(client, b"second\n", "b.txt")
        assert busy.status_code == 503
        assert busy.json()["error"]["code"] == "queue_unavailable"
        assert busy.headers["retry-after"] == "30"
