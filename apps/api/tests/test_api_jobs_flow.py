"""End-to-end job flow against the app (inline queue): create, poll, SSE, results, wait, delete."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import httpx
import pytest

from ezmd_api.testing import upload, wait_for_state

MD = b"# Fleet report\n\nQuarterly numbers for the fleet.\n\n- trucks: 12\n- vans: 4\n"


async def _done_job(client: httpx.AsyncClient, data: bytes = MD, filename: str = "report.md", **kw: object) -> str:
    r = await upload(client, data, filename, content_type="text/markdown", **kw)  # type: ignore[arg-type]
    assert r.status_code == 202, r.text
    job_id = r.json()["job"]["id"]
    body = await wait_for_state(client, job_id)
    assert body["state"] == "done", body
    return str(job_id)


async def test_multipart_create_envelope(client: httpx.AsyncClient) -> None:
    r = await upload(client, MD, "report.md", content_type="text/markdown", options={"profile": "rag"})
    assert r.status_code == 202
    body = r.json()
    job = body["job"]
    assert job["id"].startswith("job_") and len(job["id"]) == 26
    assert job["state"] == "queued"
    assert job["queue"] == "default"
    assert job["profile"] == "rag"
    assert job["input"] == {
        "kind": "bytes",
        "display": "report.md",
        "mime": "text/markdown",
        "size_bytes": len(MD),
        "sha256": None,
    }
    assert body["deduplicated"] is False
    assert body["links"] == {
        "self": f"/v1/jobs/{job['id']}",
        "events": f"/v1/jobs/{job['id']}/events",
        "result": f"/v1/jobs/{job['id']}/result?profile=rag&format=md",
    }
    assert r.headers["x-request-id"].startswith("req_")


async def test_poll_until_done(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    body = (await client.get(f"/v1/jobs/{job_id}")).json()
    assert body["progress"] == 100
    assert body["converter_id"] == "text.markdown_passthrough"
    assert body["error"] is None and body["needs_action"] is None
    assert len(body["input"]["sha256"]) == 64


@pytest.mark.parametrize("profile", ["full", "compact", "rag", "agent"])
@pytest.mark.parametrize("fmt", ["md", "json", "txt"])
async def test_result_profiles_and_formats(client: httpx.AsyncClient, profile: str, fmt: str) -> None:
    job_id = await _done_job(client)
    r = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": profile, "format": fmt})
    assert r.status_code == 200, r.text
    expected = {"md": "text/markdown; charset=utf-8", "json": "application/json", "txt": "text/plain; charset=utf-8"}
    assert r.headers["content-type"] == expected[fmt]
    assert int(r.headers["x-markdown-tokens"]) > 0
    assert r.headers["x-ezmd-truncated"] in ("true", "false")
    assert r.headers["x-ezmd-warnings"].isdigit()
    assert r.headers["x-ezmd-injection-risk"] in ("none", "low", "medium", "high")
    assert r.headers["x-content-type-options"] == "nosniff"
    if fmt == "json":
        payload = r.json()
        assert "markdown" in payload and "frontmatter" in payload
    else:
        assert "Quarterly numbers" in r.text


async def test_result_zip(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    r = await client.get(f"/v1/jobs/{job_id}/result", params={"format": "zip"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == f'attachment; filename="{job_id}.zip"'
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert f"{job_id}.md" in names


async def test_result_docx_is_501_and_bad_format_400(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    r = await client.get(f"/v1/jobs/{job_id}/result", params={"format": "docx"})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "not_implemented"
    r = await client.get(f"/v1/jobs/{job_id}/result", params={"format": "pdf"})
    assert r.status_code == 400
    r = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": "nope"})
    assert r.status_code == 400


async def test_result_override_validation(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    ok = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": "rag", "chunks.chunk_tokens": "256"})
    assert ok.status_code == 200, ok.text
    bad = await client.get(f"/v1/jobs/{job_id}/result", params={"chunks.no_such_option": "1"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_request"


async def test_result_cached_is_identical(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    a = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": "compact"})
    b = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": "compact"})
    assert a.content == b.content


def _parse_sse(text: str) -> list[dict[str, object]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields: dict[str, object] = {}
        for line in block.splitlines():
            if line.startswith(":"):
                fields.setdefault("comment", line)
                continue
            key, _, value = line.partition(": ")
            fields[key] = value
        events.append(fields)
    return events


async def test_sse_receives_done(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    r = await client.get(f"/v1/jobs/{job_id}/events")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    names = [e.get("event") for e in events]
    assert names[0] == "state" and names[-1] == "done"
    assert "progress" in names
    ids = [int(str(e["id"])) for e in events if "id" in e]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    done = json.loads(str(events[-1]["data"]))
    assert done["result_url"] == f"/v1/jobs/{job_id}/result?profile=full&format=md"
    assert done["tokens"] > 0
    # Last-Event-ID replays only newer events.
    r2 = await client.get(f"/v1/jobs/{job_id}/events", headers={"Last-Event-ID": str(ids[-2])})
    again = _parse_sse(r2.text)
    assert [e.get("event") for e in again] == ["done"]


async def test_sse_keepalive(monkeypatch: pytest.MonkeyPatch, client_app: tuple[httpx.AsyncClient, Any]) -> None:
    client, app = client_app
    from ezmd_api.routes import jobs as jobs_routes

    monkeypatch.setattr(jobs_routes, "SSE_KEEPALIVE_SECONDS", 0.05)
    monkeypatch.setattr(jobs_routes, "SSE_MAX_SECONDS", 0.3)
    monkeypatch.setattr(jobs_routes, "SSE_POLL_SECONDS", 0.05)
    job_id = await _done_job(client)
    # Replay from the end so nothing terminal is pending, then remove the buffer to force waiting.
    app_state = app.state
    app_state.services.state.delete_job(job_id)
    app_state.services.jobs.update(job_id, state="rendering")
    r = await client.get(f"/v1/jobs/{job_id}/events")
    assert ": keepalive" in r.text


async def test_wait_returns_result_body(client: httpx.AsyncClient) -> None:
    r = await upload(client, MD, "report.md", content_type="text/markdown", params={"wait": 20})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/markdown; charset=utf-8"
    assert "Quarterly numbers" in r.text
    envelope = json.loads(r.headers["x-ezmd-job"])
    assert envelope["state"] == "done"


async def test_wait_returns_error_for_failed_job(client: httpx.AsyncClient) -> None:
    r = await upload(
        client, b"\x00\x01\x02\xff" * 64, "blob.bin", content_type="application/octet-stream", params={"wait": 20}
    )
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "conversion_failed"
    assert json.loads(r.headers["x-ezmd-job"])["state"] == "failed"


async def test_failed_job_exposes_error(client: httpx.AsyncClient) -> None:
    r = await upload(client, b"\x00\x01\x02\xff" * 64, "blob.bin", content_type="application/octet-stream")
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["state"] == "failed"
    assert body["error"]["code"] == "conversion_failed"
    assert "Traceback" not in body["error"]["message"]


async def test_unknown_job_404_schema(client: httpx.AsyncClient) -> None:
    for path in ("/v1/jobs/job_0000000000000000000000", "/v1/jobs/not-a-job", "/v1/jobs/../etc/result"):
        r = await client.get(path)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


async def test_delete_purges(client: httpx.AsyncClient) -> None:
    job_id = await _done_job(client)
    r = await client.delete(f"/v1/jobs/{job_id}")
    assert r.status_code == 204
    assert (await client.get(f"/v1/jobs/{job_id}")).status_code == 404


async def test_invalid_options_rejected(client: httpx.AsyncClient) -> None:
    r = await upload(client, MD, "a.md", options={"no_such_option": 1})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"
    r = await upload(client, MD, "a.md", options={"profile": "bogus"})
    assert r.status_code == 400
    r = await client.post("/v1/convert", content=b"hello", headers={"content-type": "text/plain"})
    assert r.status_code == 400
