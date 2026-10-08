"""CLI exit codes (part4 4.2.2; D-0017 item 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_factories import P, S
from typer.testing import CliRunner

import intomd.library
from intomd.cli import EXIT_PARTIAL, app
from intomd.inputs import InputRef
from intomd.ir import ConversionResult, Document, Metadata, Paragraph, SourceType, Warning, WarningKind

runner = CliRunner()


def _fake_convert(severity: str):  # type: ignore[no-untyped-def]
    def convert_ref(ref: InputRef, options: object = None, **_: object) -> ConversionResult:
        doc = Document(
            metadata=Metadata(source=ref.display, source_type=SourceType.TEXT),
            blocks=[Paragraph(spans=[S("usable text")], provenance=P())],
            warnings=[Warning(kind=WarningKind.RECONCILIATION_FAILED, severity=severity, message="x")],  # type: ignore[arg-type]
        ).finalize()
        return ConversionResult(document=doc, converter_id="text.plain", input_ref=ref.info())

    return convert_ref


def test_error_warning_on_usable_result_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(intomd.library, "convert_ref", _fake_convert("error"))
    res = runner.invoke(app, ["convert", str(src), "--json"])
    assert res.exit_code == EXIT_PARTIAL == 3
    payload = json.loads(res.stdout)
    assert payload["status"] == "partial" and "usable text" in payload["markdown"]


def test_warning_severity_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(intomd.library, "convert_ref", _fake_convert("warning"))
    res = runner.invoke(app, ["convert", str(src), "--quiet"])
    assert res.exit_code == 0 and "usable text" in res.stdout


def test_bad_option_exits_2() -> None:
    assert runner.invoke(app, ["convert", "x.txt", "--opt", "novalue"]).exit_code == 2
