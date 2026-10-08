"""REST API against the compose stack (docs/spec/part4.md 4.14.3): uploads, SSE, profiles, formats,
warnings, deletion, auth. Owner-key calls bypass the anonymous limits; see test_it_ratelimit.py."""

from __future__ import annotations

import io
import json
import re
import struct
import zipfile
from pathlib import Path

import httpx
import pytest
from stackclient import Stack, nonce, parse_sse, upload, wait_for

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"

# One fixture per source family (the smoke corpus). The asserted heading comes from the golden.
SMOKE_CORPUS = [
    "text/markdown-kitchen-sink",
    "data/tsv-basic",
    "code/repo-small",
    "archives/zip-mixed",
    "ebooks/epub3-novel",
    "ebooks/ipynb-analysis",
    "office/docx-structure",
    "office/pptx-lecture",
    "office/xlsx-multi-sheet",
    "pdf/born-digital-report",
    "office/odt-basic",
    "web/article-standard",
    # An uploaded inline-XBRL filing is claimed by specialized.edgar through its namespace (no EDGAR URL).
    "edgar/tva-8k",
]

# Job states in pipeline order (apps/api/src/ezmd_api/jobs.py); SSE `state` events must not go back.
STATE_ORDER = ["queued", "fetching", "converting", "rendering", "done"]
HEADING = re.compile(r"^#{1,6} (.+?)(?: \{#[^}]*\})?$", re.MULTILINE)


def _input_of(fixture: str) -> Path:
    found = sorted((FIXTURES / fixture).glob("input.*"))
    assert found, f"fixture {fixture} has no input file"
    return found[0]


def _golden_heading(fixture: str) -> str:
    expected = (FIXTURES / fixture / "expected.full.md").read_text(encoding="utf-8")
    headings = [h for h in HEADING.findall(expected) if h != "Contents"]
    assert headings, f"{fixture} golden has no heading"
    return headings[0]


def _done(client: httpx.Client, data: bytes, filename: str, content_type: str = "text/plain", **kw: object) -> str:
    r = upload(client, data, filename, content_type=content_type, **kw)  # type: ignore[arg-type]
    assert r.status_code in (200, 202), r.text
    job_id = str(r.json()["job"]["id"])
    body = wait_for(client, job_id)
    assert body["state"] == "done", body
    return job_id


def _markdown_doc(title: str) -> bytes:
    return f"# {title}\n\nIntegration run {nonce()}.\n\n## Section\n\n- one\n- two\n".encode()


def test_health_ready_capabilities(stack: Stack) -> None:
    assert stack.anon.get("/healthz").status_code == 200
    assert stack.anon.get("/readyz").status_code == 200
    caps = stack.anon.get("/v1/capabilities").json()
    assert {"full", "compact", "rag", "agent"} <= set(caps["profiles"])


def test_owner_key_present(stack: Stack) -> None:
    assert stack.has_owner_key, "EZMD_API_KEY or EZMD_API_KEY_FILE must name the stack's owner key"


@pytest.mark.parametrize("fixture", SMOKE_CORPUS)
def test_smoke_corpus_converts(owner: httpx.Client, fixture: str) -> None:
    path = _input_of(fixture)
    job_id = _done(owner, path.read_bytes(), path.name, "application/octet-stream")
    r = owner.get(f"/v1/jobs/{job_id}/result", params={"format": "md", "profile": "full"})
    assert r.status_code == 200, r.text
    assert _golden_heading(fixture) in r.text


def test_uploaded_inline_xbrl_filing_uses_edgar(owner: httpx.Client) -> None:
    path = _input_of("edgar/tva-8k")
    r = upload(owner, path.read_bytes(), path.name, content_type="application/octet-stream")
    assert r.status_code in (200, 202), r.text
    body = wait_for(owner, str(r.json()["job"]["id"]))
    assert body["state"] == "done", body
    assert body["converter_id"] == "specialized.edgar", body


def test_sse_stage_order(owner: httpx.Client) -> None:
    job_id = _done(owner, _markdown_doc("SSE order"), "sse.md", "text/markdown")
    r = owner.get(f"/v1/jobs/{job_id}/events", timeout=60.0)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [e.get("event") for e in events]
    assert names[0] == "state" and names[-1] == "done", names
    states = [json.loads(e["data"])["state"] for e in events if e.get("event") == "state"]
    ranks = [STATE_ORDER.index(s) for s in states]
    assert ranks == sorted(ranks), states
    ids = [int(e["id"]) for e in events if "id" in e]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    done = json.loads(events[-1]["data"])
    assert done["tokens"] > 0
    # Resume: Last-Event-ID replays only what came after it.
    again = parse_sse(owner.get(f"/v1/jobs/{job_id}/events", headers={"Last-Event-ID": str(ids[-2])}).text)
    assert [e.get("event") for e in again] == ["done"]


def test_profiles_rerender_without_new_job(owner: httpx.Client) -> None:
    job_id = _done(owner, _markdown_doc("Profiles"), "profiles.md", "text/markdown")
    before = owner.get(f"/v1/jobs/{job_id}").json()
    bodies: dict[str, str] = {}
    for profile in ("full", "compact", "rag", "agent"):
        r = owner.get(f"/v1/jobs/{job_id}/result", params={"profile": profile, "format": "md"})
        assert r.status_code == 200, (profile, r.text)
        assert "Profiles" in r.text
        bodies[profile] = r.text
    assert len(set(bodies.values())) > 1, "every profile rendered the same bytes"
    after = owner.get(f"/v1/jobs/{job_id}").json()
    assert after["updated_at"] == before["updated_at"] and after["state"] == "done"
    assert owner.get(f"/v1/jobs/{job_id}/result", params={"profile": "nope"}).status_code == 400


def test_downloads_each_format(owner: httpx.Client) -> None:
    job_id = _done(owner, _markdown_doc("Downloads"), "downloads.md", "text/markdown")
    url = f"/v1/jobs/{job_id}/result"
    md = owner.get(url, params={"format": "md"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert int(md.headers["x-markdown-tokens"]) > 0
    txt = owner.get(url, params={"format": "txt"})
    assert txt.headers["content-type"].startswith("text/plain") and "Downloads" in txt.text
    js = owner.get(url, params={"format": "json"})
    assert js.headers["content-type"].startswith("application/json")
    assert "Downloads" in js.json()["markdown"]
    zp = owner.get(url, params={"format": "zip"})
    assert zp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(zp.content)) as z:
        assert z.testzip() is None
        assert any(n.endswith(".md") for n in z.namelist())
    assert owner.get(url, params={"format": "docx"}).status_code == 501


def test_warnings_reach_job_and_sidecar(owner: httpx.Client) -> None:
    path = _input_of("code/source-planted-secret")
    job_id = _done(owner, path.read_bytes(), path.name)
    job = owner.get(f"/v1/jobs/{job_id}").json()
    assert "secret_redacted" in job["warnings"]
    md = owner.get(f"/v1/jobs/{job_id}/result", params={"format": "md"})
    assert int(md.headers["x-ezmd-warnings"]) >= 1
    assert "a4e3770643c072829845a0b6c58a00aa6f78e8b5" not in md.text
    sidecar = owner.get(f"/v1/jobs/{job_id}/result", params={"format": "json"}).json()["sidecar"]
    codes = {w.get("code") or w.get("kind") for w in sidecar["warnings"]}
    assert "secret_redacted" in codes
    registry = {row["code"] for row in owner.get("/v1/warnings").json()["warnings"]}
    assert set(job["warnings"]) <= registry


def test_delete_purges_job(owner: httpx.Client) -> None:
    job_id = _done(owner, _markdown_doc("Delete me"), "delete.md", "text/markdown")
    assert owner.delete(f"/v1/jobs/{job_id}").status_code == 204
    assert owner.get(f"/v1/jobs/{job_id}").status_code == 404
    assert owner.get(f"/v1/jobs/{job_id}/result").status_code == 404
    assert owner.delete(f"/v1/jobs/{job_id}").status_code == 404


def test_invalid_api_key_is_401(stack: Stack) -> None:
    bad = stack.client(**{"X-API-Key": "ak_live_not_a_key"})
    for resp in (upload(bad, b"hello", "hello.txt"), bad.get("/v1/jobs/job_0000000000000000000000")):
        assert resp.status_code == 401, resp.text
        assert resp.json()["error"]["code"] == "unauthorized"


def test_jobs_are_scoped_to_their_caller(stack: Stack, owner: httpx.Client) -> None:
    job_id = _done(owner, _markdown_doc("Owner only"), "owner.md", "text/markdown")
    r = stack.anon.get(f"/v1/jobs/{job_id}")
    assert r.status_code in (403, 404), r.text


def test_unsupported_executable_415(owner: httpx.Client) -> None:
    elf = bytes([0x7F, 0x45, 0x4C, 0x46, 2, 1, 1, 0]) + bytes(8) + struct.pack("<HHI", 2, 0x3E, 1) + bytes(200)
    r = upload(owner, elf, "tool.bin", content_type="application/octet-stream")
    assert r.status_code == 415, r.text
