from __future__ import annotations

import importlib.util
from pathlib import Path

from ezmd.warnings.codes import CODES, WarningKind, spec_for

ROOT = Path(__file__).resolve().parents[3]


def test_every_code_has_a_spec_and_suggestion() -> None:
    assert set(CODES) == set(WarningKind)
    for kind, spec in CODES.items():
        assert spec.code is kind
        assert kind.value == kind.name.lower()
        assert spec.description.strip() and spec.suggestion.strip()
        assert spec.severity in ("info", "warning", "error")
    assert spec_for("pages_without_text").code is WarningKind.PAGES_WITHOUT_TEXT


def test_docs_warnings_md_is_current() -> None:
    spec = importlib.util.spec_from_file_location("gen_warnings_doc", ROOT / "tools" / "gen_warnings_doc.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "warnings.md").read_text(encoding="utf-8")
    assert committed == mod.render(), "docs/warnings.md is stale; run `uv run python tools/gen_warnings_doc.py`"
