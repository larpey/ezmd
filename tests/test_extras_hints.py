"""Every `ezmd[<extra>]` that the code tells a user to install must be an extra `ezmd` declares."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HINT = re.compile(r"ezmd\[([a-z0-9_,-]+)\]")

# Extras the spec names (docs/spec/part4.md 4.3.3) that later phases add. A hint for one of these is allowed
# until its phase lands; remove the entry when the extra is declared.
PENDING = {
    "server": "needs ezmd-api published (Phase 1 release, owner gate)",
    "iwork": "Docling iWork backend, not yet packaged as an extra",
    "ocr": "Phase 2",
    "media": "Phase 2",
    "web": "Phase 3",
    "fetch": "Phase 3",
}


def _declared() -> set[str]:
    data = tomllib.loads((ROOT / "packages/core/pyproject.toml").read_text(encoding="utf-8"))
    return set(data["project"].get("optional-dependencies", {}))


def _hints() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for base in ("packages", "apps"):
        for path in (ROOT / base).rglob("src/**/*.py"):
            for match in HINT.finditer(path.read_text(encoding="utf-8")):
                for extra in match.group(1).split(","):
                    found.setdefault(extra, set()).add(path.relative_to(ROOT).as_posix())
    return found


def test_hinted_extras_are_declared() -> None:
    declared = _declared()
    missing = {extra: sorted(paths) for extra, paths in _hints().items() if extra not in declared | set(PENDING)}
    assert not missing, f"code tells users to install extras ezmd does not declare: {missing}"


def test_pending_extras_are_still_pending() -> None:
    assert not set(PENDING) & _declared(), "remove declared extras from PENDING"


def test_forwarded_extras_exist_on_converters() -> None:
    core = tomllib.loads((ROOT / "packages/core/pyproject.toml").read_text(encoding="utf-8"))
    conv = tomllib.loads((ROOT / "packages/converters/pyproject.toml").read_text(encoding="utf-8"))
    conv_extras = set(conv["project"].get("optional-dependencies", {}))
    for reqs in core["project"]["optional-dependencies"].values():
        for req in reqs:
            m = re.fullmatch(r"ezmd-converters\[([a-z0-9_,-]+)\]", req)
            if m:
                assert set(m.group(1).split(",")) <= conv_extras, req
