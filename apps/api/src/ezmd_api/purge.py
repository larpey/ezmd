"""ezmd_api.purge: retention purge and the residential-fetch reaper (docs/spec/part1.md 7.1, 7.2, 8.4).

`purge_expired()` deletes the blobs (prefix `jobs/{id}/`) and rows of jobs past `expires_at`.
`reap_residential()` returns expired fetch-node claims to the queue once and moves jobs that cannot
be fetched to `needs_user_action`. `reap_stale()` fails jobs whose worker stopped updating them for
longer than the queue's wall time (docs/spec/part4.md 4.11.3), and `clean_temp()` removes orphaned
job and upload temp directories. `Scheduler` runs the first three on a background thread; run
`python -m ezmd_api.purge` for one pass (or `--loop`) as its own process, or `ezmd-admin reap`.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from ezmd_api.blobs import job_prefix
from ezmd_api.db import JobRow
from ezmd_api.jobs import CONVERTING, EXPIRED, FETCHING, NEEDS_USER_ACTION, RENDERING, InvalidTransition, JobGone
from ezmd_api.util import as_utc, utcnow

if TYPE_CHECKING:
    from ezmd_api.services import Services

log = logging.getLogger("ezmd.api.purge")

REAPER_INTERVAL_SECONDS = 30.0
MAX_CLAIM_ATTEMPTS = 2
STALE_GRACE_SECONDS = 150
"""Added to a queue's timeout before a job nobody updates counts as abandoned (covers the 30 s kill grace)."""
TEMP_PREFIXES = ("ezmd-job-", "ezmd-upload-")
NO_NODE_REASON = "No residential fetch node is online and this site blocks datacenter requests."
UPLOAD_NEEDED = {
    "kind": "upload_file",
    "reason": "No residential fetch node could fetch this URL. Upload the file or use the browser extension.",
    "accept": ["audio/*", "video/*"],
    "alternatives": ["use_extension"],
}


def purge_job(services: Services, job_id: str) -> int:
    """Delete one job's blobs, events, and row now. Returns the number of blobs removed."""
    try:
        services.jobs.transition(job_id, EXPIRED)
    except (JobGone, InvalidTransition):
        pass
    removed = services.blobs.delete_prefix(job_prefix(job_id))
    services.jobs.delete(job_id)
    return removed


def purge_expired(services: Services) -> int:
    count = 0
    for job_id in services.jobs.expired_ids():
        try:
            purge_job(services, job_id)
            count += 1
        except Exception:
            log.exception("purge failed", extra={"job_id": job_id})
    if count:
        log.info("purged expired jobs", extra={"count": count})
    return count


def needs_upload(services: Services, job_id: str, reason: str | None = None) -> None:
    payload = dict(UPLOAD_NEEDED)
    if reason:
        payload["reason"] = reason
    try:
        services.jobs.transition(
            job_id,
            NEEDS_USER_ACTION,
            needs_action=json.dumps(payload),
            claim_token_hash=None,
            claim_expires_at=None,
        )
    except (JobGone, InvalidTransition):
        pass


def reap_residential(services: Services) -> int:
    now = utcnow()
    wait = timedelta(seconds=services.settings.residential_wait_seconds)
    nodes_online = bool(services.state.nodes_online())
    with services.db.session() as s:
        rows = list(
            s.execute(
                select(JobRow).where(JobRow.queue == "fetch_residential", JobRow.state == FETCHING).limit(500)
            ).scalars()
        )
    changed = 0
    for row in rows:
        if row.claim_expires_at is not None:
            if as_utc(row.claim_expires_at) > now:
                continue
            if row.claim_attempts < MAX_CLAIM_ATTEMPTS:
                services.jobs.update(row.id, claim_token_hash=None, claim_expires_at=None, claim_node_id=None)
            else:
                needs_upload(services, row.id)
            changed += 1
        elif not nodes_online and as_utc(row.updated_at) + wait <= now:
            needs_upload(services, row.id, NO_NODE_REASON)
            changed += 1
    return changed


def reap_stale(services: Services, *, now_grace: bool = False) -> int:
    """Fail fetching/converting/rendering jobs (not residential fetches, which `reap_residential` owns) whose
    row was not touched for longer than the queue's timeout plus STALE_GRACE_SECONDS: the worker died or
    hung past its own watchdog. `now_grace=True` drops the grace (operator `reap --now`)."""
    now = utcnow()
    with services.db.session() as s:
        rows = list(
            s.execute(
                select(JobRow)
                .where(JobRow.state.in_((FETCHING, CONVERTING, RENDERING)), JobRow.queue != "fetch_residential")
                .limit(1000)
            ).scalars()
        )
    reaped = 0
    for row in rows:
        limit = services.settings.queue_timeout(row.queue) + (0 if now_grace else STALE_GRACE_SECONDS)
        if as_utc(row.updated_at) + timedelta(seconds=limit) <= now:
            if services.queue.waiting(row.id, row.rq_job_id):
                continue  # handed off and still queued behind other work, not abandoned
            if services.jobs.fail(row.id, "timeout", "The conversion exceeded its time limit.") is not None:
                reaped += 1
    if reaped:
        log.info("reaped stale jobs", extra={"count": reaped})
    return reaped


def clean_temp(max_age_seconds: float, root: Path | None = None) -> int:
    """Remove ezmd job/upload temp directories older than `max_age_seconds`. Returns how many."""
    base = root or Path(tempfile.gettempdir())
    cutoff = time.time() - max_age_seconds
    removed = 0
    for prefix in TEMP_PREFIXES:
        for path in base.glob(prefix + "*"):
            try:
                if path.is_dir() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
                    removed += 1
            except OSError:
                log.debug("could not inspect temp dir %s", path.name)
    return removed


class Scheduler:
    """Background thread: residential reaper every 30 s, retention purge every EZMD_PURGE_INTERVAL_S."""

    def __init__(self, services: Services, heartbeat: Path | None = None) -> None:
        self.services = services
        self.heartbeat = heartbeat
        """When set, touched after every tick so a container healthcheck can verify the loop is alive."""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ezmd-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        last_purge = 0.0
        while not self._stop.is_set():
            try:
                reap_residential(self.services)
                reap_stale(self.services)
                if time.monotonic() - last_purge >= self.services.settings.purge_interval_s:
                    purge_expired(self.services)
                    last_purge = time.monotonic()
            except Exception:
                log.exception("scheduler tick failed")
            else:
                self._beat()
            self._stop.wait(REAPER_INTERVAL_SECONDS)

    def _beat(self) -> None:
        if self.heartbeat is None:
            return
        try:
            self.heartbeat.touch()
        except OSError:
            log.warning("could not write scheduler heartbeat %s", self.heartbeat)


def main(argv: list[str] | None = None) -> None:
    """`python -m ezmd_api.purge` runs one purge + reaper pass and exits (compose loops it);
    `--loop` keeps running on the Scheduler cadence instead."""
    import argparse

    from ezmd_api.logs import configure_logging
    from ezmd_api.services import build_services
    from ezmd_api.settings import Settings

    parser = argparse.ArgumentParser(prog="ezmd-purge", description="Purge expired ezmd jobs.")
    parser.add_argument("--loop", action="store_true", help="run forever instead of a single pass")
    parser.add_argument(
        "--heartbeat",
        type=Path,
        default=None,
        help="file touched after every successful tick (for container healthchecks)",
    )
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings)
    services = build_services(settings)
    services.db.ensure_schema()
    if not args.loop:
        reap_residential(services)
        reap_stale(services)
        purge_expired(services)
        services.close()
        return
    scheduler = Scheduler(services, heartbeat=args.heartbeat)
    scheduler.start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        scheduler.stop()


if __name__ == "__main__":
    main()
