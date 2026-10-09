"""`ezmd convert` (docs/spec/part4.md 4.2.2 item 1 and 4.2.3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import ezmd.library
from ezmd.cli import app
from ezmd.cli.convert import auto_profile

runner = CliRunner()
ELF = bytes([0x7F]) + b"ELF" + bytes([2, 1, 1, 0]) + bytes(8) + bytes([2, 0, 0x3E, 0]) + bytes(200)


def _txt(tmp_path: Path, name: str = "a.txt", text: str = "Hello\n=====\n\nWorld.\n") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def test_stdout_markdown_with_frontmatter(tmp_path: Path) -> None:
    res = runner.invoke(app, ["convert", str(_txt(tmp_path))])
    assert res.exit_code == 0, res.output
    assert res.stdout.startswith("---\n") and 'title: "Hello"' in res.stdout and "World." in res.stdout


def test_out_file_and_sidecar(tmp_path: Path) -> None:
    target = tmp_path / "o" / "x.md"
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--out", str(target)])
    assert res.exit_code == 0, res.output
    assert target.read_text(encoding="utf-8").startswith("---\n")
    side = json.loads((tmp_path / "o" / "x.ezmd.json").read_text(encoding="utf-8"))
    assert side["profile"] == "full"
    assert res.stdout == ""


def test_out_dir_uses_title_and_no_sidecar(tmp_path: Path) -> None:
    outdir = tmp_path / "outdir"
    outdir.mkdir()
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--out", str(outdir), "--no-sidecar"])
    assert res.exit_code == 0, res.output
    assert (outdir / "Hello.md").is_file()
    assert not list(outdir.glob("*.ezmd.json"))


@pytest.mark.parametrize(("fmt", "check"), [("txt", "World."), ("json", '"markdown"')])
def test_formats(tmp_path: Path, fmt: str, check: str) -> None:
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--format", fmt])
    assert res.exit_code == 0, res.output
    assert check in res.stdout
    if fmt == "json":
        assert "frontmatter" in json.loads(res.stdout)


@pytest.mark.parametrize("fmt", ["docx", "srt"])
def test_unbuilt_formats_exit_2(tmp_path: Path, fmt: str) -> None:
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--format", fmt, "--json"])
    assert res.exit_code == 2
    payload = json.loads(res.stdout)
    assert payload["status"] == "failed" and "not yet supported" in payload["error"]["message"]


def test_unknown_format_and_profile_exit_2(tmp_path: Path) -> None:
    assert runner.invoke(app, ["convert", str(_txt(tmp_path)), "--format", "pdf"]).exit_code == 2
    assert runner.invoke(app, ["convert", str(_txt(tmp_path)), "--profile", "tiny"]).exit_code == 2


def test_stdin(tmp_path: Path) -> None:
    res = runner.invoke(app, ["convert", "-", "--json"], input=b"Title\n=====\n\nfrom stdin\n")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload["source"] == "stdin" and "from stdin" in payload["markdown"]


def test_json_is_valid_on_failure_missing_file(tmp_path: Path) -> None:
    res = runner.invoke(app, ["convert", str(tmp_path / "nope.pdf"), "--json"])
    assert res.exit_code == 2
    payload = json.loads(res.stdout)
    assert payload["status"] == "failed" and payload["warnings"] and payload["exit_code"] == 2


def test_unsupported_type_exit_6_json(tmp_path: Path) -> None:
    p = tmp_path / "report.pdf"
    p.write_bytes(ELF)
    res = runner.invoke(app, ["convert", str(p), "--json"])
    assert res.exit_code == 6
    payload = json.loads(res.stdout)
    assert payload["status"] == "failed"
    assert payload["warnings"][0]["severity"] == "error"


def test_unconvertible_type_exit_6(tmp_path: Path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.7" + bytes([10]) + b"0" * 100)
    res = runner.invoke(app, ["convert", str(p), "--json"])
    assert res.exit_code in (1, 6)
    assert json.loads(res.stdout)["status"] == "failed"


def test_too_large_exit_5(tmp_path: Path) -> None:
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--opt", "max_bytes=5", "--json"])
    assert res.exit_code == 5, res.output
    assert json.loads(res.stdout)["error"]["code"] == "input_too_large"


def _capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    real = ezmd.library.convert

    def spy(source: Any, **kw: Any) -> Any:
        seen.update(kw)
        return real(source, **kw)

    monkeypatch.setattr(ezmd.library, "convert", spy)
    return seen


def test_lang_and_opts_reach_library_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch)
    res = runner.invoke(
        app, ["convert", str(_txt(tmp_path)), "--lang", "en,de", "--opt", "max_pages=3", "--opt", "ocr=false"]
    )
    assert res.exit_code == 0, res.output
    opts = seen["options"]
    assert opts.languages == ["en", "de"] and opts.max_pages == 3 and opts.ocr is False


def test_engine_maps_to_converter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture(monkeypatch)
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--engine", "text=plain"])
    assert res.exit_code == 0, res.output
    assert seen["options"].converter == "text.plain"


def test_engine_unknown_exit_2(tmp_path: Path) -> None:
    res = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--engine", "pdf=nothing-like-this"])
    assert res.exit_code == 2
    assert runner.invoke(app, ["convert", str(_txt(tmp_path)), "--engine", "novalue"]).exit_code == 2


def test_url_source_through_library_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    import ezmd.core.netguard as netguard

    class Fake:
        url = "https://example.com/page"
        body = b"Example\n=======\n\nDomain text.\n"
        content_type = "text/plain"

    monkeypatch.setattr(netguard, "fetch", lambda url, **kw: Fake())
    res = runner.invoke(app, ["convert", "https://example.com/page"])
    assert res.exit_code == 0, res.output
    assert res.stdout.startswith("---\n") and "Domain text." in res.stdout


def test_blocked_fetch_exit_4(monkeypatch: pytest.MonkeyPatch) -> None:
    import ezmd.core.netguard as netguard

    def blocked(url: str, **kw: object) -> object:
        raise netguard.ResidentialOnly("residential only", url=url)

    monkeypatch.setattr(netguard, "fetch", blocked)
    res = runner.invoke(app, ["convert", "https://video.example/watch", "--json"])
    assert res.exit_code == 4
    assert json.loads(res.stdout)["status"] == "failed"


def test_interrupt_exit_130(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **kw: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(ezmd.library, "convert", boom)
    assert runner.invoke(app, ["convert", str(_txt(tmp_path))]).exit_code == 130


def test_warnings_printed_to_stderr_after_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd.ir import Warning, WarningKind

    real = ezmd.library.convert

    def with_warning(source: Any, **kw: Any) -> Any:
        r = real(source, **kw)
        r.conversion.warnings.append(Warning(kind=WarningKind.ENCODING_UNCERTAIN, message="guessed latin-1"))
        r._cache.clear()
        return r

    monkeypatch.setattr(ezmd.library, "convert", with_warning)
    res = runner.invoke(app, ["convert", str(_txt(tmp_path))])
    assert res.exit_code == 0
    assert "WARN [encoding_uncertain] guessed latin-1" in res.stderr
    quiet = runner.invoke(app, ["convert", str(_txt(tmp_path)), "--quiet"])
    assert "WARN" not in quiet.stderr


def test_auto_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert auto_profile(None, False) == "compact"
    assert auto_profile(Path("x.md"), False) == "full"
    assert auto_profile(None, True) == "full"
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert auto_profile(None, False) == "full"


def test_resolve_engine_matches_underscore_parts_of_an_id() -> None:
    from ezmd.cli.options import resolve_engine

    rows: list[dict[str, object]] = [
        {"id": "documents.docling_pdf", "family": "documents"},
        {"id": "documents.pdfium_text", "family": "documents"},
        {"id": "text.plain", "family": "text"},
    ]
    assert resolve_engine("pdf=docling", rows) == "documents.docling_pdf"
    assert resolve_engine("pdf=pdfium", rows) == "documents.pdfium_text"
    assert resolve_engine("text=plain", rows) == "text.plain"
    with pytest.raises(ValueError, match="no converter matches"):
        resolve_engine("pdf=nothing", rows)


PDF = Path(__file__).resolve().parents[4] / "fixtures/pdf/born-digital-report/input.pdf"


@pytest.mark.parametrize(
    "args", [["--engine", "pdf=docling"], ["--converter", "documents.docling_pdf"]], ids=["engine", "converter"]
)
def test_docling_without_the_extra_names_the_extra(args: list[str]) -> None:
    import importlib.util

    if importlib.util.find_spec("docling") is not None:
        pytest.skip("docling is installed")
    res = runner.invoke(app, ["convert", str(PDF), *args])
    assert res.exit_code != 0
    assert "ezmd[docs]" in res.output and "Unknown converter" not in res.output, res.output
