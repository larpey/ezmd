"""Network tier against the compose stack (docs/spec/part4.md 4.14.5 items 1 and 7).

Runs in .github/workflows/integration.yml after `tests/integration/stack.sh up`, while the stack still
has EZMD_ALLOW_PRIVATE_NETWORKS=false. Uses the owner key (EZMD_API_KEY or EZMD_API_KEY_FILE)
so the anonymous rate limits do not interfere.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from ssrf_table import LITERAL

pytestmark = pytest.mark.network

FIXTURE_URL = os.environ.get("EZMD_FIXTURE_ORIGIN", "http://web.fixtures.example:8000") + "/article-short/input.html"
CSP = (
    "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; "
    "frame-src https://challenges.cloudflare.com; "
    "connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; "
    "object-src 'none'; base-uri 'none'; form-action 'self'"
)


def _key() -> str:
    key = os.environ.get("EZMD_API_KEY", "").strip()
    path = os.environ.get("EZMD_API_KEY_FILE", "").strip()
    if not key and path and Path(path).is_file():
        key = Path(path).read_text(encoding="utf-8").strip()
    return key


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    # Module-scoped, so it runs before conftest's per-test tier check: skip here too.
    if os.environ.get("EZMD_NETWORK_TESTS") != "1" or not os.environ.get("EZMD_BASE_URL"):
        pytest.skip("network tier: set EZMD_NETWORK_TESTS=1 and EZMD_BASE_URL (tests/integration/stack.sh)")
    key = _key()
    with httpx.Client(
        base_url=os.environ["EZMD_BASE_URL"].rstrip("/"),
        verify=os.environ.get("EZMD_INSECURE", "") != "1",
        timeout=30.0,
        headers={"X-API-Key": key} if key else {},
    ) as c:
        yield c


@pytest.mark.parametrize("url", LITERAL)
def test_stack_refuses_ssrf_urls_at_submit(client: httpx.Client, url: str) -> None:
    r = client.post("/v1/convert", json={"url": url})
    assert r.status_code in (400, 422), (url, r.status_code, r.text)
    assert r.json()["error"]["code"] in ("url_blocked", "invalid_request"), r.text
    if r.status_code == 422:
        assert r.json()["error"]["code"] == "url_blocked"


def test_worker_refuses_name_resolving_to_private_address(client: httpx.Client) -> None:
    """The fixture server's dotted alias passes submit-time checks; worker-fetch resolves it to a private
    Docker address and must refuse to connect (DNS-rebinding style; the request never leaves the guard)."""
    r = client.post("/v1/convert", json={"url": FIXTURE_URL})
    assert r.status_code in (200, 202), r.text
    job_id = r.json()["job"]["id"]
    deadline = time.monotonic() + 120
    while True:
        body = client.get(f"/v1/jobs/{job_id}").json()
        if body["state"] in ("done", "failed", "needs_user_action", "expired"):
            break
        assert time.monotonic() < deadline, body
        time.sleep(0.5)
    assert body["state"] == "failed", f"private fixture server was fetched: {body}"
    assert body["error"]["code"] == "url_blocked", body


def test_edge_security_headers(client: httpx.Client) -> None:
    for path in ("/", "/v1/capabilities", "/healthz"):
        r = client.get(path)
        assert r.status_code == 200, path
        h = r.headers
        assert h["content-security-policy"] == CSP, path
        assert h["x-content-type-options"] == "nosniff", path
        assert h["strict-transport-security"].startswith("max-age="), path
        assert h["x-frame-options"] == "DENY", path
        assert h["referrer-policy"] == "no-referrer", path
        assert "server" not in h, (path, h.get("server"))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/metrics"),
        ("GET", "/admin"),
        ("POST", "/v1/fetch-node/claim"),
        ("GET", "/v1/fetch-node/jobs"),
    ],
)
def test_internal_endpoints_404_at_the_edge(client: httpx.Client, method: str, path: str) -> None:
    r = client.request(method, path, headers={"Authorization": "Bearer not-a-real-token-1234567890"})
    assert r.status_code == 404, (path, r.status_code)
