"""ezmd_api.jobs: the job store, its state machine, and progress events
(docs/spec/part1.md sections 7.1 and 7.2).

Every state change and progress write goes through `JobStore`, which persists the row and appends
a numbered event to the per-job buffer (published on `ezmd:job:{id}`), so SSE clients never poll
the database.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from ezmd_api.db import Database, JobRow
from ezmd_api.state import StateBackend
from ezmd_api.util import utcnow

QUEUED = "queued"
FETCHING = "fetching"
CONVERTING = "converting"
RENDERING = "rendering"
DONE = "done"
FAILED = "failed"
NEEDS_USER_ACTION = "needs_user_action"
EXPIRED = "expired"

STATES = (QUEUED, FETCHING, CONVERTING, RENDERING, DONE, FAILED, NEEDS_USER_ACTION, EXPIRED)
ACTIVE_STATES = (QUEUED, FETCHING, CONVERTING, RENDERING)
TERMINAL_EVENT_STATES = (DONE, FAILED, NEEDS_USER_ACTION)

TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({FETCHING, CONVERTING, FAILED, EXPIRED}),
    FETCHING: frozenset({CONVERTING, NEEDS_USER_ACTION, FAILED, EXPIRED}),
    # converting -> fetching: a converter raised FetchRequired mid-conversion.
    CONVERTING: frozenset({RENDERING, FETCHING, NEEDS_USER_ACTION, FAILED, EXPIRED}),
    RENDERING: frozenset({DONE, FAILED, EXPIRED}),
    DONE: frozenset({EXPIRED}),
    FAILED: frozenset({EXPIRED}),
    NEEDS_USER_ACTION: frozenset({QUEUED, FAILED, EXPIRED}),
    EXPIRED: frozenset(),
}

STAGE_MESSAGES = {
    QUEUED: "Queued",
    FETCHING: "Fetching",
    CONVERTING: "Converting",
    RENDERING: "Rendering",
    DONE: "Done",
    FAILED: "Failed",
    NEEDS_USER_ACTION: "Waiting for you",
    EXPIRED: "Expired",
}


class JobGone(Exception):
    """The job row does not exist (never created, purged, or deleted by the user)."""


class InvalidTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"illegal job transition {current} -> {target}")
        self.current = current
        self.target = target


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def result_url(job_id: str, profile: str, fmt: str = "md") -> str:
    return f"/v1/jobs/{job_id}/result?profile={profile}&format={fmt}"


class JobStore:
    def __init__(self, db: Database, state: StateBackend) -> None:
        self.db = db
        self.state = state

    # ---- reads ----

    def get(self, job_id: str) -> JobRow | None:
        with self.db.session() as s:
            return s.get(JobRow, job_id)

    def require(self, job_id: str) -> JobRow:
        row = self.get(job_id)
        if row is None:
            raise JobGone(job_id)
        return row

    def count_active(self, *, client_ip_hash: str | None = None, api_key_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(JobRow).where(JobRow.state.in_(ACTIVE_STATES))
        if api_key_id is not None:
            stmt = stmt.where(JobRow.api_key_id == api_key_id)
        elif client_ip_hash is not None:
            stmt = stmt.where(JobRow.client_ip_hash == client_ip_hash, JobRow.api_key_id.is_(None))
        with self.db.session() as s:
            return int(s.execute(stmt).scalar_one())

    def find_existing(
        self,
        *,
        api_key_id: str | None,
        client_ip_hash: str | None,
        input_sha256: str | None = None,
        options_json: str | None = None,
        profile: str | None = None,
        idempotency_key: str | None = None,
    ) -> JobRow | None:
        """Dedup lookup (section 7.1). `client_ip_hash` is passed only when the scope must include it
        (anonymous requests in public mode)."""
        now = utcnow()
        stmt = select(JobRow).where(JobRow.expires_at > now, JobRow.state != EXPIRED)
        stmt = stmt.where(JobRow.api_key_id == api_key_id if api_key_id else JobRow.api_key_id.is_(None))
        if client_ip_hash is not None:
            stmt = stmt.where(JobRow.client_ip_hash == client_ip_hash)
        if idempotency_key is not None:
            stmt = stmt.where(JobRow.idempotency_key == idempotency_key)
        else:
            stmt = stmt.where(
                JobRow.input_sha256 == input_sha256,
                JobRow.options_json == options_json,
                JobRow.profile == profile,
                JobRow.state == DONE,
            )
        with self.db.session() as s:
            return s.execute(stmt.order_by(JobRow.created_at.desc()).limit(1)).scalar_one_or_none()

    def expired_ids(self, now: datetime | None = None, limit: int = 500) -> list[str]:
        stmt = select(JobRow.id).where(JobRow.expires_at <= (now or utcnow())).limit(limit)
        with self.db.session() as s:
            return list(s.execute(stmt).scalars())

    # ---- writes ----

    def create(self, row: JobRow) -> JobRow:
        with self.db.session() as s:
            s.add(row)
        self.state.append_event(row.id, "state", {"state": row.state})
        return row

    def update(self, job_id: str, **fields: Any) -> JobRow:
        with self.db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                raise JobGone(job_id)
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = utcnow()
            return row

    def transition(
        self, job_id: str, target: str, *, event_data: dict[str, Any] | None = None, **fields: Any
    ) -> JobRow:
        with self.db.session() as s:
            row = s.get(JobRow, job_id, with_for_update=True)
            if row is None:
                raise JobGone(job_id)
            if not can_transition(row.state, target):
                raise InvalidTransition(row.state, target)
            row.state = target
            row.updated_at = utcnow()
            fields.setdefault("stage_message", STAGE_MESSAGES[target])
            if target == DONE:
                fields.setdefault("progress", 100)
            for k, v in fields.items():
                setattr(row, k, v)
        self.state.append_event(job_id, "state", {"state": target})
        if target in TERMINAL_EVENT_STATES:
            from ezmd_api.metrics import record_finished

            record_finished(self.state, target, row.queue)
        if target == DONE:
            data = {"result_url": result_url(job_id, row.profile), **(event_data or {})}
            self.state.append_event(job_id, "done", data)
        elif target == FAILED:
            self.state.append_event(job_id, "failed", self.error_payload(row))
        elif target == NEEDS_USER_ACTION:
            self.state.append_event(job_id, "needs_user_action", self.needs_action_payload(row) or {})
        return row

    def progress(self, job_id: str, pct: int, message: str) -> None:
        pct = max(0, min(100, int(pct)))
        self.update(job_id, progress=pct, stage_message=message[:500])
        self.state.append_event(job_id, "progress", {"progress": pct, "stage_message": message[:500]})

    def warning(self, job_id: str, warning: dict[str, Any]) -> None:
        self.state.append_event(job_id, "warning", warning)

    def fail(self, job_id: str, code: str, message: str, detail: dict[str, Any] | None = None) -> JobRow | None:
        try:
            return self.transition(job_id, FAILED, error_code=code, error_message=message[:2000])
        except (JobGone, InvalidTransition):
            return None

    def delete(self, job_id: str) -> bool:
        with self.db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                return False
            s.delete(row)
        self.state.delete_job(job_id)
        return True

    # ---- payloads ----

    @staticmethod
    def error_payload(row: JobRow) -> dict[str, Any]:
        from ezmd_api.errors import ERROR_STATUS

        code = row.error_code or "conversion_failed"
        return {
            "error": {
                "code": code,
                "message": row.error_message or "Conversion failed.",
                "status": ERROR_STATUS.get(code, 500),
                "detail": {},
            }
        }

    @staticmethod
    def needs_action_payload(row: JobRow) -> dict[str, Any] | None:
        if not row.needs_action:
            return None
        payload = dict(json.loads(row.needs_action))
        payload["supply_url"] = f"/v1/jobs/{row.id}/supply"
        return payload
