"""Config file locations and precedence: flags > environment > config file > defaults (part4 4.2.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import ezmd.library
from ezmd.cli import app
from ezmd.cli.config import ConfigError, config_path, load_config

runner = CliRunner()


def test_platform_paths() -> None:
    env = {"HOME": "/home/u", "APPDATA": "C:/Users/u/AppData/Roaming"}
    assert config_path(env, "linux") == Path("/home/u/.config/ezmd/config.toml")
    assert config_path({**env, "XDG_CONFIG_HOME": "/xdg"}, "linux") == Path("/xdg/ezmd/config.toml")
    assert config_path(env, "darwin") == Path("/home/u/Library/Application Support/ezmd/config.toml")
    assert config_path(env, "win32") == Path("C:/Users/u/AppData/Roaming/ezmd/config.toml")
    assert config_path({**env, "EZMD_CONFIG": "/etc/x.toml"}, "win32") == Path("/etc/x.toml")


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


FILE = """
[defaults]
profile = "rag"
format = "txt"
sidecar = false
[remote]
url = "https://file.example"
api_key = "from-file"
[limits]
max_file_mb = 2
[engines]
pdf = "docling"
[future]
x = 1
"""


def test_file_values_and_env_overrides(tmp_path: Path) -> None:
    path = _write(tmp_path, FILE)
    cfg = load_config({"EZMD_CONFIG": str(path)})
    assert (cfg.profile, cfg.format, cfg.sidecar, cfg.remote_url, cfg.api_key) == (
        "rag",
        "txt",
        False,
        "https://file.example",
        "from-file",
    )
    assert cfg.engines == {"pdf": "docling"} and cfg.max_file_mb == 2 and cfg.unknown_keys == ("future",)
    env = {
        "EZMD_CONFIG": str(path),
        "EZMD_PROFILE": "agent",
        "EZMD_FORMAT": "md",
        "EZMD_REMOTE": "",
        "EZMD_API_KEY": "from-env",
        "EZMD_SIDECAR": "yes",
    }
    cfg = load_config(env)
    assert (cfg.profile, cfg.format, cfg.sidecar, cfg.remote_url, cfg.api_key) == ("agent", "md", True, "", "from-env")


@pytest.mark.parametrize(
    "text",
    ["[defaults\nprofile=1", '[defaults]\nprofile = "tiny"', "[defaults]\nsidecar = 1", "defaults = 3"],
)
def test_invalid_config_raises(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigError):
        load_config({"EZMD_CONFIG": str(_write(tmp_path, text))})


def test_missing_explicit_config_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config({"EZMD_CONFIG": str(tmp_path / "absent.toml")})
    assert load_config({"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)}, "linux").path is None


def _spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    real = ezmd.library.convert

    def spy(source: Any, **kw: Any) -> Any:
        seen.update(kw)
        return real(source, **kw)

    monkeypatch.setattr(ezmd.library, "convert", spy)
    return seen


def test_precedence_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "a.txt"
    src.write_text("Hello\n=====\n\nbody\n", encoding="utf-8")
    cfg = _write(tmp_path, '[defaults]\nprofile = "rag"\nformat = "txt"\n[limits]\nmax_file_mb = 1\n')
    monkeypatch.setenv("EZMD_CONFIG", str(cfg))
    seen = _spy(monkeypatch)

    res = runner.invoke(app, ["convert", str(src), "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert (payload["profile"], payload["format"]) == ("rag", "txt")
    assert seen["options"].max_bytes == 1024 * 1024

    monkeypatch.setenv("EZMD_PROFILE", "agent")
    assert json.loads(runner.invoke(app, ["convert", str(src), "--json"]).stdout)["profile"] == "agent"

    flagged = runner.invoke(app, ["convert", str(src), "--json", "-p", "compact", "-f", "md", "--opt", "max_bytes=99"])
    payload = json.loads(flagged.stdout)
    assert (payload["profile"], payload["format"]) == ("compact", "md")
    assert seen["options"].max_bytes == 99


def test_bad_config_exits_2_with_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_CONFIG", str(_write(tmp_path, "[defaults\n")))
    res = runner.invoke(app, ["convert", "x.txt", "--json"])
    assert res.exit_code == 2
    assert json.loads(res.stdout)["status"] == "failed"


def test_config_api_key_sent_to_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    import ezmd.cli.remote as remote

    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"version": "1", "converters": []})

    monkeypatch.setattr(remote, "transport_factory", lambda: httpx.MockTransport(handler))
    monkeypatch.setenv(
        "EZMD_CONFIG", str(_write(tmp_path, '[remote]\nurl = "https://cfg.example"\napi_key = "cfg-key"\n'))
    )
    assert runner.invoke(app, ["capabilities", "--json"]).exit_code == 0
    assert seen[0].url.host == "cfg.example" and seen[0].headers["x-api-key"] == "cfg-key"
