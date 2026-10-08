"""intomd_api.metrics: Prometheus text exposition for GET /metrics (docs/spec/part4.md 4.10.5).

No client library: the API and the RQ workers are separate processes, so cumulative counters and the
conversion-duration histogram live in the shared state backend (a Redis hash; memory in inline mode)
and gauges are computed from the job table at scrape time. Every recorder swallows its own errors:
metrics never fail a job or a request.

Series:
- `intomd_jobs{state,queue}` gauge: job rows by state and queue (rows live until purged).
- `intomd_queue_depth{queue}` gauge: queued jobs per queue.
- `intomd_jobs_finished_total{state,queue}` counter: jobs that reached done, failed, or needs_user_action.
- `intomd_conversion_duration_seconds{converter}` histogram: converter wall time (IR `metrics.duration_seconds`).
- `intomd_warnings_total{code}` counter: warnings emitted, by canonical code.
- `intomd_rate_limited_total{reason}` counter: requests refused by a rate limit or admission check.
- `intomd_fetch_node_online{node_id}` gauge (1 per node seen in the last 60 s) and `intomd_fetch_nodes_online`.
- `intomd_build_info{version}` gauge.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import func, select

if TYPE_CHECKING:
    from intomd_api.services import Services
    from intomd_api.state import StateBackend

log = logging.getLogger("intomd.api.metrics")

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
DURATION_BUCKETS: tuple[float, ...] = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0)
_BACKSLASH = chr(92)
_NL = chr(10)

HELP: dict[str, tuple[str, str]] = {
    "intomd_build_info": ("gauge", "Build information."),
    "intomd_jobs": ("gauge", "Job rows by state and queue."),
    "intomd_queue_depth": ("gauge", "Jobs waiting in each queue."),
    "intomd_jobs_finished_total": ("counter", "Jobs that reached done, failed, or needs_user_action."),
    "intomd_conversion_duration_seconds": ("histogram", "Converter wall time in seconds."),
    "intomd_warnings_total": ("counter", "Warnings emitted, by canonical code."),
    "intomd_rate_limited_total": ("counter", "Requests refused by a rate limit or admission check."),
    "intomd_fetch_node_online": ("gauge", "1 for each residential fetch node seen in the last 60 s."),
    "intomd_fetch_nodes_online": ("gauge", "Residential fetch nodes seen in the last 60 s."),
}


def escape_label(value: str) -> str:
    out = value.replace(_BACKSLASH, _BACKSLASH * 2).replace('"', _BACKSLASH + '"')
    return out.replace(_NL, _BACKSLASH + "n")


def series(name: str, **labels: str) -> str:
    if not labels:
        return name
    inner = ",".join(f'{k}="{escape_label(v)}"' for k, v in sorted(labels.items()))
    return name + "{" + inner + "}"


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _add(state: StateBackend, increments: dict[str, float]) -> None:
    try:
        state.metric_add_many(increments)
    except Exception:
        log.warning("metric update failed", exc_info=True)


# ---------------------------------------------------------------------------
# Recorders
# ---------------------------------------------------------------------------


def record_finished(state: StateBackend, job_state: str, queue: str) -> None:
    _add(state, {series("intomd_jobs_finished_total", state=job_state, queue=queue): 1.0})


def record_conversion(state: StateBackend, converter_id: str, seconds: float, warning_codes: list[str]) -> None:
    seconds = max(0.0, float(seconds))
    name = "intomd_conversion_duration_seconds"
    inc: dict[str, float] = defaultdict(float)
    for bound in DURATION_BUCKETS:
        if seconds <= bound:
            inc[series(name + "_bucket", converter=converter_id, le=_fmt(bound))] += 1.0
    inc[series(name + "_bucket", converter=converter_id, le="+Inf")] += 1.0
    inc[series(name + "_sum", converter=converter_id)] += seconds
    inc[series(name + "_count", converter=converter_id)] += 1.0
    for code in warning_codes:
        inc[series("intomd_warnings_total", code=code)] += 1.0
    _add(state, dict(inc))


def record_rate_limited(state: StateBackend, reason: str) -> None:
    _add(state, {series("intomd_rate_limited_total", reason=reason): 1.0})


# ---------------------------------------------------------------------------
# Exposition
# ---------------------------------------------------------------------------


def _base_name(field: str) -> str:
    name = field.split("{", 1)[0]
    for suffix in ("_bucket", "_sum", "_count"):
        if name.endswith(suffix) and name.removesuffix(suffix) in HELP:
            return name.removesuffix(suffix)
    return name


def _gauges(services: Services) -> dict[str, float]:
    from intomd_api import __version__
    from intomd_api import queue as q
    from intomd_api.db import JobRow
    from intomd_api.jobs import QUEUED

    out: dict[str, float] = {series("intomd_build_info", version=__version__): 1.0}
    with services.db.session() as s:
        rows = s.execute(select(JobRow.state, JobRow.queue, func.count()).group_by(JobRow.state, JobRow.queue)).all()
    depth: dict[str, float] = dict.fromkeys(q.ALL_QUEUES, 0.0)
    for job_state, queue, count in rows:
        n = float(count)
        out[series("intomd_jobs", state=str(job_state), queue=str(queue))] = n
        if job_state == QUEUED:
            depth[str(queue)] = depth.get(str(queue), 0.0) + n
    for name, waiting in depth.items():
        out[series("intomd_queue_depth", queue=name)] = waiting
    try:
        nodes = services.state.nodes_online()
    except Exception:
        nodes = []
    for node in nodes:
        out[series("intomd_fetch_node_online", node_id=node)] = 1.0
    out["intomd_fetch_nodes_online"] = float(len(nodes))
    return out


def render(services: Services) -> str:
    """The full exposition text."""
    values = _gauges(services)
    try:
        values.update(services.state.metric_snapshot())
    except Exception:
        log.warning("metric snapshot failed", exc_info=True)
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for field, value in values.items():
        grouped[_base_name(field)].append((field, value))
    lines: list[str] = []
    for name in sorted(grouped):
        kind, text = HELP.get(name, ("untyped", ""))
        if text:
            lines.append(f"# HELP {name} {text}")
        lines.append(f"# TYPE {name} {kind}")
        lines.extend(f"{field} {_fmt(value)}" for field, value in sorted(grouped[name], key=_sort_key))
    return _NL.join(lines) + _NL


def _sort_key(item: tuple[str, float]) -> tuple[str, float]:
    """Keep histogram buckets in ascending `le` order within one label set."""
    field = item[0]
    if 'le="' not in field:
        return (field, 0.0)
    head, _, rest = field.partition('le="')
    le = rest.split('"', 1)[0]
    bound = float("inf") if le == "+Inf" else float(le)
    return (head, bound)
