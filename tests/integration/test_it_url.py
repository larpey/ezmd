"""URL inputs fetched by worker-fetch from the in-network fixture server (tests/integration/compose.fixtures.yml).

Needs the stack restarted with EZMD_ALLOW_PRIVATE_NETWORKS=true (`stack.sh private`, EZMD_PRIVATE_FETCH=1):
the fixture server lives on a private Docker network, which the SSRF guard refuses by default (that
refusal is asserted by tests/security/test_net_stack.py before the restart).
"""

from __future__ import annotations

import json

import httpx
import pytest
from stackclient import Stack, convert_url, parse_sse, wait_for

pytestmark = pytest.mark.private_fetch


def test_url_job_fetches_and_converts(stack: Stack, owner: httpx.Client) -> None:
    url = f"{stack.fixture_origin}/article-standard/input.html"
    r = convert_url(owner, url, profile="full")
    assert r.status_code in (200, 202), r.text
    job_id = r.json()["job"]["id"]
    body = wait_for(owner, job_id)
    assert body["state"] == "done", body
    assert body["converter_id"].startswith("web."), body
    md = owner.get(f"/v1/jobs/{job_id}/result", params={"format": "md"}).text
    assert "Tide Tables for Small Harbors" in md
    assert "web.fixtures.example" in md  # frontmatter source is the fetched URL

    events = parse_sse(owner.get(f"/v1/jobs/{job_id}/events").text)
    states = [json.loads(e["data"])["state"] for e in events if e.get("event") == "state"]
    assert "fetching" in states and states.index("fetching") < len(states) - 1
    assert events[-1].get("event") == "done"


def test_url_not_found_fails_cleanly(stack: Stack, owner: httpx.Client) -> None:
    r = convert_url(owner, f"{stack.fixture_origin}/does-not-exist-{id(stack)}.html")
    assert r.status_code in (200, 202), r.text
    body = wait_for(owner, r.json()["job"]["id"])
    assert body["state"] == "failed", body
    assert body["error"]["code"] == "fetch_failed", body
