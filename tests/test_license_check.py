"""tools/license_check.py covers every extra except nonfree (tools/license_allowlist.toml, docs/licenses.md)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def lc() -> ModuleType:
    spec = importlib.util.spec_from_file_location("license_check", ROOT / "tools" / "license_check.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["license_check"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_export_covers_every_extra_but_nonfree(lc: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="torch==2.14.1\n", stderr="")

    monkeypatch.setattr(lc.subprocess, "run", fake_run)
    assert [p.name for p in lc.exported_packages()] == ["torch"]
    (cmd,) = seen
    assert "--all-extras" in cmd
    assert cmd[cmd.index("--no-extra") + 1] == "nonfree"


def test_platform_runtime_exception_is_explicit(lc: ModuleType) -> None:
    policy = lc.load_policy(lc.DEFAULT_ALLOWLIST, lc.DEFAULT_OVERRIDES)
    # The exception class is a named list with a reason, not a blanket license allowance.
    assert policy.platform_runtime, "expected the [platform_runtime] exception class"
    assert policy.platform_runtime_reason.strip()
    assert "LicenseRef-NVIDIA-Proprietary" not in policy.allow
    verdict = lc.check_package(lc.Package("nvidia-cublas", "13.1.1.3"), policy, offline=True)
    assert verdict.ok and verdict.source == "platform-runtime exception"
    # A package outside the list gets no pass, even under the same license.
    other = lc.check_package(lc.Package("nvidia-something-new", "1.0"), policy, offline=True)
    assert not other.ok


def test_platform_runtime_exception_never_covers_the_default_install(lc: ModuleType) -> None:
    """Every excepted package must come only from an extra: none may be in the no-extras tree."""
    policy = lc.load_policy(lc.DEFAULT_ALLOWLIST, lc.DEFAULT_OVERRIDES)
    default = {p.name for p in lc.exported_packages(extras=False)}
    assert not (default & policy.platform_runtime), sorted(default & policy.platform_runtime)
