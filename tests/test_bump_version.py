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
    "packages/core/src/ezmd/__init__.py",
    "packages/mcp/server.json",
    "packages/sdk-ts/package.json",
    "packages/sdk-ts/src/version.ts",
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
    assert "ezmd-converters==0.9.0rc2" in core["dependencies"]
    assert "ezmd==0.9.0rc2" in mcp["dependencies"]
    assert core["optional-dependencies"]["mcp"] == ["ezmd-mcp==0.9.0rc2"]
    assert "ezmd-mcp==0.9.0rc2" in core["optional-dependencies"]["all"]
    server = json.loads((tree / "packages/mcp/server.json").read_text(encoding="utf-8"))
    assert server["version"] == "0.9.0rc2" and all(p["version"] == "0.9.0rc2" for p in server["packages"])
    assert '__version__ = "0.9.0rc2"' in (tree / "packages/core/src/ezmd/__init__.py").read_text(encoding="utf-8")


def test_final_bump_with_npm(tree: Path) -> None:
    bump, check = _load("bump_version"), _load("release_version")
    sdk_before = (tree / "packages/sdk-ts/src/version.ts").read_text(encoding="utf-8")
    bump.bump(tree, "0.9.0", npm=True)
    assert check.check_versions(tree, "0.9.0", "0.9.0", False) == []
    sdk = (tree / "packages/sdk-ts/src/version.ts").read_text(encoding="utf-8")
    assert sdk == sdk_before.replace(sdk_before.split('"')[1], "0.9.0")
    assert 'export const SDK_VERSION = "0.9.0";' in sdk


def test_rc_bump_leaves_npm_sdk_alone(tree: Path) -> None:
    before = {
        r: (tree / r).read_text(encoding="utf-8")
        for r in ("packages/sdk-ts/package.json", "packages/sdk-ts/src/version.ts")
    }
    _load("bump_version").bump(tree, "0.9.0rc2", npm=False)
    assert {r: (tree / r).read_text(encoding="utf-8") for r in before} == before


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
    assert f"ezmd-converters=={version}" in core["dependencies"]
    assert core["optional-dependencies"]["mcp"] == [f"ezmd-mcp=={version}"]
