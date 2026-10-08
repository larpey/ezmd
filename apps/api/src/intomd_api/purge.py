"""intomd_api.purge: retention purge and the residential-fetch reaper (docs/spec/part1.md 7.1, 7.2, 8.4).

`purge_expired()` deletes the blobs (prefix `jobs/{id}/`) and rows of jobs past `expires_at`.
`reap_residential()` returns expired fetch-node claims to the queue once and moves jobs that cannot
be fetched to `needs_user_action`. `Scheduler` runs both on a background thread; run
`python -m intomd_api.purge` for one pass (or `--loop`) as its own process instead.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from intomd_api.blobs import job_prefix
from intomd_api.db import JobRow
from intomd_api.jobs import EXPIRED, FETCHING, NEEDS_USER_ACTION, InvalidTransition, JobGone
from intomd_api.util import as_utc, utcnow

if TYPE_CHECKING:
    from intomd_api.services import Services

log = logging.getLogger("intomd.api.purge")

REAPER_INTERVAL_SECONDS = 30.0
MAX_CLAIM_ATTEMPTS = 2
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


class Scheduler:
    """Background thread: residential reaper every 30 s, retention purge every INTOMD_PURGE_INTERVAL_S."""

    def __init__(self, services: Services) -> None:
        self.services = services
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="intomd-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        last_purge = 0.0
        import time

        while not self._stop.is_set():
            try:
                reap_residential(self.services)
                if time.monotonic() - last_purge >= self.services.settings.purge_interval_s:
                    purge_expired(self.services)
                    last_purge = time.monotonic()
            except Exception:
                log.exception("scheduler tick failed")
            self._stop.wait(REAPER_INTERVAL_SECONDS)


def main(argv: list[str] | None = None) -> None:
    """`python -m intomd_api.purge` runs one purge + reaper pass and exits (compose loops it);
    `--loop` keeps running on the Scheduler cadence instead."""
    import argparse

    from intomd_api.logs import configure_logging
    from intomd_api.services import build_services
    from intomd_api.settings import Settings

    parser = argparse.ArgumentParser(prog="intomd-purge", description="Purge expired intomd jobs.")
    parser.add_argument("--loop", action="store_true", help="run forever instead of a single pass")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings)
    services = build_services(settings)
    services.db.create_all()
    if not args.loop:
        reap_residential(services)
        purge_expired(services)
        services.close()
        return
    scheduler = Scheduler(services)
    scheduler.start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        scheduler.stop()


if __name__ == "__main__":
    main()
