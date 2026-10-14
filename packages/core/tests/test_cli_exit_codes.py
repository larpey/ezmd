"""CLI exit codes (part4 4.2.2; D-0017 item 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core_factories import P, S
from typer.testing import CliRunner

import ezmd.library
from ezmd.cli import EXIT_PARTIAL, app
from ezmd.inputs import InputRef
from ezmd.ir import ConversionResult, Document, Metadata, Paragraph, SourceType, Warning, WarningKind

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
    monkeypatch.setattr(ezmd.library, "convert_ref", _fake_convert("error"))
    res = runner.invoke(app, ["convert", str(src), "--json"])
    assert res.exit_code == EXIT_PARTIAL == 3
    payload = json.loads(res.stdout)
    assert payload["status"] == "partial" and "usable text" in payload["markdown"]


def test_warning_severity_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(ezmd.library, "convert_ref", _fake_convert("warning"))
    res = runner.invoke(app, ["convert", str(src), "--quiet"])
    assert res.exit_code == 0 and "usable text" in res.stdout


def test_bad_option_exits_2() -> None:
    assert runner.invoke(app, ["convert", "x.txt", "--opt", "novalue"]).exit_code == 2


# -- missing extras and unsupported types have one stable code each (D-0054) ---------------------------


def _json(res: object) -> dict[str, object]:
    return json.loads(res.stdout)  # type: ignore[attr-defined,no-any-return]


@pytest.mark.skipif(__import__("importlib").util.find_spec("pyarrow") is not None, reason="pyarrow is installed")
def test_missing_extra_for_an_unavailable_converter_exits_2(tmp_path: Path) -> None:
    src = tmp_path / "trips.parquet"
    src.write_bytes(b"PAR1" + b"\x00" * 64 + b"PAR1")
    res = runner.invoke(app, ["convert", str(src), "--json"])
    payload = _json(res)
    assert res.exit_code == 2, payload
    assert payload["exit_code"] == 2 and payload["warnings"][0]["kind"] == "extra_required"  # type: ignore[index]
    assert "ezmd[data]" in str(payload["warnings"])


def test_missing_extra_for_a_7z_archive_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd_converters.archives import sevenzip

    monkeypatch.setattr(sevenzip, "available", lambda: False)
    src = tmp_path / "bundle.7z"
    src.write_bytes(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 64)
    res = runner.invoke(app, ["convert", str(src), "--json"])
    payload = _json(res)
    assert res.exit_code == 2, payload
    assert payload["exit_code"] == 2 and "ezmd[7z]" in str(payload["markdown"])


def test_unsupported_type_has_a_stable_code(tmp_path: Path) -> None:
    from ezmd.cli.exitcodes import EXIT_UNSUPPORTED, classify
    from ezmd.registry import UNSUPPORTED_MEDIA_TYPE, ConversionError

    src = tmp_path / "blob.bin"
    src.write_bytes(bytes(range(256)) * 8)
    res = runner.invoke(app, ["convert", str(src), "--json"])
    payload = _json(res)
    assert res.exit_code == EXIT_UNSUPPORTED == 6, payload
    assert payload["error"]["code"] == "unsupported_media_type"  # type: ignore[index]
    reworded = ConversionError("x", user_message="Some other wording.", code=UNSUPPORTED_MEDIA_TYPE)
    assert classify(reworded).exit_code == 6  # classified by code, not by the message text


def test_extra_required_code_maps_to_exit_2() -> None:
    from ezmd.cli.exitcodes import EXIT_ARGS, classify
    from ezmd.registry import EXTRA_REQUIRED, ConversionError

    f = classify(ConversionError("x", user_message="Install it.", code=EXTRA_REQUIRED))
    assert (f.exit_code, f.code, f.warning_kind) == (EXIT_ARGS, "extra_required", "extra_required")


@pytest.mark.parametrize("url", ["ftp://example.com/report.pdf", "FTP://example.com/a", "s3://bucket/key.csv"])
def test_non_http_url_is_an_unsupported_scheme_not_a_missing_file(url: str) -> None:
    res = runner.invoke(app, ["convert", url, "--json"])
    payload = _json(res)
    assert res.exit_code == 2, payload
    message = str(payload["error"]["message"])  # type: ignore[index]
    assert "no such file" not in message and "http and https" in message and url.split(":")[0].lower() in message


def test_library_and_netguard_raise_scheme_not_allowed() -> None:
    from ezmd.core.netguard import SchemeNotAllowed, UrlBlocked, validate_url
    from ezmd.library import convert

    with pytest.raises(SchemeNotAllowed) as e:
        convert("ftp://example.com/a.pdf")
    assert isinstance(e.value, UrlBlocked) and str(e.value).startswith("scheme 'ftp'")
    with pytest.raises(SchemeNotAllowed):
        validate_url("gopher://example.com/")


def test_sandbox_unavailable_maps_to_exit_2() -> None:
    from ezmd.cli.exitcodes import EXIT_ARGS, classify
    from ezmd.registry import SANDBOX_UNAVAILABLE, ConversionError

    f = classify(ConversionError("x", user_message="Install bubblewrap.", code=SANDBOX_UNAVAILABLE))
    assert (f.exit_code, f.code) == (EXIT_ARGS, "sandbox_unavailable")
