"""HTTP transport: bearer token on every request, loopback by default, refusal to bind publicly without a
token (docs/spec/part4.md 4.4.3 and 4.4.6, part1 8.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import make_server
from starlette.testclient import TestClient

from ezmd_mcp.cli import StartupError, main, parse_args, resolve_http
from ezmd_mcp.http import build_http_app

TOKEN = "t0ken-for-tests-0123456789"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def app(root: Path) -> Any:
    return build_http_app(make_server(root), token=TOKEN)


def test_missing_token_is_401(app: Any) -> None:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        r = c.post("/mcp", json=INIT, headers=HEADERS)
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")
    assert r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("auth", ["Bearer wrong-token-wrong-token", "Basic " + TOKEN, TOKEN, "Bearer "])
def test_invalid_token_is_401(app: Any, auth: str) -> None:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        r = c.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": auth})
    assert r.status_code == 401


def test_valid_token_reaches_the_mcp_app(app: Any) -> None:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        r = c.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200, r.text
        assert "ezmd" in r.text  # serverInfo.name
        assert c.get("/mcp", headers={"Authorization": "Bearer nope-nope-nope-nope"}).status_code == 401


def test_binds_loopback_by_default() -> None:
    cfg = resolve_http(parse_args(["--transport", "http"]), env={})
    assert cfg.host == "127.0.0.1" and cfg.port == 8765
    assert cfg.token and cfg.generated  # a token is required by default; one is generated for loopback


def test_bind_from_env_and_token_from_env() -> None:
    env = {"EZMD_MCP_BIND": "0.0.0.0", "EZMD_MCP_TOKEN": TOKEN, "EZMD_MCP_PORT": "9000"}
    cfg = resolve_http(parse_args(["--transport", "http"]), env=env)
    assert (cfg.host, cfg.port, cfg.token, cfg.generated) == ("0.0.0.0", 9000, TOKEN, False)


def test_refuses_public_bind_without_token(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EZMD_MCP_TOKEN", raising=False)
    monkeypatch.delenv("EZMD_MCP_BIND", raising=False)
    code = main(["--transport", "http", "--host", "0.0.0.0"])
    assert code != 0
    err = capsys.readouterr().err
    assert "refusing to bind non-loopback host '0.0.0.0' without a bearer token" in err
    with pytest.raises(StartupError, match="loopback"):
        resolve_http(parse_args(["--transport", "http", "--host", "10.0.0.5", "--token", TOKEN, "--no-auth"]), env={})
    with pytest.raises(StartupError, match="16 characters"):
        resolve_http(parse_args(["--transport", "http", "--token", "short"]), env={})


def test_no_auth_only_on_loopback() -> None:
    cfg = resolve_http(parse_args(["--transport", "http", "--no-auth"]), env={})
    assert cfg.token is None
    assert resolve_http(parse_args(["--transport", "http", "--host", "::1", "--no-auth"]), env={}).token is None


def test_bad_startup_options_exit_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--remote", "ftp://example.com"]) == 2
    assert "--remote must be an http(s) URL" in capsys.readouterr().err
