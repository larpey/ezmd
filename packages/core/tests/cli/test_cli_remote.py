"""`--remote`: the REST client, stubbed with httpx.MockTransport (no network)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import ezmd.cli.remote as remote
from ezmd import __version__
from ezmd.cli import app

runner = CliRunner()
BASE = "https://ezmd.example"
PAYLOAD = {
    "markdown": '---\ntitle: "Remote"\n---\n\nremote body\n',
    "frontmatter": {"title": "Remote", "tokens": 12, "truncated": False, "warnings": ["encoding_uncertain"]},
    "sidecar": None,
    "chunks": [],
}
JOB = {"id": "job123", "state": "done", "progress": 1.0}


def _install(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    monkeypatch.setattr(remote, "transport_factory", lambda: httpx.MockTransport(record))
    monkeypatch.setattr(remote, "sleep", lambda s: None)
    return seen


def _file(tmp_path: Path) -> Path:
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    return p


def test_immediate_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/convert" and req.url.params["wait"] == "30"
        return httpx.Response(200, json=PAYLOAD, headers={"X-Ezmd-Job": json.dumps(JOB)})

    monkeypatch.setenv("EZMD_API_KEY", "k-secret")
    seen = _install(monkeypatch, handler)
    res = runner.invoke(app, ["convert", str(_file(tmp_path)), "--remote", BASE, "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert "remote body" in payload["markdown"] and payload["tokens"] == 12
    assert payload["warnings"][0]["kind"] == "encoding_uncertain"
    req = seen[0]
    assert req.headers["user-agent"] == f"ezmd-cli/{__version__}"
    assert req.headers["x-api-key"] == "k-secret"
    assert b'name="file"' in req.content and b'name="options"' in req.content


def test_poll_then_result_and_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter(["converting", "rendering", "done"])

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(202, json={"job": {"id": "j1", "state": "queued"}, "deduplicated": False})
        if req.url.path == "/v1/jobs/j1":
            return httpx.Response(200, json={"id": "j1", "state": next(states), "progress": 0.5})
        if req.url.path == "/v1/jobs/j1/result":
            if req.url.params["format"] == "txt":
                return httpx.Response(200, text="remote body as text\n")
            return httpx.Response(200, json=PAYLOAD)
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "nope"}})

    seen = _install(monkeypatch, handler)
    res = runner.invoke(app, ["convert", str(_file(tmp_path)), "--remote", BASE, "--format", "txt"])
    assert res.exit_code == 0, res.output
    assert res.stdout == "remote body as text\n"
    assert [r.url.path for r in seen].count("/v1/jobs/j1") == 3


def test_url_source_posts_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert body["url"] == "https://example.com/" and body["profile"] == "compact"
        return httpx.Response(200, json=PAYLOAD, headers={"X-Ezmd-Job": json.dumps(JOB)})

    _install(monkeypatch, handler)
    res = runner.invoke(app, ["convert", "https://example.com/", "--remote", BASE, "-p", "compact"])
    assert res.exit_code == 0, res.output
    assert "remote body" in res.stdout


@pytest.mark.parametrize(
    ("status", "code", "exit_code"),
    [(415, "unsupported_media_type", 6), (413, "input_too_large", 5), (422, "platform_disabled", 4), (500, "x", 1)],
)
def test_error_codes_map_to_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int, code: str, exit_code: int
) -> None:
    _install(monkeypatch, lambda req: httpx.Response(status, json={"error": {"code": code, "message": "m"}}))
    res = runner.invoke(app, ["convert", str(_file(tmp_path)), "--remote", BASE, "--json"])
    assert res.exit_code == exit_code
    assert json.loads(res.stdout)["error"]["code"] == code


def test_failed_job_while_polling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(202, json={"job": {"id": "j2", "state": "queued"}})
        err = {"code": "conversion_failed", "message": "Every converter failed."}
        return httpx.Response(200, json={"id": "j2", "state": "failed", "error": err})

    _install(monkeypatch, handler)
    res = runner.invoke(app, ["convert", str(_file(tmp_path)), "--remote", BASE, "--json"])
    assert res.exit_code == 1
    assert json.loads(res.stdout)["warnings"][0]["message"] == "Every converter failed."


def test_remote_from_env_and_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = {"version": "9.9", "converters": [{"id": "x.y", "family": "x", "mimes": ["a/b"], "loaded": True}]}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/capabilities"
        return httpx.Response(200, json=caps)

    _install(monkeypatch, handler)
    monkeypatch.setenv("EZMD_REMOTE", BASE)
    res = runner.invoke(app, ["capabilities", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout)["version"] == "9.9"
    table = runner.invoke(app, ["capabilities"])
    assert "x.y" in table.stdout


def test_unreachable_remote_exit_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    _install(monkeypatch, handler)
    res = runner.invoke(app, ["convert", str(_file(tmp_path)), "--remote", BASE, "--json"])
    assert res.exit_code == 1
    assert json.loads(res.stdout)["error"]["code"] == "remote_unreachable"


def test_bad_remote_url_exit_2(tmp_path: Path) -> None:
    res = runner.invoke(app, ["convert", str(_file(tmp_path)), "--remote", "ftp://nope"])
    assert res.exit_code == 2
