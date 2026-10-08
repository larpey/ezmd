"""docs/converters/README.md and the mkdocs.yml converters nav match the registry (gen_converters_matrix.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
STALE = "run `uv run python tools/gen_converters_matrix.py`"


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_converters_matrix", ROOT / "tools" / "gen_converters_matrix.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _no_family_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTOMD_ENABLE_SOCIAL", raising=False)


def test_matrix_is_current(gen: ModuleType) -> None:
    committed = (ROOT / "docs" / "converters" / "README.md").read_text(encoding="utf-8")
    assert committed == gen.render(), f"docs/converters/README.md is stale; {STALE}"


def test_mkdocs_nav_is_current(gen: ModuleType) -> None:
    committed = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert committed == gen.update_mkdocs(committed), f"mkdocs.yml converters nav is stale; {STALE}"


def test_matrix_lists_every_builtin_converter(gen: ModuleType) -> None:
    from intomd_converters import builtin_converters

    text = gen.render()
    ids = {c.id for c in builtin_converters()}
    assert ids, "no built-in converters"
    missing = sorted(i for i in ids if f"| `{i}` |" not in text)
    assert missing == [], f"converters missing from the matrix: {missing}"


def test_every_family_page_is_in_the_nav(gen: ModuleType) -> None:
    nav = gen.render_nav()
    pages = [p.name for p in (ROOT / "docs" / "converters").glob("*.md") if p.name != "README.md"]
    assert pages
    for name in pages:
        assert f"converters/{name}" in nav


def test_install_column_never_names_an_undefined_extra(gen: ModuleType) -> None:
    extras = gen.defined_extras()
    for row in gen.rows():
        if row.install.startswith("extra"):
            named = [part.split("`")[1] for part in row.install.split(", ")]
            assert set(named) <= extras, row
        if row.install == "planned":
            assert row.status == "Planned"


def test_update_mkdocs_requires_markers(gen: ModuleType) -> None:
    with pytest.raises(SystemExit):
        gen.update_mkdocs("nav:\n  - Home: index.md\n")
