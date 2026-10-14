"""ezmd_api.queue: queue routing and enqueue helpers (docs/spec/part1.md section 7.2).

The RQ payload is the job id only; workers load everything else from the job store. With
`EZMD_QUEUE=inline` jobs run on a small thread pool inside the API process (for `ezmd serve`
without Redis, and for tests). `fetch_residential` has no worker: fetch nodes claim those jobs
through `/v1/fetch-node/claim`, which reads them from the job store.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

log = logging.getLogger("ezmd.api.queue")

DEFAULT = "default"
MEDIA = "media"
FETCH = "fetch"
FETCH_RESIDENTIAL = "fetch_residential"
RQ_QUEUES = (DEFAULT, MEDIA, FETCH)
ALL_QUEUES = (DEFAULT, MEDIA, FETCH, FETCH_RESIDENTIAL)
WORKER_ENTRY = "ezmd_api.worker.rq_entry"
HEARTBEAT_MAX_AGE_S = 60
"""/readyz needs a worker heartbeat at most this old (docs/spec/part1.md section 7.3)."""
WORKER_TTL_S = 45
"""RQ `worker_ttl` for ezmd workers. An idle RQ worker beats once per dequeue timeout (worker_ttl - 15 s)
and a busy one every `job_monitoring_interval` (30 s), so both beat twice per readiness window. RQ's
default of 420 s left an idle worker silent for 405 s and /readyz answered 503 (D-0045)."""


# What the queue knows about one job (JobQueue.liveness), for the reaper's reconciliation.
WAITING = "waiting"
"""In a queue, not started by any worker."""
RUNNING = "running"
"""Started by a worker that is still heartbeating (or the backend cannot tell)."""
LOST = "lost"
"""The queue no longer holds the job, or its worker stopped heartbeating: nobody will finish it."""
UNKNOWN = "unknown"
"""The queue backend could not be asked (Redis down); the reaper does nothing."""


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

    def liveness(self, job_id: str, rq_job_id: str | None) -> str:
        """WAITING, RUNNING, LOST, or UNKNOWN (see the constants above)."""
        ...

    def cancel(self, job_id: str, rq_job_id: str | None) -> None:
        """Best effort: drop a queued job or stop a running one (`ezmd-admin jobs kill`)."""
        ...

    def shutdown(self) -> None: ...


class InlineQueue:
    """Runs jobs in-process on background threads. `runner(job_id)` is the worker entry."""

    mode = "inline"

    def __init__(self, runner: Callable[[str], None], max_workers: int = 2) -> None:
        self._runner = runner
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ezmd-inline")
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

    def liveness(self, job_id: str, rq_job_id: str | None) -> str:
        """Threads cannot be lost without the process, so anything not pending counts as running."""
        return WAITING if self.waiting(job_id, rq_job_id) else RUNNING

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
            description=f"ezmd {job_id}",
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
        return self.liveness(job_id, rq_job_id) == WAITING

    def liveness(self, job_id: str, rq_job_id: str | None) -> str:
        """From the RQ job: queued/deferred/scheduled is WAITING; started is RUNNING while the job's
        heartbeat (refreshed every `job_monitoring_interval` by its worker) is within HEARTBEAT_MAX_AGE_S,
        else LOST; missing (Redis restarted without persistence) or finished/failed/stopped is LOST."""
        from datetime import UTC, datetime

        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        if not rq_job_id:
            return LOST
        try:
            job = Job.fetch(rq_job_id, connection=self.redis)
            status = str(getattr(job.get_status(), "value", job.get_status()))
        except NoSuchJobError:
            return LOST
        except Exception:
            log.warning("could not read RQ job state", extra={"job_id": job_id})
            return UNKNOWN
        if status in ("queued", "deferred", "scheduled"):
            return WAITING
        if status != "started":
            return LOST
        hb = job.last_heartbeat
        if hb is None:
            return RUNNING
        hb = hb if hb.tzinfo else hb.replace(tzinfo=UTC)
        return RUNNING if (datetime.now(UTC) - hb).total_seconds() <= HEARTBEAT_MAX_AGE_S else LOST

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
        """At least one RQ worker heartbeated in the last HEARTBEAT_MAX_AGE_S (readiness)."""
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
            if (now - hb).total_seconds() <= HEARTBEAT_MAX_AGE_S:
                return True
        return False

    def shutdown(self) -> None:
        return None
