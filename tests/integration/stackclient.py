"""Thin synchronous client for the compose stack used by tests/integration (no SDK, plain httpx).

Configuration comes from the environment that `tests/integration/stack.sh env` prints:
EZMD_BASE_URL, EZMD_API_KEY or EZMD_API_KEY_FILE, EZMD_FIXTURE_ORIGIN, and
EZMD_INSECURE=1 to skip TLS verification (Caddy's internal CA on https://localhost).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

TERMINAL = frozenset({"done", "failed", "expired", "needs_user_action"})
DEFAULT_TIMEOUT_S = float(os.environ.get("EZMD_IT_JOB_TIMEOUT_S", "180"))


def _owner_key() -> str:
    key = os.environ.get("EZMD_API_KEY", "").strip()
    if key:
        return key
    path = os.environ.get("EZMD_API_KEY_FILE", "").strip()
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    return ""


@dataclass
class Stack:
    base_url: str
    owner: httpx.Client
    anon: httpx.Client
    fixture_origin: str
    has_owner_key: bool
    verify: bool
    _clients: list[httpx.Client] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> Stack:
        base = os.environ["EZMD_BASE_URL"].rstrip("/")
        verify = os.environ.get("EZMD_INSECURE", "") != "1"
        key = _owner_key()
        timeout = httpx.Timeout(60.0, connect=10.0)
        owner = httpx.Client(base_url=base, verify=verify, timeout=timeout, headers={"X-API-Key": key} if key else {})
        anon = httpx.Client(base_url=base, verify=verify, timeout=timeout)
        origin = os.environ.get("EZMD_FIXTURE_ORIGIN", "http://web.fixtures.example:8000").rstrip("/")
        return cls(base, owner, anon, origin, bool(key), verify, [owner, anon])

    def client(self, **headers: str) -> httpx.Client:
        c = httpx.Client(base_url=self.base_url, verify=self.verify, timeout=60.0, headers=headers)
        self._clients.append(c)
        return c

    def close(self) -> None:
        for c in self._clients:
            c.close()


def upload(
    client: httpx.Client,
    data: bytes,
    filename: str,
    *,
    content_type: str = "text/plain",
    options: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    files = {"file": (filename, data, content_type)}
    form = {"options": json.dumps(options)} if options is not None else None
    return client.post("/v1/convert", files=files, data=form, params=params)


def convert_url(client: httpx.Client, url: str, **body: Any) -> httpx.Response:
    return client.post("/v1/convert", json={"url": url, **body})


def wait_for(client: httpx.Client, job_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        r = client.get(f"/v1/jobs/{job_id}")
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        if body["state"] in TERMINAL:
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"job {job_id} still {body['state']} after {timeout_s}s: {body}")
        time.sleep(0.5)


def parse_sse(text: str) -> list[dict[str, str]]:
    """Split a text/event-stream body into events (comments dropped)."""
    events: list[dict[str, str]] = []
    for chunk in text.replace(chr(13), "").split(chr(10) * 2):
        ev: dict[str, str] = {}
        for line in chunk.split(chr(10)):
            if not line or line.startswith(":"):
                continue
            name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            ev[name] = ev[name] + chr(10) + value if name in ev else value
        if ev:
            events.append(ev)
    return events


def nonce() -> str:
    """A per-run token that keeps uploads from being deduplicated onto an earlier run's job."""
    return f"{time.time_ns():x}-{os.getpid()}"
