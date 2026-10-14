"""Admission: the concurrency race, keyed headroom under the global cap, and the per-caller upload slot
(red-team uploads/ratelimit findings, D-0062)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import fakeredis
import pytest

from ezmd_api import ratelimit
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload


def _active_row(services: Any, *, ip_hash: str, key_id: str | None = None) -> str:
    from datetime import timedelta

    from ezmd_api.db import JobRow
    from ezmd_api.util import new_job_id, utcnow

    now = utcnow()
    row = JobRow(
        id=new_job_id(),
        state="converting",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
        client_ip_hash=ip_hash,
        api_key_id=key_id,
        input_kind="bytes",
        input_display="other.txt",
        profile="full",
        options_json="{}",
        queue="default",
        progress=0,
        stage_message="Converting",
        warnings_count=0,
        truncated=False,
        claim_attempts=0,
    )
    services.jobs.create(row)
    return str(row.id)


async def test_concurrent_request_that_passed_the_precheck_is_refused_after_insert(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    """Two parallel uploads both passed count_active before either row existed (2 jobs at concurrency 1).
    Admission is now re-checked after the row is inserted; the loser's row is removed."""
    async with api_client(settings_factory(queue="rq", anon_concurrency=1), redis_client=fakeredis.FakeRedis()) as (
        client,
        app,
    ):
        services = app.state.services
        real = ratelimit.admit_job

        def precheck_then_race(request: Any, caller: Any, **kw: Any) -> None:
            real(request, caller, **kw)
            if not kw.get("created"):
                _active_row(services, ip_hash=caller.ip_hash)  # the other request lands its row now

        monkeypatch.setattr("ezmd_api.routes.convert.admit_job", precheck_then_race)
        r = await upload(client, b"racing\n", "race.txt")
        assert r.status_code == 429, r.text
        assert r.json()["error"]["detail"]["reason"] == "concurrency"
        assert services.jobs.count_active() == 1  # only the other request's job survives


async def test_url_path_rechecks_after_insert_too(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    async with api_client(settings_factory(queue="rq", anon_concurrency=1), redis_client=fakeredis.FakeRedis()) as (
        client,
        app,
    ):
        services = app.state.services
        real = ratelimit.admit_job

        def precheck_then_race(request: Any, caller: Any, **kw: Any) -> None:
            real(request, caller, **kw)
            if not kw.get("created"):
                _active_row(services, ip_hash=caller.ip_hash)

        monkeypatch.setattr("ezmd_api.routes.convert.admit_job", precheck_then_race)
        r = await client.post("/v1/convert", json={"url": "https://example.com/a.txt"})
        assert r.status_code == 429, r.text
        assert services.jobs.count_active() == 1


async def test_anonymous_traffic_leaves_headroom_for_keyed_callers(settings_factory: Callable[..., Settings]) -> None:
    from ezmd_api.auth import create_api_key

    settings = settings_factory(queue="rq", max_active_jobs=3)
    assert settings.anon_active_job_cap == 2
    async with api_client(settings, redis_client=fakeredis.FakeRedis()) as (client, app):
        services = app.state.services
        _active_row(services, ip_hash="ip-a")
        _active_row(services, ip_hash="ip-b")
        anon = await upload(client, b"anonymous\n", "a.txt")
        assert anon.status_code == 503
        assert anon.json()["error"]["code"] == "queue_unavailable"
        key, _ = create_api_key(services.db, services.settings, "ci", env="test")
        keyed = await upload(client, b"keyed\n", "k.txt", headers={"X-API-Key": key})
        assert keyed.status_code == 202, keyed.text


async def test_upload_slot_refuses_a_second_parallel_upload_before_reading_it(
    settings_factory: Callable[..., Settings],
) -> None:
    from ezmd_api.auth import hash_ip

    async with api_client(settings_factory(queue="rq", anon_concurrency=1), redis_client=fakeredis.FakeRedis()) as (
        client,
        app,
    ):
        services = app.state.services
        state = services.state
        slot = ratelimit.upload_slot_key(f"ip:{hash_ip(services.settings, '127.0.0.1')}")

        def held() -> int:
            value = state.gauge_incr(slot, 60) - 1
            state.gauge_decr(slot)
            return value

        ok = await upload(client, b"first\n", "a.txt")
        assert ok.status_code == 202
        assert held() == 0  # released once the body was handled
        services.jobs.fail(ok.json()["job"]["id"], "internal_error", "test")  # free the concurrency slot
        state.gauge_incr(slot, 60)  # another upload from this caller is still streaming
        busy = await upload(client, b"second\n", "b.txt")
        assert busy.status_code == 429
        assert busy.json()["error"]["detail"]["reason"] == "upload_in_progress"
        assert held() == 1  # the refused request did not take or leak a slot
