"""Worker heartbeats vs readiness, and the reaper's reconciliation with RQ (S1/S2, D-0045)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis
import pytest

from ezmd_api import queue as q
from ezmd_api import worker
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client


@pytest.fixture
def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


def _registered_worker(redis: fakeredis.FakeRedis, beat_age_s: float) -> Any:
    w = worker.build_worker([q.DEFAULT], redis)
    w.register_birth()
    stamp = datetime.now(UTC) - timedelta(seconds=beat_age_s)
    redis.hset(w.key, "last_heartbeat", stamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    return w


def test_workers_beat_well_inside_the_readiness_window(redis: fakeredis.FakeRedis) -> None:
    """An idle RQ worker beats once per dequeue timeout (worker_ttl - 15 s); a busy one every
    job_monitoring_interval. Both must be shorter than the window /readyz accepts."""
    w = worker.build_worker([q.DEFAULT], redis)
    assert w.worker_ttl == q.WORKER_TTL_S
    assert w.dequeue_timeout < q.HEARTBEAT_MAX_AGE_S
    assert w.job_monitoring_interval < q.HEARTBEAT_MAX_AGE_S
    # The worker key must outlive the window, or a live worker vanishes from Worker.all() first.
    assert w.worker_ttl + 60 > q.HEARTBEAT_MAX_AGE_S


def test_idle_worker_just_before_its_next_beat_is_alive(redis: fakeredis.FakeRedis) -> None:
    idle_gap = worker.build_worker([q.DEFAULT], redis).dequeue_timeout + 5
    _registered_worker(redis, beat_age_s=idle_gap)
    assert q.RQQueue(redis).workers_alive() is True


def test_worker_silent_past_the_window_is_dead(redis: fakeredis.FakeRedis) -> None:
    _registered_worker(redis, beat_age_s=q.HEARTBEAT_MAX_AGE_S + 5)
    assert q.RQQueue(redis).workers_alive() is False


def test_worker_reregisters_after_redis_loses_its_registry(redis: fakeredis.FakeRedis) -> None:
    """B2b: Redis restarted without persistence; RQ's worker set is gone and a plain heartbeat only
    rewrites the worker hash, so Worker.all() stays empty and /readyz says 503 until a worker restarts."""
    w = worker.build_worker([q.DEFAULT], redis)
    w.register_birth()
    redis.flushall()
    assert q.RQQueue(redis).workers_alive() is False
    w.heartbeat()
    assert q.RQQueue(redis).workers_alive() is True


async def test_readyz_200_with_an_idle_worker(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    """Regression: an idle worker last beat ~400 s ago under RQ's default ttl, and /readyz said 503."""
    w = worker.build_worker([q.DEFAULT], redis)
    _registered_worker(redis, beat_age_s=w.dequeue_timeout)
    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, _app):
        r = await client.get("/readyz")
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Reaper reconciliation with RQ
# ---------------------------------------------------------------------------


async def _job(client: Any) -> str:
    from ezmd_api.testing import upload

    r = await upload(client, b"reconcile me\n", "r.txt")
    assert r.status_code == 202, r.text
    job_id: str = r.json()["job"]["id"]
    return job_id


def _age(services: Any, job_id: str, seconds: float, **fields: Any) -> None:
    from ezmd_api.db import JobRow
    from ezmd_api.util import utcnow

    with services.db.session() as s:
        row = s.get(JobRow, job_id)
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = utcnow() - timedelta(seconds=seconds)


def _rq_job(services: Any, job_id: str) -> Any:
    from rq.job import Job

    row = services.jobs.require(job_id)
    return Job.fetch(row.rq_job_id, connection=services.redis)


def _started(services: Any, job_id: str, beat_age_s: float) -> None:
    from rq.job import JobStatus

    job = _rq_job(services, job_id)
    job.set_status(JobStatus.STARTED)
    job.heartbeat(datetime.now(UTC) - timedelta(seconds=beat_age_s), 600)


async def test_queued_job_missing_from_rq_is_requeued(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    """S1: Redis restarted (no persistence) and the RQ job is gone; the row would sit queued forever."""
    from rq import Queue

    from ezmd_api.purge import reconcile_queue

    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, app):
        services = app.state.services
        job_id = await _job(client)
        old_rq_id = services.jobs.require(job_id).rq_job_id
        redis.flushall()
        _age(services, job_id, q.HEARTBEAT_MAX_AGE_S + 1)
        assert reconcile_queue(services) == 1
        row = services.jobs.require(job_id)
        assert row.state == "queued"
        assert row.rq_job_id and row.rq_job_id != old_rq_id
        assert [j.args for j in Queue("default", connection=redis).get_jobs()] == [(job_id,)]


async def test_started_job_with_a_dead_worker_fails_fast_and_frees_the_slot(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    """S2: the worker died mid-job; fail within ~a minute instead of the queue timeout plus 150 s."""
    from ezmd_api.purge import reconcile_queue

    async with api_client(settings_factory(queue="rq", anon_concurrency=1), redis_client=redis) as (client, app):
        services = app.state.services
        job_id = await _job(client)
        _age(services, job_id, q.HEARTBEAT_MAX_AGE_S + 1, state="converting")
        _started(services, job_id, beat_age_s=q.HEARTBEAT_MAX_AGE_S + 30)
        assert reconcile_queue(services) == 1
        row = services.jobs.require(job_id)
        assert row.state == "failed"
        assert row.error_code == "internal_error"
        assert services.jobs.count_active() == 0
        again = await _job(client)  # the caller's concurrency slot is free again
        assert again != job_id


async def test_started_job_missing_from_rq_fails(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    from ezmd_api.purge import reconcile_queue

    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, app):
        services = app.state.services
        job_id = await _job(client)
        redis.flushall()
        _age(services, job_id, q.HEARTBEAT_MAX_AGE_S + 1, state="converting")
        assert reconcile_queue(services) == 1
        assert services.jobs.require(job_id).state == "failed"


@pytest.mark.parametrize("case", ["live_worker", "still_queued", "recently_touched"])
async def test_reconcile_leaves_healthy_jobs_alone(
    case: str, settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    from ezmd_api.purge import reconcile_queue

    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, app):
        services = app.state.services
        job_id = await _job(client)
        if case == "live_worker":
            _age(services, job_id, 600, state="converting")
            _started(services, job_id, beat_age_s=5)
        elif case == "still_queued":
            _age(services, job_id, 3600)  # a long backlog: RQ still has it queued
        else:
            redis.flushall()  # missing from RQ, but the row changed moments ago (enqueue in flight)
        assert reconcile_queue(services) == 0
        assert services.jobs.require(job_id).state in ("queued", "converting")
