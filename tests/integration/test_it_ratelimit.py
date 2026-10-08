"""Anonymous creation limit (docs/spec/part4.md 4.14.3 and 4.14.5 item 5): the 21st request in 60 s gets 429.

Consumes the runner's anonymous budget, so the workflow runs it after the Playwright suite
(`-m ratelimit`). The stack keeps EZMD_ANON_RATELIMIT_MAX=20 per 60 s (tests/integration/stack.sh).
Earlier anonymous traffic in the same window is accounted for through X-RateLimit-Remaining.
"""

from __future__ import annotations

import os

import httpx
import pytest
from stackclient import nonce, upload, wait_for

pytestmark = pytest.mark.ratelimit

LIMIT = int(os.environ.get("EZMD_IT_ANON_LIMIT", "20"))


def test_anonymous_creation_limit_429(anon: httpx.Client) -> None:
    # One real job, then identical uploads: those deduplicate onto it (200) without new jobs, so the
    # per-IP concurrency limit never interferes and only the creation limiter can answer 429.
    data = f"rate limit probe {nonce()}\n".encode()
    first = upload(anon, data, "probe.txt")
    if first.status_code == 429:
        pytest.fail(f"window already exhausted before the test started: {first.headers}")
    assert first.status_code == 202, first.text
    assert int(first.headers["x-ratelimit-limit"]) == LIMIT
    remaining = int(first.headers["x-ratelimit-remaining"])
    assert wait_for(anon, first.json()["job"]["id"])["state"] == "done"

    for i in range(remaining):
        r = upload(anon, data, "probe.txt")
        assert r.status_code == 200, (i, r.status_code, r.text)
        assert r.json()["deduplicated"] is True
        assert int(r.headers["x-ratelimit-remaining"]) == remaining - i - 1

    blocked = upload(anon, data, "probe.txt")
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) > 0
    assert blocked.headers["x-ratelimit-limit"] == str(LIMIT)
    assert blocked.headers["x-ratelimit-remaining"] == "0"
    if remaining == LIMIT - 1:
        # A fresh window: exactly 20 accepted, the 21st refused.
        assert 1 + remaining == LIMIT
