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


async def test_readyz_200_with_an_idle_worker(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    """Regression: an idle worker last beat ~400 s ago under RQ's default ttl, and /readyz said 503."""
    w = worker.build_worker([q.DEFAULT], redis)
    _registered_worker(redis, beat_age_s=w.dequeue_timeout)
    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, _app):
        r = await client.get("/readyz")
    assert r.status_code == 200, r.text
