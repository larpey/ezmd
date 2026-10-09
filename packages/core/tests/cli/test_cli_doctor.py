"""`ezmd doctor` (part4 4.2.2 item 5): MISSING rows exit 2 only when an installed extra needs them."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import ezmd.cli.doctor as doctor
from ezmd.cli import app

runner = CliRunner()


def _no_ffmpeg(monkeypatch: pytest.MonkeyPatch, extras: set[str]) -> None:
    real = doctor._which
    monkeypatch.setattr(doctor, "_which", lambda n: None if n in ("ffmpeg", "ffprobe") else real(n))
    monkeypatch.setattr(doctor, "installed_extras", lambda: set(extras))


def _row(payload: dict[str, object], name: str) -> dict[str, object]:
    checks = payload["checks"]
    assert isinstance(checks, list)
    return next(c for c in checks if c["name"] == name)


def test_missing_ffmpeg_without_media_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_ffmpeg(monkeypatch, set())
    res = runner.invoke(app, ["doctor", "--json"])
    payload = json.loads(res.stdout)
    row = _row(payload, "ffmpeg")
    assert row["status"] == "MISSING" and "Install ffmpeg" in str(row["fix"]) and row["fatal"] is False
    assert res.exit_code == 0, payload


def test_missing_ffmpeg_with_media_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_ffmpeg(monkeypatch, {"media"})
    res = runner.invoke(app, ["doctor", "--json"])
    assert res.exit_code == 2
    assert _row(json.loads(res.stdout), "ffmpeg")["fatal"] is True
    table = runner.invoke(app, ["doctor"])
    assert table.exit_code == 2 and "MISSING" in table.stdout and "ffmpeg" in table.stderr


def test_rows_cover_the_spec_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(doctor, "installed_extras", lambda: {"docs"})
    payload = json.loads(runner.invoke(app, ["doctor", "--json"]).stdout)
    names = {c["name"] for c in payload["checks"]}
    expected = {"python", "ezmd", "ffmpeg", "ffprobe", "pandoc", "libreoffice", "libmagic", "magika model"}
    assert expected | {"cache dir", "config dir", "redis", "docling", "extra: media"} <= names
    assert _row(payload, "redis")["status"] == "MISSING"  # configured but unreachable
    assert payload["exit_code"] == 2


def test_quiet_hides_ok_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "installed_extras", lambda: set())
    res = runner.invoke(app, ["doctor", "--quiet"], env={"COLUMNS": "200"})
    assert res.stdout.strip()
    assert not any("python" in line.split() for line in res.stdout.splitlines())


def _pyproject_extras() -> set[str]:
    import tomllib
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return set(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["optional-dependencies"])


def test_extra_rows_are_the_published_extras_plus_planned_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "installed_extras", lambda: set())
    payload = json.loads(runner.invoke(app, ["doctor", "--json"]).stdout)
    rows = {c["name"][len("extra: ") :]: c for c in payload["checks"] if str(c["name"]).startswith("extra: ")}
    published = _pyproject_extras() - {"all"}
    assert published <= set(rows), sorted(rows)
    assert {"data", "7z", "nonfree"} <= set(rows)
    for extra in published:
        assert rows[extra]["fix"] == f"pip install 'ezmd[{extra}]'" or extra == "nonfree", rows[extra]
    for extra, row in rows.items():
        if extra not in published:
            assert extra in doctor.PLANNED_EXTRAS, extra
            assert "pip install" not in str(row["fix"]) and "later release" in str(row["fix"]), row


def test_installed_extras_needs_the_extra_packages_not_just_ezmd_converters() -> None:
    import importlib.util

    found = doctor.installed_extras()
    if importlib.util.find_spec("pyarrow") is None:
        assert "data" not in found
    if importlib.util.find_spec("py7zr") is None:
        assert "7z" not in found
    if importlib.util.find_spec("docling") is None:
        assert "docs" not in found and "all" not in found
    if importlib.util.find_spec("ezmd_mcp") is not None:
        assert "mcp" in found
    assert not found & set(doctor.PLANNED_EXTRAS)


def test_no_fix_names_an_extra_that_does_not_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    import re

    monkeypatch.setenv("EZMD_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(doctor, "installed_extras", lambda: set())
    monkeypatch.setattr(doctor.importlib, "import_module", _no_redis(doctor.importlib.import_module))
    payload = json.loads(runner.invoke(app, ["doctor", "--json"]).stdout)
    published = _pyproject_extras()
    for row in payload["checks"]:
        for extra in re.findall(r"ezmd\[([a-z0-9_-]+)\]", str(row["fix"])):
            assert extra in published, row


def _no_redis(real: object) -> object:
    def fake(name: str) -> object:
        if name == "redis":
            raise ImportError(name)
        return real(name)  # type: ignore[operator]

    return fake
