"""Generated docs pages stay in sync with the code they describe (docs/cli.md, docs/selfhost.md)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_docs_cli_md_is_current() -> None:
    gen = _load("gen_cli_doc")
    committed = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    assert committed == gen.render(), "docs/cli.md is stale; run `uv run python tools/gen_cli_doc.py`"


def test_cli_doc_covers_every_command() -> None:
    gen = _load("gen_cli_doc")
    text = gen.render()
    assert gen.commands(), "no CLI commands found"
    for name in gen.commands():
        assert f"## intomd {name}" in text


def test_selfhost_env_table_is_current() -> None:
    pytest.importorskip("intomd_api")
    gen = _load("gen_env_doc")
    committed = (ROOT / "docs" / "selfhost.md").read_text(encoding="utf-8")
    assert committed == gen.update(committed), (
        "docs/selfhost.md env table is stale; run `uv run python tools/gen_env_doc.py`"
    )


def test_every_setting_is_documented() -> None:
    pytest.importorskip("intomd_api")
    gen = _load("gen_env_doc")
    from intomd_api.settings import env_names

    assert gen.missing_descriptions() == []
    assert set(gen.DESCRIPTIONS) <= set(gen.Settings.model_fields), "DESCRIPTIONS has entries for removed settings"
    table = gen.render_table()
    for name in env_names():
        assert f"`{name}`" in table


def test_errors_md_lists_every_api_error_code() -> None:
    pytest.importorskip("intomd_api")
    from intomd_api.errors import ERROR_STATUS

    text = (ROOT / "docs" / "errors.md").read_text(encoding="utf-8")
    missing = [code for code, status in ERROR_STATUS.items() if f"`{code}` | {status} |" not in text]
    assert missing == [], f"docs/errors.md is missing API error codes: {missing}"
