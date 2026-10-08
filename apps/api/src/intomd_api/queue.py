"""intomd_api.queue: queue routing and enqueue helpers (docs/spec/part1.md section 7.2).

The RQ payload is the job id only; workers load everything else from the job store. With
`INTOMD_QUEUE=inline` jobs run on a small thread pool inside the API process (for `intomd serve`
without Redis, and for tests). `fetch_residential` has no worker: fetch nodes claim those jobs
through `/v1/fetch-node/claim`, which reads them from the job store.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

log = logging.getLogger("intomd.api.queue")

DEFAULT = "default"
MEDIA = "media"
FETCH = "fetch"
FETCH_RESIDENTIAL = "fetch_residential"
RQ_QUEUES = (DEFAULT, MEDIA, FETCH)
WORKER_ENTRY = "intomd_api.worker.rq_entry"


def queue_for_mime(mime: str | None) -> str:
    """Route by mime family: audio and video go to `media`, everything else to `default`."""
    family = (mime or "").split("/", 1)[0]
    return MEDIA if family in ("audio", "video") else DEFAULT


def queue_for_url(prefer_residential: bool) -> str:
    return FETCH_RESIDENTIAL if prefer_residential else FETCH


class JobQueue(Protocol):
    mode: str

    def enqueue(self, job_id: str, queue: str, *, timeout_s: int) -> str | None: ...
    def workers_alive(self) -> bool: ...
    def shutdown(self) -> None: ...


class InlineQueue:
    """Runs jobs in-process on background threads. `runner(job_id)` is the worker entry."""

    mode = "inline"

    def __init__(self, runner: Callable[[str], None], max_workers: int = 2) -> None:
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="intomd-inline")

    def enqueue(self, job_id: str, queue: str, *, timeout_s: int) -> str | None:
        if queue == FETCH_RESIDENTIAL:
            return None
        self._pool.submit(self._run, job_id)
        return None

    def _run(self, job_id: str) -> None:
        try:
            self._runner(job_id)
        except Exception:
            log.exception("inline job crashed", extra={"job_id": job_id})

    def workers_alive(self) -> bool:
        return True

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)


class RQQueue:
    mode = "rq"

    def __init__(self, redis: Any) -> None:
        self.redis = redis

    def enqueue(self, job_id: str, queue: str, *, timeout_s: int) -> str | None:
        if queue == FETCH_RESIDENTIAL:
            return None
        from rq import Queue

        q = Queue(queue, connection=self.redis)
        job = q.enqueue(
            WORKER_ENTRY,
            job_id,
            job_timeout=timeout_s + 60,
            result_ttl=0,
            failure_ttl=24 * 3600,
            description=f"intomd {job_id}",
        )
        return str(job.id)

    def workers_alive(self) -> bool:
        """At least one RQ worker heartbeated in the last 60 s (readiness)."""
        from datetime import UTC, datetime

        from rq import Worker

        try:
            workers = Worker.all(connection=self.redis)
        except Exception:
            return False
        now = datetime.now(UTC)
        for w in workers:
            hb = w.last_heartbeat
            if hb is None:
                continue
            hb = hb if hb.tzinfo else hb.replace(tzinfo=UTC)
            if (now - hb).total_seconds() <= 60:
                return True
        return False

    def shutdown(self) -> None:
        return None
