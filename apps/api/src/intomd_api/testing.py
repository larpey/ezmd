"""intomd_api.testing: helpers for API tests (apps/api/tests and tests/security/test_api_*.py).

Not imported by the app. Provides a settings factory, an httpx client bound to the app through
ASGITransport (with the lifespan run), an in-process stand-in for the spawn sandbox so most tests
do not pay process start-up, and polling helpers.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from intomd_api import isolation, worker
from intomd_api.main import create_app
from intomd_api.settings import Settings

TEST_LIMITS: dict[str, Any] = {
    "anon_concurrency": 100,
    "anon_ratelimit_max": 10_000,
    "anon_daily_max": 100_000,
    "anon_result_ratelimit_max": 10_000,
    "anon_sse_max": 100,
    "max_active_jobs": 1000,
}


def make_settings(data_dir: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "queue": "inline",
        "scheduler_enabled": False,
        "data_dir": data_dir,
        "web_dist": data_dir / "no-web-dist",
        **TEST_LIMITS,
    }
    values.update(overrides)
    return Settings(**values)


def in_process_isolation(req: isolation.ChildRequest, **_: Any) -> isolation.ChildOutcome:
    """Run the child entry point in this process (no rlimits). For tests only."""
    isolation.child_main(asdict(req))
    return isolation._read_outcome(req, 0)


def use_in_process_isolation(monkeypatch: Any) -> None:
    monkeypatch.setattr(isolation, "_apply_limits", lambda req: None)
    monkeypatch.setattr(worker, "run_isolated", in_process_isolation)


@asynccontextmanager
async def api_client(
    settings: Settings, *, redis_client: Any = None, client_addr: tuple[str, int] = ("127.0.0.1", 50000)
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(settings, redis_client=redis_client)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=client_addr)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, app


async def upload(
    client: httpx.AsyncClient,
    data: bytes,
    filename: str = "notes.txt",
    *,
    content_type: str = "text/plain",
    options: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    files = {"file": (filename, data, content_type)}
    form = {"options": json.dumps(options)} if options is not None else None
    return await client.post("/v1/convert", files=files, data=form, params=params, headers=headers)


async def wait_for_state(
    client: httpx.AsyncClient,
    job_id: str,
    states: tuple[str, ...] = ("done", "failed"),
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        r = await client.get(f"/v1/jobs/{job_id}", headers=headers)
        body: dict[str, Any] = r.json()
        if r.status_code != 200 or body.get("state") in states:
            return body
        if loop.time() > deadline:
            raise TimeoutError(f"job {job_id} stuck in {body.get('state')}")
        await asyncio.sleep(0.05)
