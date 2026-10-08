"""intomd_api.queue: queue routing and enqueue helpers (docs/spec/part1.md section 7.2).

The RQ payload is the job id only; workers load everything else from the job store. With
`INTOMD_QUEUE=inline` jobs run on a small thread pool inside the API process (for `intomd serve`
without Redis, and for tests). `fetch_residential` has no worker: fetch nodes claim those jobs
through `/v1/fetch-node/claim`, which reads them from the job store.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

log = logging.getLogger("intomd.api.queue")

DEFAULT = "default"
MEDIA = "media"
FETCH = "fetch"
FETCH_RESIDENTIAL = "fetch_residential"
RQ_QUEUES = (DEFAULT, MEDIA, FETCH)
ALL_QUEUES = (DEFAULT, MEDIA, FETCH, FETCH_RESIDENTIAL)
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
    def waiting(self, job_id: str, rq_job_id: str | None) -> bool:
        """True while the job sits in a queue and no worker has started it (the reaper leaves it alone)."""
        ...

    def cancel(self, job_id: str, rq_job_id: str | None) -> None:
        """Best effort: drop a queued job or stop a running one (`intomd-admin jobs kill`)."""
        ...

    def shutdown(self) -> None: ...


class InlineQueue:
    """Runs jobs in-process on background threads. `runner(job_id)` is the worker entry."""

    mode = "inline"

    def __init__(self, runner: Callable[[str], None], max_workers: int = 2) -> None:
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="intomd-inline")
        self._lock = threading.Lock()
        self._pending: set[str] = set()

    def enqueue(self, job_id: str, queue: str, *, timeout_s: int) -> str | None:
        if queue == FETCH_RESIDENTIAL:
            return None
        with self._lock:
            self._pending.add(job_id)
        self._pool.submit(self._run, job_id)
        return None

    def waiting(self, job_id: str, rq_job_id: str | None) -> bool:
        with self._lock:
            return job_id in self._pending

    def cancel(self, job_id: str, rq_job_id: str | None) -> None:
        """A thread cannot be killed; the job's failed state makes the runner skip or abandon it."""
        with self._lock:
            self._pending.discard(job_id)

    def _run(self, job_id: str) -> None:
        with self._lock:
            self._pending.discard(job_id)
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

    def _job(self, rq_job_id: str | None) -> Any:
        if not rq_job_id:
            return None
        from rq.job import Job

        try:
            return Job.fetch(rq_job_id, connection=self.redis)
        except Exception:
            return None

    def waiting(self, job_id: str, rq_job_id: str | None) -> bool:
        job = self._job(rq_job_id)
        if job is None:
            return False
        try:
            status = str(getattr(job.get_status(), "value", job.get_status()))
        except Exception:
            return False
        return status in ("queued", "deferred", "scheduled")

    def cancel(self, job_id: str, rq_job_id: str | None) -> None:
        job = self._job(rq_job_id)
        if job is None:
            return
        try:
            status = str(getattr(job.get_status(), "value", job.get_status()))
            if status == "started":
                from rq.command import send_stop_job_command

                send_stop_job_command(self.redis, job.id)
            else:
                job.cancel()
        except Exception:
            log.warning("could not cancel RQ job", extra={"job_id": job_id})

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
