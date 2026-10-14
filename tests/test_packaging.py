"""Packaging metadata guards: dependency bounds that survive `pip install --pre`, and license files in dists."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
# Every workspace member with dependencies; the first three are published to PyPI (release.yml python-dist).
MEMBERS = ("packages/core", "packages/converters", "packages/mcp", "apps/api", "apps/fetch-node")
PUBLISHED = ("packages/core", "packages/converters", "packages/mcp")
# Direct dependencies with a pre-release newer than their latest final on PyPI, mapped to the first release
# series that has one (checked against the PyPI JSON API when this list was written; last on 2026-10-13).
# `pip install --pre ezmd` lets those pre-releases satisfy an open `>=` bound, so each declaration must stay
# below that series. httpx 1.0.devN dropped httpcore, which ezmd.core.netguard imports; defusedxml 0.8.0rc2
# and openpyxl 3.2.0b1 were picked by `--pre` in the rc4 install test.
PRERELEASE_SERIES = {"httpx": "1.0", "lxml": "7.0", "defusedxml": "0.8", "openpyxl": "3.2"}
# Modules imported directly that only arrive transitively unless declared (import name, distribution).
IMPORTED_DIRECTLY = {"httpcore": "httpcore"}


def _project(member: str) -> dict[str, Any]:
    data = tomllib.loads((ROOT / member / "pyproject.toml").read_text(encoding="utf-8"))
    project: dict[str, Any] = data["project"]
    return project


def _requirements(member: str) -> list[Requirement]:
    project = _project(member)
    reqs = [Requirement(r) for r in project.get("dependencies", [])]
    for extra in project.get("optional-dependencies", {}).values():
        reqs += [Requirement(r) for r in extra]
    return reqs


def _names(member: str) -> set[str]:
    return {r.name.lower() for r in _requirements(member)}


@pytest.mark.parametrize("member", MEMBERS)
def test_prerelease_series_are_capped(member: str) -> None:
    for req in _requirements(member):
        series = PRERELEASE_SERIES.get(req.name.lower())
        if series is None:
            continue
        first_bad = Version(f"{series}.dev0")
        assert not req.specifier.contains(first_bad, prereleases=True), (
            f"{member}: {req} admits {req.name} {series} pre-releases under --pre; add an upper bound <{series}"
        )


@pytest.mark.parametrize("member", MEMBERS)
def test_directly_imported_transitives_are_declared(member: str) -> None:
    pattern = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(map(re.escape, IMPORTED_DIRECTLY))})\b", re.MULTILINE)
    imported = {
        m.group(1) for path in (ROOT / member / "src").rglob("*.py") for m in pattern.finditer(path.read_text("utf-8"))
    }
    missing = {IMPORTED_DIRECTLY[i] for i in imported} - _names(member)
    assert not missing, f"{member} imports {sorted(missing)} but does not declare it as a dependency"


def test_core_mcp_extras_pin_ezmd_mcp_exactly() -> None:
    project = _project("packages/core")
    version = project["version"]
    extras = project["optional-dependencies"]
    for name in ("mcp", "all"):
        pins = [r for r in extras[name] if Requirement(r).name == "ezmd-mcp"]
        assert pins == [f"ezmd-mcp=={version}"], f"extra {name!r}: {pins}"


@pytest.mark.parametrize("member", PUBLISHED)
@pytest.mark.parametrize("name", ["LICENSE", "NOTICE"])
def test_license_copies_match_root(member: str, name: str) -> None:
    copy = ROOT / member / name
    assert copy.is_file(), f"{member}/{name} is missing (hatchling only packs files inside the package dir)"
    assert copy.read_bytes() == (ROOT / name).read_bytes(), f"{member}/{name} drifted from the root {name}"


@pytest.mark.parametrize("member", PUBLISHED)
def test_license_files_declared(member: str) -> None:
    assert _project(member).get("license-files") == ["LICENSE", "NOTICE"]


# The only top-level directory each wheel may carry besides its dist-info. `ezmd/testing` stays in the core
# wheel on purpose: the spec ships `ezmd-score`/`ezmd-golden` with `ezmd`, and `ezmd shadow` imports it (D-0051).
WHEEL_PACKAGES = {"packages/core": "ezmd", "packages/converters": "ezmd_converters", "packages/mcp": "ezmd_mcp"}


def _uv() -> str | None:
    return os.environ.get("UV") or shutil.which("uv")


@pytest.mark.slow
@pytest.mark.parametrize("member", PUBLISHED)
def test_built_dists_carry_license_and_notice(member: str, tmp_path: Path) -> None:
    uv = _uv()
    if uv is None:
        pytest.skip("uv not available to build the dists")
    subprocess.run(
        [uv, "build", "--quiet", "--out-dir", str(tmp_path), str(ROOT / member)],
        check=True,
        capture_output=True,
        env={**os.environ, "UV_NO_PROGRESS": "1"},
    )
    (wheel,) = tmp_path.glob("*.whl")
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    dist_info = next(n.split("/", 1)[0] for n in names if n.split("/", 1)[0].endswith(".dist-info"))
    package = WHEEL_PACKAGES[member]
    stray = sorted(n for n in names if n.split("/", 1)[0] not in (package, dist_info) or "__pycache__" in n)
    assert not stray, f"{wheel.name} ships files outside {package}/ (tests, tools, caches): {stray[:10]}"
    for f in ("LICENSE", "NOTICE"):
        assert f"{dist_info}/licenses/{f}" in names, f"{wheel.name} lacks {dist_info}/licenses/{f}"
    (sdist,) = tmp_path.glob("*.tar.gz")
    with tarfile.open(sdist) as tf:
        members = {m.name.split("/", 1)[1] for m in tf.getmembers() if "/" in m.name}
    assert {"LICENSE", "NOTICE"} <= members, f"{sdist.name} lacks LICENSE/NOTICE"
