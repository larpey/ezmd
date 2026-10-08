from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import (
    Comment,
    Document,
    Footnote,
    Heading,
    ListBlock,
    Paragraph,
    Slide,
    SourceType,
    Table,
    TrackedChange,
    WarningKind,
)
from ezmd.registry import ConversionError, ConverterRegistry, ConvertOptions
from ezmd_converters import office
from ezmd_converters.office import iwork, libreoffice
from ezmd_converters.office.libreoffice import LibreOfficeConverter, find_soffice
from ezmd_converters.office.odf import OdfConverter
from ezmd_converters.office.rtf import RtfConverter

Run = Callable[..., Document]
BS = chr(92)


def _zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data.encode("utf-8") if isinstance(data, str) else data)
    return buf.getvalue()


NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink"'
)


def _odf(body: str, styles: str = "", mime: str = "application/vnd.oasis.opendocument.spreadsheet") -> bytes:
    content = (
        f"<office:document-content {NS}><office:automatic-styles>{styles}</office:automatic-styles>"
        f"<office:body>{body}</office:body></office:document-content>"
    )
    return _zip({"mimetype": mime, "content.xml": content, "Basic/Standard/Module1.xml": "<macro/>"})


def test_odt_fixture(run: Run, fixture_bytes: Callable[[str], bytes]) -> None:
    doc = run(OdfConverter(), fixture_bytes("odt-basic"), "n.odt")
    heads = [(b.level, b.spans[0].text) for b in doc.blocks if isinstance(b, Heading)]
    assert heads == [(1, "Garden Pond Notes"), (2, "Building steps"), (2, "Plants to add")]
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    assert lists[0].ordered and not lists[1].ordered and len(lists[1].items[0].children) == 2
    table = next(b for b in doc.blocks if isinstance(b, Table))
    assert table.n_rows == 3 and table.header_rows == 1
    para = next(b for b in doc.blocks if isinstance(b, Paragraph) and any(sp.change for sp in b.spans))
    changed = {sp.change: sp for sp in para.spans if sp.change}
    assert changed["delete"].change_author == "Eli Grant" and changed["delete"].text.strip() == "cheap"
    assert changed["insert"].change_author == "Dana Fox" and changed["insert"].change_id == "ct1"
    comment = next(b for b in doc.blocks if isinstance(b, Comment))
    assert comment.author == "Dana Fox" and comment.anchor_block_id == para.id
    assert not any(isinstance(b, TrackedChange) for b in doc.blocks)
    assert any(isinstance(b, Footnote) for b in doc.blocks)
    assert doc.metadata.title == "Garden Pond Notes"


def test_ods_sheets_hidden_and_macros(run: Run) -> None:
    styles = (
        '<style:style style:name="ta2" style:family="table"><style:table-properties table:display="false"/>'
        "</style:style>"
    )
    row = (
        '<table:table-row><table:table-cell office:value-type="string"><text:p>Item</text:p></table:table-cell>'
        '<table:table-cell office:value-type="string"><text:p>Share</text:p></table:table-cell></table:table-row>'
        '<table:table-row><table:table-cell office:value-type="string"><text:p>Liner</text:p></table:table-cell>'
        '<table:table-cell office:value-type="percentage" office:value="0.25"><text:p>25.0%</text:p></table:table-cell>'
        '<table:table-cell table:formula="of:=[.B2]*2" office:value-type="float" office:value="0.5">'
        "<text:p>0.5</text:p></table:table-cell></table:table-row>"
        '<table:table-row table:number-rows-repeated="1000000"><table:table-cell table:number-columns-repeated="1024"/>'
        "</table:table-row>"
    )
    body = (
        f'<office:spreadsheet><table:table table:name="Costs">{row}</table:table>'
        f'<table:table table:name="Secret" table:style-name="ta2">{row}</table:table></office:spreadsheet>'
    )
    doc = run(OdfConverter(), _odf(body, styles), "s.ods")
    heads = [b for b in doc.blocks if isinstance(b, Heading)]
    assert [h.spans[0].text for h in heads] == ["Costs", "Secret"] and heads[1].attrs["hidden"] == "true"
    assert doc.metadata.sheets == ["Costs", "Secret"]
    table = next(b for b in doc.blocks if isinstance(b, Table))
    cells = {(c.row, c.col): c for c in table.cells}
    assert cells[(1, 1)].spans[0].text == "25.0%" and cells[(1, 2)].formula == "=[.B2]*2"
    assert table.header_rows == 1 and table.n_rows == 2
    kinds = {w.kind for w in doc.warnings}
    assert {WarningKind.HIDDEN_SHEETS_INCLUDED, WarningKind.REMOVED_SCRIPT_OR_MACRO} <= kinds


def test_odp_slides(run: Run) -> None:
    body = (
        '<office:presentation><draw:page draw:name="p1">'
        '<draw:frame presentation:class="title" svg:y="1cm"><draw:text-box><text:p>Welcome</text:p>'
        "</draw:text-box></draw:frame>"
        '<draw:frame presentation:class="outline" svg:y="5cm"><draw:text-box><text:list><text:list-item>'
        "<text:p>First point</text:p></text:list-item></text:list></draw:text-box></draw:frame>"
        '<presentation:notes><draw:frame presentation:class="notes"><draw:text-box><text:p>Say hello.</text:p>'
        "</draw:text-box></draw:frame></presentation:notes></draw:page></office:presentation>"
    )
    doc = run(OdfConverter(), _odf(body, mime="application/vnd.oasis.opendocument.presentation"), "d.odp")
    slide = next(b for b in doc.blocks if isinstance(b, Slide))
    assert slide.title == "Welcome" and doc.metadata.slides == 1
    lst = next(b for b in doc.blocks if isinstance(b, ListBlock))
    notes = next(b for b in doc.blocks if isinstance(b, Paragraph) and b.attrs.get("slide_part") == "notes")
    assert lst.parent_id == slide.id and notes.parent_id == slide.id and notes.spans[0].text == "Say hello."


def test_odf_without_content(run: Run) -> None:
    with pytest.raises(ConversionError, match=r"content\.xml"):
        run(OdfConverter(), _zip({"mimetype": "x"}), "x.odt")


def test_rtf(run: Run, fixture_bytes: Callable[[str], bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_DISABLE_LIBREOFFICE", "1")
    doc = run(RtfConverter(), fixture_bytes("rtf-simple"), "r.rtf")
    assert isinstance(doc.blocks[0], Heading) and doc.metadata.title == "Pond Visit Report"
    assert doc.metadata.author == "Field Team"
    assert "café" in doc.plain_text()
    assert any(w.kind == WarningKind.LIBREOFFICE_MISSING for w in doc.warnings)
    with pytest.raises(ConversionError, match="RTF header"):
        run(RtfConverter(), b"hello", "r.rtf")
    pict = ("{" + BS + "rtf1 Text {" + BS + "pict 0102} more {" + BS + "object x}" + BS + "par}").encode()
    w = {x.kind for x in run(RtfConverter(), pict, "p.rtf").warnings}
    assert {WarningKind.IMAGE_SKIPPED, WarningKind.OLE_OBJECT_SKIPPED} <= w


def test_libreoffice_missing_and_native(
    run: Run, fixture_bytes: Callable[[str], bytes], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EZMD_DISABLE_LIBREOFFICE", "1")
    assert find_soffice() is None
    doc = run(LibreOfficeConverter(), b"\xd0\xcf\x11\xe0legacy", "old.doc")
    assert doc.blocks == [] and doc.warnings[0].kind == WarningKind.LIBREOFFICE_MISSING
    monkeypatch.delenv("EZMD_DISABLE_LIBREOFFICE")
    fake = tmp_path / "soffice"
    fake.write_text("x")
    monkeypatch.setenv("LIBREOFFICE_PATH", str(fake))
    assert find_soffice() == str(fake)
    seen: dict[str, object] = {}

    def fake_run(soffice: str, ref: InputRef, target: str, timeout: int) -> bytes:
        seen.update(soffice=soffice, target=target, timeout=timeout)
        return fixture_bytes("docx-review")

    monkeypatch.setattr(libreoffice, "_run", fake_run)
    out = run(LibreOfficeConverter(), b"{" + BS.encode() + b"rtf1 x}", "memo.rtf")
    assert seen["target"] == "docx" and out.metadata.source_type == SourceType.RTF
    assert out.metadata.extra["converted_with"] == "libreoffice"
    assert any(isinstance(b, TrackedChange) for b in out.blocks)


def test_libreoffice_run_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd.core import sandbox

    captured: dict[str, object] = {}

    def fake(argv: list[str], **kw: object) -> sandbox.SandboxResult:
        captured["argv"] = argv
        captured["env"] = kw.get("env")
        outdir = Path(argv[argv.index("--outdir") + 1])
        (outdir / "input.docx").write_bytes(b"PK")
        xcu = Path(argv[6].split("=", 1)[1].replace("file:///", "").replace("file://", "")) / "user"
        captured["xcu"] = (xcu / "registrymodifications.xcu").exists() or True
        return sandbox.SandboxResult(argv, 0, b"", b"", False, False, 0.1)

    monkeypatch.setattr(sandbox, "run", fake)
    ref = InputRef.from_bytes(b"data", filename="a.doc")
    assert libreoffice._run("soffice", ref, "docx", 5) == b"PK"
    argv = captured["argv"]
    assert isinstance(argv, list) and "--headless" in argv and argv[argv.index("--convert-to") + 1] == "docx"
    assert any(a.startswith("-env:UserInstallation=file:") for a in argv)

    def failing(argv: list[str], **kw: object) -> sandbox.SandboxResult:
        return sandbox.SandboxResult(argv, 1, b"", b"", False, False, 0.1)

    monkeypatch.setattr(sandbox, "run", failing)
    with pytest.raises(ConversionError, match="exited"):
        libreoffice._run("soffice", ref, "docx", 5)


def test_iwork_unavailable() -> None:
    u = iwork.unavailable()
    assert u.id == "documents.iwork" and u.requires_extras == ("iwork",) and u.can_handle(None) == 0.0  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("docx-review", "documents.docx"),
        ("docx-macro", "documents.docx"),
        ("pptx-lecture", "documents.pptx"),
        ("xlsx-multi-sheet", "documents.xlsx"),
        ("odt-basic", "documents.odf"),
        ("rtf-simple", "documents.rtf"),
    ],
)
def test_registry_resolution(
    name: str, expected: str, fixture_bytes: Callable[[str], bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EZMD_DISABLE_LIBREOFFICE", "1")
    reg = ConverterRegistry()
    for c in office.converters():
        reg.register(c)
    for mime, ids in office.CHAINS.items():
        reg.set_chain(mime, ids)
    ext = {"docx-macro": ".docm", "pptx-lecture": ".pptx", "xlsx-multi-sheet": ".xlsx", "odt-basic": ".odt",
           "rtf-simple": ".rtf"}.get(name, ".docx")  # fmt: skip
    ref = InputRef.from_bytes(fixture_bytes(name), filename=f"input{ext}")
    detect(ref)
    cands = reg.candidates(ref, ConvertOptions())
    assert cands and cands[0][1].id == expected, (ref.detected, [c.id for _, c in cands])


def test_rtf_chain_falls_back_without_libreoffice(
    fixture_bytes: Callable[[str], bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EZMD_DISABLE_LIBREOFFICE", "1")
    reg = ConverterRegistry()
    for c in office.converters():
        reg.register(c)
    for mime, ids in office.CHAINS.items():
        reg.set_chain(mime, ids)
    ref = InputRef.from_bytes(fixture_bytes("rtf-simple"), filename="input.rtf")
    detect(ref)
    result = reg.convert(ref, ConvertOptions())
    assert result.converter_id == "documents.rtf"
    kinds = {w.kind for w in result.all_warnings}
    assert WarningKind.LIBREOFFICE_MISSING in kinds
    assert reg.registrations()[
        [r.converter.id for r in reg.registrations()].index("documents.libreoffice")
    ].import_error


def test_libreoffice_available_when_soffice_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "soffice"
    fake.write_text("x")
    monkeypatch.delenv("EZMD_DISABLE_LIBREOFFICE", raising=False)
    monkeypatch.setenv("LIBREOFFICE_PATH", str(fake))
    conv = next(c for c in office.converters() if c.id == "documents.libreoffice")
    assert isinstance(conv, LibreOfficeConverter)
    ref = InputRef.from_bytes(bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]) + bytes(1024), filename="a.ppt")
    detect(ref)
    assert conv.can_handle(ref) > 0


def test_family_listing() -> None:
    ids = {c.id for c in office.converters()}
    assert {"documents.docx", "documents.pptx", "documents.xlsx", "documents.odf", "documents.rtf",
            "documents.libreoffice", "documents.iwork"} <= ids  # fmt: skip
    assert all(c.family == "documents" for c in office.converters())
