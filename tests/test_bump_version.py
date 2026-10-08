"""tools/bump_version.py keeps every recorded version in step with tools/release_version.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    f"{p}/pyproject.toml"
    for p in ("packages/core", "packages/converters", "packages/mcp", "apps/api", "apps/fetch-node")
] + [
    "packages/core/src/intomd/__init__.py",
    "packages/mcp/server.json",
    "packages/sdk-ts/package.json",
]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    return tmp_path


def test_rc_bump_satisfies_release_check(tree: Path) -> None:
    bump, check = _load("bump_version"), _load("release_version")
    bump.bump(tree, "0.9.0rc2", npm=False)
    assert check.check_versions(tree, "0.9.0rc2", "0.9.0-rc2", True) == []
    core = tomllib.loads((tree / "packages/core/pyproject.toml").read_text(encoding="utf-8"))["project"]
    mcp = tomllib.loads((tree / "packages/mcp/pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "intomd-converters==0.9.0rc2" in core["dependencies"]
    assert "intomd==0.9.0rc2" in mcp["dependencies"]
    server = json.loads((tree / "packages/mcp/server.json").read_text(encoding="utf-8"))
    assert server["version"] == "0.9.0rc2" and all(p["version"] == "0.9.0rc2" for p in server["packages"])
    assert '__version__ = "0.9.0rc2"' in (tree / "packages/core/src/intomd/__init__.py").read_text(encoding="utf-8")


def test_final_bump_with_npm(tree: Path) -> None:
    bump, check = _load("bump_version"), _load("release_version")
    bump.bump(tree, "0.9.0", npm=True)
    assert check.check_versions(tree, "0.9.0", "0.9.0", False) == []


@pytest.mark.parametrize("bad", ["0.9", "v0.9.0", "0.9.0-rc1", "0.9.0rc0"])
def test_rejects_bad_versions(tree: Path, bad: str) -> None:
    with pytest.raises(SystemExit):
        _load("bump_version").bump(tree, bad, npm=False)


def test_npm_refuses_release_candidates(tree: Path) -> None:
    with pytest.raises(SystemExit):
        _load("bump_version").bump(tree, "0.9.0rc1", npm=True)


def test_repo_versions_are_consistent() -> None:
    """The checked-in Python versions agree with each other and with the inter-package pins."""
    versions = {
        tomllib.loads((ROOT / p / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        for p in ("packages/core", "packages/converters", "packages/mcp")
    }
    assert len(versions) == 1
    (version,) = versions
    core = tomllib.loads((ROOT / "packages/core/pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert f"intomd-converters=={version}" in core["dependencies"]
