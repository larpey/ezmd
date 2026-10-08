"""Phase 0 close council (DECISIONS.md D-0017) API changes: fetch re-enqueue, FetchRequired
re-validation and depth cap, result-size cap, keyed limits, result query keys, agent salt, IR cache
key, experimental_disabled."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import fakeredis
import pytest

from intomd_api import isolation, rendering, worker
from intomd_api.settings import Settings
from intomd_api.testing import api_client, in_process_isolation, upload, wait_for_state

PUBLIC_SECRET = "s" * 32


def _fake_fetch(calls: list[str], body: bytes = b"Fetched text.\n") -> Callable[..., Any]:
    from intomd.core.netguard import FetchResult

    def fetch(url: str, **kwargs: Any) -> FetchResult:
        calls.append(url)
        return FetchResult(
            url=url,
            status=200,
            headers={"content-type": "text/plain"},
            body=body,
            resolved_ip="93.184.216.34",
            redirects=[],
            duration_seconds=0.01,
        )

    return fetch


# ---- item 2: the fetch worker never parses ----


async def test_fetched_body_is_reenqueued_to_default(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    from rq import Queue

    from intomd.core import netguard

    calls: list[str] = []
    monkeypatch.setattr(netguard, "fetch", _fake_fetch(calls))
    redis = fakeredis.FakeRedis()
    parsed: list[str] = []
    monkeypatch.setattr(
        worker, "run_isolated", lambda req, **kw: parsed.append(req.url or "") or in_process_isolation(req)
    )
    async with api_client(settings_factory(queue="rq"), redis_client=redis) as (client, app):
        services = app.state.services
        r = await client.post("/v1/convert", json={"url": "https://example.com/a.txt"})
        job_id = r.json()["job"]["id"]
        assert len(Queue("fetch", connection=redis).get_jobs()) == 1
        worker.process_job(services, job_id)  # what the fetch worker runs
        row = services.jobs.require(job_id)
        assert calls == ["https://example.com/a.txt"]
        assert parsed == [], "the fetch worker must not convert"
        assert row.blob_input is not None and row.blob_ir is None
        assert row.queue == "default" and row.state == "converting"
        default_jobs = Queue("default", connection=redis).get_jobs()
        assert [j.args for j in default_jobs] == [(job_id,)]
        worker.process_job(services, job_id)  # what the default worker runs
        assert services.jobs.require(job_id).state == "done"
        assert parsed == ["https://example.com/a.txt"]


# ---- item 3: FetchRequired is re-validated, depth-capped, and stored on the job ----


def _fetch_required(url: str, *, residential: bool = True, depth: int = 0, times: int = 1) -> Callable[..., Any]:
    remaining = [times]

    def run(req: isolation.ChildRequest, **kw: Any) -> isolation.ChildOutcome:
        if remaining[0] > 0:
            remaining[0] -= 1
            return isolation.ChildOutcome("fetch_required", fetch_url=url, residential=residential, fetch_depth=depth)
        return in_process_isolation(req)

    return run


async def test_fetch_required_ignores_child_residential_flag(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    from intomd.core import netguard

    calls: list[str] = []
    monkeypatch.setattr(netguard, "fetch", _fake_fetch(calls, b"Second page body.\n"))
    monkeypatch.setattr(worker, "run_isolated", _fetch_required("https://example.org/next.txt#frag"))
    r = await upload(client, b"first\n", "a.txt")
    job_id = r.json()["job"]["id"]
    body = await wait_for_state(client, job_id)
    assert body["state"] == "done", body
    assert body["queue"] != "fetch_residential"
    assert calls == ["https://example.org/next.txt"]
    assert "Second page body." in (await client.get(f"/v1/jobs/{job_id}/result")).text


async def test_fetch_required_url_is_revalidated(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    monkeypatch.setattr(worker, "run_isolated", _fetch_required("http://169.254.169.254/latest/meta-data"))
    r = await upload(client, b"first\n", "a.txt")
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["state"] == "failed"
    assert body["error"]["code"] == "url_blocked"


async def test_fetch_required_respects_disabled_policy(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings], tmp_path: Path
) -> None:
    policy = tmp_path / "platforms.toml"
    policy.write_text("[hosts]" + chr(10) + '"blocked.example" = "disabled"' + chr(10), encoding="utf-8")
    monkeypatch.setattr(worker, "run_isolated", _fetch_required("https://blocked.example/x"))
    async with api_client(settings_factory(platforms_file=policy)) as (client, _):
        r = await upload(client, b"first\n", "a.txt")
        body = await wait_for_state(client, r.json()["job"]["id"])
        assert body["error"]["code"] == "platform_disabled"


async def test_fetch_required_depth_limit(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    from intomd.core import netguard

    calls: list[str] = []
    monkeypatch.setattr(netguard, "fetch", _fake_fetch(calls))
    monkeypatch.setattr(worker, "run_isolated", _fetch_required("https://example.org/loop", times=100))
    r = await upload(client, b"first\n", "a.txt")
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["state"] == "failed"
    assert body["error"]["code"] == "fetch_depth_exceeded"
    assert len(calls) == 2  # MAX_FETCH_DEPTH


async def test_fetch_required_child_depth_cannot_lower_the_count(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    monkeypatch.setattr(worker, "run_isolated", _fetch_required("https://example.org/deep", depth=99))
    r = await upload(client, b"first\n", "a.txt")
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["error"]["code"] == "fetch_depth_exceeded"


# ---- item 5: the child's result file is capped ----


def test_result_file_cap(tmp_path: Path) -> None:
    out = tmp_path / "result.json"
    req = isolation.ChildRequest(
        input_path=str(tmp_path / "in"),
        out_path=str(out),
        display="x",
        kind="bytes",
        url=None,
        declared_mime=None,
        convert_options={},
        converter_id=None,
        max_seconds=10,
        mem_mb=512,
        max_bytes=1024,
        max_result_bytes=1024,
    )
    Path(str(out) + ".status.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    out.write_bytes(b"x" * 2048)
    outcome = isolation._read_outcome(req, 0)
    assert outcome.status == "error"
    assert outcome.code == "result_too_large"
    assert outcome.result_json is None
    out.write_bytes(b"{}")
    assert isolation._read_outcome(req, 0).result_json == "{}"


async def test_result_too_large_fails_job(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(max_result_bytes=1024)) as (client, _):
        r = await upload(client, b"A sentence that repeats. " * 400, "big.txt")
        body = await wait_for_state(client, r.json()["job"]["id"])
        assert body["state"] == "failed"
        assert body["error"]["code"] == "result_too_large"
        assert body["error"]["status"] == 422


# ---- item 6 (D-0017 API list): keyed callers get their key's limits ----


async def test_keyed_callers_get_key_page_limit(settings_factory: Callable[..., Settings]) -> None:
    from intomd_api.auth import create_api_key

    async with api_client(settings_factory(anon_max_pages=10)) as (client, app):
        services = app.state.services
        key, _ = create_api_key(services.db, services.settings, "big", env="test", max_pages=5000)
        default_key, _ = create_api_key(services.db, services.settings, "default", env="test")

        def stored_pages(resp: Any) -> int:
            row = services.jobs.require(resp.json()["job"]["id"])
            return int(json.loads(row.options_json)["convert"]["max_pages"])

        anon = await upload(client, b"anon\n", "a.txt", options={"max_pages": 4000})
        assert stored_pages(anon) == 10
        keyed = await upload(client, b"keyed\n", "b.txt", options={"max_pages": 4000}, headers={"X-API-Key": key})
        assert stored_pages(keyed) == 4000
        capped = await upload(client, b"capped\n", "c.txt", options={"max_pages": 9000}, headers={"X-API-Key": key})
        assert stored_pages(capped) == 5000
        unset = await upload(client, b"unset\n", "d.txt", headers={"X-API-Key": default_key})
        assert stored_pages(unset) == 10_000


async def test_keyed_upload_limit_is_the_keys(settings_factory: Callable[..., Settings]) -> None:
    from intomd_api.auth import create_api_key

    async with api_client(settings_factory(anon_max_upload_mb=1)) as (client, app):
        services = app.state.services
        key, _ = create_api_key(services.db, services.settings, "big", env="test", max_upload_bytes=4 * 1024 * 1024)
        data = b"a" * (2 * 1024 * 1024)
        assert (await upload(client, data, "a.txt")).status_code == 413
        assert (await upload(client, data, "a.txt", headers={"X-API-Key": key})).status_code == 202


# ---- item 7: cursor and flat profile keys on GET /result; agent salt in public mode ----


def _capture_renderer(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    real = rendering._call_renderer

    def spy(result: Any, profile: str, fmt: str, overrides: dict[str, Any]) -> Any:
        seen.append({"profile": profile, **overrides})
        return real(result, profile, fmt, {k: v for k, v in overrides.items() if k != "cursor"})

    monkeypatch.setattr(rendering, "_call_renderer", spy)
    return seen


async def test_result_accepts_flat_keys_and_cursor(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    seen = _capture_renderer(monkeypatch)
    r = await upload(
        client, b"# Title" + bytes([10, 10]) + b"Body text." + bytes([10]), "a.md", content_type="text/markdown"
    )
    job_id = r.json()["job"]["id"]
    await wait_for_state(client, job_id)
    flat = await client.get(f"/v1/jobs/{job_id}/result", params={"max_tokens": "500"})
    assert flat.status_code == 200, flat.text
    assert seen[-1]["max_tokens"] == 500
    dotted = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": "rag", "chunks.chunk_tokens": "200"})
    assert dotted.status_code == 200, dotted.text
    assert seen[-1]["chunks.chunk_tokens"] == 200
    paged = await client.get(f"/v1/jobs/{job_id}/result", params={"cursor": "123"})
    assert paged.status_code == 200, paged.text
    assert seen[-1]["cursor"] == "123"  # passed through as an opaque string
    bad = await client.get(f"/v1/jobs/{job_id}/result", params={"bogus_key": "1"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_request"


async def test_public_mode_forces_random_agent_salt(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    seen = _capture_renderer(monkeypatch)
    settings = settings_factory(public_mode=True, jwt_secret=PUBLIC_SECRET, key_pepper=PUBLIC_SECRET)
    async with api_client(settings) as (client, _):
        r = await upload(client, b"hello agent\n", "a.txt", options={"profile": "agent"})
        job_id = r.json()["job"]["id"]
        assert (await wait_for_state(client, job_id))["state"] == "done"
        assert seen[-1]["agent_salt"] == "random"
        res = await client.get(f"/v1/jobs/{job_id}/result", params={"agent_salt": "deterministic"})
        assert res.status_code == 200
        assert seen[-1]["agent_salt"] == "random"
        full = await client.get(f"/v1/jobs/{job_id}/result", params={"profile": "full"})
        assert full.status_code == 200
        assert "agent_salt" not in seen[-1]


async def test_self_host_keeps_deterministic_agent_salt(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    seen = _capture_renderer(monkeypatch)
    r = await upload(client, b"hello agent\n", "a.txt", options={"profile": "agent"})
    await wait_for_state(client, r.json()["job"]["id"])
    assert "agent_salt" not in seen[-1]


# ---- item 8: the dedup / IR-cache key covers schema, converter, and engine versions ----


async def test_stale_ir_cache_key_is_not_deduplicated(client_app: Any) -> None:
    from intomd_api import ircache

    client, app = client_app
    services = app.state.services
    first = await upload(client, b"cache me\n", "a.txt")
    job_id = first.json()["job"]["id"]
    await wait_for_state(client, job_id)
    row = services.jobs.require(job_id)
    assert row.ir_cache_key == ircache.ir_cache_key(ircache.current_schema_version(), row.converter_id)
    again = await upload(client, b"cache me\n", "a.txt")
    assert again.status_code == 200 and again.json()["job"]["id"] == job_id
    services.jobs.update(job_id, ir_cache_key="0" * 64)  # as if produced by an older release
    fresh = await upload(client, b"cache me\n", "a.txt")
    assert fresh.status_code == 202
    assert fresh.json()["job"]["id"] != job_id


def test_ir_cache_key_changes_with_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    from intomd_api import ircache

    base = ircache.ir_cache_key("1", "text.plain")
    assert ircache.ir_cache_key("1.1", "text.plain") != base
    assert ircache.ir_cache_key("1", "text.markdown_passthrough") != base
    monkeypatch.setattr(ircache, "engine_version", lambda: "9.9.9")
    assert ircache.ir_cache_key("1", "text.plain") != base


# ---- item 9: experimental_disabled maps to 422 ----


async def test_experimental_disabled_is_422(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    import intomd.pipeline
    from intomd.registry import ConversionError

    def refuse(*args: Any, **kwargs: Any) -> Any:
        err = ConversionError("experimental only", user_message="Experimental converters are disabled.")
        err.code = "experimental_disabled"  # type: ignore[attr-defined]
        raise err

    monkeypatch.setattr(intomd.pipeline, "convert_ref", refuse)
    r = await upload(client, b"x\n", "a.txt")
    job_id = r.json()["job"]["id"]
    body = await wait_for_state(client, job_id)
    assert body["error"]["code"] == "experimental_disabled"
    assert body["error"]["status"] == 422
    waited = await upload(client, b"y\n", "b.txt", params={"wait": 10})
    assert waited.status_code == 422
    assert waited.json()["error"]["code"] == "experimental_disabled"


async def test_unknown_conversion_codes_are_not_passed_through(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    import intomd.pipeline
    from intomd.registry import ConversionError

    def refuse(*args: Any, **kwargs: Any) -> Any:
        err = ConversionError("nope")
        err.code = "rate_limited"  # type: ignore[attr-defined]
        raise err

    monkeypatch.setattr(intomd.pipeline, "convert_ref", refuse)
    r = await upload(client, b"x\n", "a.txt")
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["error"]["code"] == "conversion_failed"


def test_openapi_lists_new_error_codes() -> None:
    from intomd_api.openapi import openapi_document

    description = json.loads(openapi_document())["info"]["description"]
    for code in ("experimental_disabled", "fetch_depth_exceeded", "result_too_large"):
        assert f"`{code}`" in description
