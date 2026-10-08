"""tools/check_fixture_provenance.py: the real corpus passes, and each rule rejects what it should."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.org/doc.html"
OWN = '[provenance]\norigin = "self-generated"\nlicense = "CC0-1.0"\nsource = '


def _load() -> ModuleType:
    path = ROOT / "tools" / "check_fixture_provenance.py"
    spec = importlib.util.spec_from_file_location("check_fixture_provenance", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cfp = _load()


def _fixture(root: Path, name: str, provenance: str) -> None:
    d = root / "fixtures" / "fam" / name
    d.mkdir(parents=True)
    (d / "input.txt").write_text("x", encoding="utf-8")
    (d / "meta.toml").write_text(f'converter = "text.plain"\n\n{provenance}\n', encoding="utf-8")


def _credit(fx: str, *, license_: str = "CC-BY-4.0", url: str = URL, retrieved: str = "2026-10-08") -> str:
    return (
        f"### fixtures/fam/{fx}\n- Title: A doc\n- Author: Someone\n- License: {license_}\n"
        f"- URL: {url}\n- Retrieved: {retrieved}\n"
    )


def _cc_by(source: str = URL) -> str:
    return f'[provenance]\norigin = "cc-by"\nlicense = "CC-BY-4.0"\nsource = "{source}"'


def test_repository_corpus_passes() -> None:
    assert cfp.check(ROOT) == []


def test_self_generated_with_existing_script_passes(tmp_path: Path) -> None:
    (tmp_path / "fixtures" / "fam").mkdir(parents=True)
    (tmp_path / "fixtures" / "fam" / "_generate.py").write_text("", encoding="utf-8")
    _fixture(
        tmp_path,
        "a",
        OWN + '"fixtures/fam/_generate.py"',
    )
    _fixture(
        tmp_path,
        "b",
        OWN + '"hand-written for this repository (CC0)"',
    )
    assert cfp.check(tmp_path) == []


@pytest.mark.parametrize(
    ("provenance", "needle"),
    [
        ("", "no [provenance]"),
        ('[provenance]\norigin = "scraped"\nlicense = "CC0-1.0"\nsource = "x"', "origin"),
        ('[provenance]\norigin = "self-generated"\nlicense = "MIT"\nsource = "hand-written"', "not allowed"),
        ('[provenance]\norigin = "cc-by"\nlicense = "CC-BY-NC-4.0"\nsource = "' + URL + '"', "not allowed"),
        (OWN + '""', "source is empty"),
        (OWN + '"fixtures/nope.py"', "existing"),
        (_cc_by("http://example.org/x"), "https URL"),
        (OWN + '"fixtures/fam"', "existing file"),
        (OWN + '"/etc/hosts"', "existing file"),
        (
            OWN + '"C:/Windows/win.ini"',
            "existing file",
        ),
        (
            OWN + '"fixtures/../fixtures/fam/a/input.txt"',
            "existing file",
        ),
        (OWN + '"hand-written by me"', "exactly"),
    ],
)
def test_invalid_provenance_is_rejected(tmp_path: Path, provenance: str, needle: str) -> None:
    _fixture(tmp_path, "a", provenance)
    errors = cfp.check(tmp_path)
    assert any(needle in e for e in errors), errors


def test_third_party_fixture_needs_credit(tmp_path: Path) -> None:
    _fixture(tmp_path, "a", _cc_by())
    assert any("needs a CREDITS.md entry" in e for e in cfp.check(tmp_path))
    (tmp_path / "CREDITS.md").write_text("# Credits\n\n" + _credit("a"), encoding="utf-8")
    assert cfp.check(tmp_path) == []


@pytest.mark.parametrize(
    ("credit", "needle"),
    [
        (_credit("a", license_="CC-BY-3.0"), "License"),
        (_credit("a", url="https://example.org/other"), "URL does not match"),
        (_credit("a", retrieved="last week"), "ISO date"),
        ("### fixtures/fam/a\n- Title: A doc\n- License: CC-BY-4.0\n- URL: " + URL + "\n", "lacks '- Author:'"),
        (_credit("a") + _credit("a"), "duplicate"),
        (_credit("a") + _credit("gone"), "stale"),
    ],
)
def test_bad_credit_entries_are_rejected(tmp_path: Path, credit: str, needle: str) -> None:
    _fixture(tmp_path, "a", _cc_by())
    (tmp_path / "CREDITS.md").write_text(credit, encoding="utf-8")
    errors = cfp.check(tmp_path)
    assert any(needle in e for e in errors), errors


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fixture(tmp_path, "a", _cc_by())
    assert cfp.main(["prog", str(tmp_path)]) == 1
    (tmp_path / "CREDITS.md").write_text(_credit("a"), encoding="utf-8")
    assert cfp.main(["prog", str(tmp_path)]) == 0
    assert "1 fixtures, 0 problem(s)" in capsys.readouterr().out
