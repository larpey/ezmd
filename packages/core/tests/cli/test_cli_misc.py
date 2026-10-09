"""version, capabilities, detect, serve, completion, and the 40-line --help budget (part4 4.2.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer.core
import typer.main
from typer.testing import CliRunner

import ezmd.cli.info as info
from ezmd import __version__
from ezmd.cli import app

runner = CliRunner()
COMMANDS = list(getattr(typer.main.get_command(app), "commands", {}))


def test_every_phase1_command_exists() -> None:
    assert {"convert", "batch", "doctor", "serve", "capabilities", "version", "detect"} <= set(COMMANDS)


@pytest.mark.parametrize("rich", [True, False])
@pytest.mark.parametrize("command", [None, *COMMANDS])
def test_help_fits_in_40_lines(command: str | None, rich: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(typer.core, "HAS_RICH", rich)
    args = [command, "--help"] if command else ["--help"]
    res = runner.invoke(app, args, env={"COLUMNS": "100", "NO_COLOR": "1"}, terminal_width=100)
    assert res.exit_code == 0
    lines = res.output.rstrip("\n").splitlines()
    assert len(lines) <= 40, f"ezmd {command} --help is {len(lines)} lines"


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_scripts_generate_and_install(
    shell: str, monkeypatch: pytest.MonkeyPatch, isolated_cli_env: Path
) -> None:
    monkeypatch.setenv("_TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION", "1")
    shown = runner.invoke(app, ["--show-completion", shell], prog_name="ezmd")
    assert shown.exit_code == 0 and "_EZMD_COMPLETE" in shown.output
    installed = runner.invoke(app, ["--install-completion", shell], prog_name="ezmd")
    assert installed.exit_code == 0, installed.output
    assert f"{shell} completion installed" in installed.output
    assert any(isolated_cli_env.rglob("*")), "nothing was written under the isolated home"


def test_version_json_and_text() -> None:
    data = json.loads(runner.invoke(app, ["version", "--json"]).stdout)
    assert data["version"] == __version__ and set(data) == {"version", "commit", "build_date"}
    assert runner.invoke(app, ["version"]).stdout.startswith(f"ezmd {__version__}")


def test_version_reads_build_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "_build_info.json"
    f.write_text(json.dumps({"commit": "abc123", "build_date": "2026-10-01"}), encoding="utf-8")
    monkeypatch.setattr(info, "_BUILD_FILE", f)
    assert info.build_info() == {"version": __version__, "commit": "abc123", "build_date": "2026-10-01"}


def test_git_commit_from_worktree_layout(tmp_path: Path) -> None:
    common = tmp_path / "repo" / ".git"
    wt_git = common / "worktrees" / "wt"
    (common / "refs" / "heads").mkdir(parents=True)
    wt_git.mkdir(parents=True)
    (common / "refs" / "heads" / "feature").write_text("f" * 40 + "\n", encoding="utf-8")
    (wt_git / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
    wt = tmp_path / "wt"
    (wt / "pkg").mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {wt_git.as_posix()}\n", encoding="utf-8")
    assert info._git_commit(wt / "pkg") == "f" * 40


def test_capabilities_local() -> None:
    data = json.loads(runner.invoke(app, ["capabilities", "--json"]).stdout)
    assert any(r["id"] == "text.plain" for r in data["converters"])
    assert "text.plain" in runner.invoke(app, ["capabilities"], env={"COLUMNS": "200"}).stdout


def test_detect(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("plain words here\n", encoding="utf-8")
    res = runner.invoke(app, ["detect", str(p)])
    assert res.exit_code == 0 and json.loads(res.stdout)["mime"].startswith("text/")


def test_serve_refuses_public_bind() -> None:
    assert runner.invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code == 2


def test_serve_without_the_api_points_at_self_hosting(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "ezmd_api.main", None)
    res = runner.invoke(app, ["serve"])
    assert res.exit_code == 2
    assert "pip install ezmd-api" not in res.output
    assert "selfhost" in res.output and "Docker" in res.output, res.output
