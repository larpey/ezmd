"""RQ mode with fakeredis: enqueue payloads, queue routing, 409 before done, Redis-backed state."""

from __future__ import annotations

import json
from collections.abc import Callable

import fakeredis
import pytest

from intomd_api import queue as q
from intomd_api.settings import Settings
from intomd_api.state import EVENT_BUFFER_CAP, RedisState
from intomd_api.testing import api_client, upload
from intomd_api.worker import process_job


@pytest.fixture
def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


async def test_enqueue_payload_is_job_id_only(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    from rq import Queue

    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, app):
        r = await upload(client, b"hello rq\n", "a.txt")
        assert r.status_code == 202
        job_id = r.json()["job"]["id"]
        rq_jobs = Queue("default", connection=redis).get_jobs()
        assert len(rq_jobs) == 1
        assert rq_jobs[0].func_name == q.WORKER_ENTRY
        assert rq_jobs[0].args == (job_id,)
        assert rq_jobs[0].kwargs == {}
        row = app.state.services.jobs.get(job_id)
        assert row.rq_job_id == rq_jobs[0].id


async def test_409_before_done_then_worker_finishes(
    settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis
) -> None:
    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, app):
        r = await upload(client, b"# Title\n\nbody\n", "a.md", content_type="text/markdown")
        job_id = r.json()["job"]["id"]
        early = await client.get(f"/v1/jobs/{job_id}/result")
        assert early.status_code == 409
        err = early.json()["error"]
        assert err["code"] == "job_not_ready"
        assert err["detail"] == {"state": "queued"}
        process_job(app.state.services, job_id)  # what the RQ worker would run
        done = await client.get(f"/v1/jobs/{job_id}/result")
        assert done.status_code == 200
        assert "Title" in done.text
        events = await client.get(f"/v1/jobs/{job_id}/events")
        assert "event: done" in events.text


async def test_readyz_needs_a_worker(settings_factory: Callable[..., Settings], redis: fakeredis.FakeRedis) -> None:
    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, _):
        r = await client.get("/readyz")
        assert r.status_code == 503
        assert r.json()["checks"] == {"database": True, "state": True, "workers": False}


async def test_readyz_inline_ready(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory()) as (client, _):
        r = await client.get("/readyz")
        assert r.status_code == 200
        assert (await client.get("/healthz")).json() == {"status": "ok"}


def test_queue_routing() -> None:
    assert q.queue_for_mime("audio/mpeg") == q.MEDIA
    assert q.queue_for_mime("video/mp4") == q.MEDIA
    assert q.queue_for_mime("application/pdf") == q.DEFAULT
    assert q.queue_for_mime(None) == q.DEFAULT
    assert q.queue_for_url(False) == q.FETCH
    assert q.queue_for_url(True) == q.FETCH_RESIDENTIAL


def test_redis_sliding_window(redis: fakeredis.FakeRedis) -> None:
    state = RedisState(redis)
    results = [state.rate_hit("k", 3, 60) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert [r.remaining for r in results] == [2, 1, 0, 0]
    assert results[-1].retry_after >= 1
    assert redis.zcard("intomd:rl:k") == 3


def test_redis_event_buffer_capped_and_published(redis: fakeredis.FakeRedis) -> None:
    state = RedisState(redis)
    sub = state.subscribe("job_x")
    for i in range(EVENT_BUFFER_CAP + 20):
        state.append_event("job_x", "progress", {"progress": i % 100, "stage_message": "x"})
    events = state.events_since("job_x", 0)
    assert len(events) == EVENT_BUFFER_CAP
    assert events[0].id == 21 and events[-1].id == EVENT_BUFFER_CAP + 20
    assert sub.wait(1.0) is True
    sub.close()
    tail = [e.id for e in state.events_since("job_x", EVENT_BUFFER_CAP + 18)]
    assert tail == [EVENT_BUFFER_CAP + 19, EVENT_BUFFER_CAP + 20]
    raw = redis.lrange("intomd:job:job_x:events", -1, -1)[0]
    assert json.loads(raw)["event"] == "progress"


def test_redis_gauges_and_nodes(redis: fakeredis.FakeRedis) -> None:
    state = RedisState(redis)
    assert state.gauge_incr("g", 60) == 1
    assert state.gauge_incr("g", 60) == 2
    state.gauge_decr("g")
    state.gauge_decr("g")
    state.gauge_decr("g")
    assert int(redis.get("intomd:gauge:g")) == 0
    assert state.nodes_online() == []
    state.node_heartbeat("pi-1", {"capabilities": ["yt-dlp"]})
    assert state.nodes_online() == ["pi-1"]
