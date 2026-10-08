from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pikepdf
import pytest
from conftest import FIXTURES, convert_path, new_pdf, save
from pikepdf import Array, Dictionary, Name, String

from ezmd.ir import PageBreak, Paragraph, Table, WarningKind, spans_text
from ezmd.registry import ConversionError
from ezmd_converters.pdf.sanitize import EncryptedNoPassword, sanitize


def _kinds(doc: object) -> list[str]:
    return [str(w.kind) for w in doc.warnings]  # type: ignore[attr-defined]


def test_sanitize_strips_active_content_and_attachments() -> None:
    san = sanitize(FIXTURES / "javascript-attachment" / "input.pdf", passwords=[""], max_pages=10, source="x.pdf")
    try:
        kinds = [w.kind for w in san.warnings]
        assert WarningKind.ATTACHMENT_SKIPPED in kinds
        skipped = next(w for w in san.warnings if w.kind == WarningKind.ATTACHMENT_SKIPPED)
        assert skipped.detail["name"] == "bookings.csv"
        removed = next(w for w in san.warnings if w.kind == WarningKind.REMOVED_SCRIPT_OR_MACRO)
        assert removed.detail == {"AA": 1, "JavaScript": 2, "OpenAction": 1}
        with pikepdf.open(san.path) as pdf:
            assert "/OpenAction" not in pdf.Root
            assert "/Names" not in pdf.Root or "/JavaScript" not in pdf.Root.Names
            assert "/Names" not in pdf.Root or "/EmbeddedFiles" not in pdf.Root.Names
            page = pdf.pages[0].obj
            assert "/AA" not in page
            for annot in page.get("/Annots", Array()):
                assert "/A" not in annot
            assert not pdf.is_encrypted
    finally:
        san.cleanup()
    assert not san.path.exists()


def test_javascript_fixture_converts_text(tmp_path: Path) -> None:
    doc = convert_path(FIXTURES / "javascript-attachment" / "input.pdf")
    text = doc.plain_text()
    assert "booking calendar" in text and "validate your booking" in text
    assert {"attachment_skipped", "removed_script_or_macro"} <= set(_kinds(doc))


def test_encrypted_without_password_is_stub() -> None:
    doc = convert_path(FIXTURES / "encrypted-user-password" / "input.pdf")
    assert [type(b) for b in doc.blocks] == [Paragraph]
    assert spans_text(doc.blocks[0].spans) == "Encrypted PDF; no valid password supplied"  # type: ignore[union-attr]
    assert _kinds(doc) == ["encrypted_no_password"]
    assert doc.warnings[0].severity == "error"


def test_encrypted_with_password_option() -> None:
    doc = convert_path(FIXTURES / "encrypted-user-password" / "input.pdf", {"pdf.password": "fixture"})
    assert "restricted to board members" in doc.plain_text()
    assert "encrypted_no_password" not in _kinds(doc)


def test_password_file_and_cap(tmp_path: Path) -> None:
    pw = tmp_path / "pw.txt"
    pw.write_text("\n".join([f"wrong{i}" for i in range(60)] + ["fixture"]), encoding="utf-8")
    doc = convert_path(FIXTURES / "encrypted-user-password" / "input.pdf", {"pdf.password_file": str(pw)})
    assert "encrypted_no_password" in _kinds(doc), "more than 50 candidates must never be tried"
    pw.write_text("wrong\nfixture\n", encoding="utf-8")
    doc = convert_path(FIXTURES / "encrypted-user-password" / "input.pdf", {"pdf.password_file": str(pw)})
    assert "board members" in doc.plain_text()


def test_sanitize_raises_for_locked() -> None:
    with pytest.raises(EncryptedNoPassword):
        sanitize(FIXTURES / "encrypted-user-password" / "input.pdf", passwords=["", "nope"], max_pages=5, source="x")


def test_owner_password_only_is_converted_with_info(tmp_path: Path) -> None:
    pdf = new_pdf([[(72, 700, "Copy restricted but readable text.", 10, False)]])
    path = save(
        pdf,
        tmp_path / "owner.pdf",
        encryption=pikepdf.Encryption(owner="owner", user="", allow=pikepdf.Permissions(extract=False)),
    )
    doc = convert_path(path)
    assert "Copy restricted" in doc.plain_text()
    assert "copy_restricted_ignored" in _kinds(doc)


def test_page_cap_truncates(make_pdf: Callable[..., Path]) -> None:
    path = make_pdf([[(72, 700, f"Body text on page {i} of the capped document.", 10, False)] for i in range(5)])
    doc = convert_path(path, {"pdf.max_pages": 2})
    assert doc.truncated
    assert [b.page_number for b in doc.blocks if isinstance(b, PageBreak)] == [1, 2]
    cap = next(w for w in doc.warnings if w.kind == WarningKind.PAGE_CAP_REACHED)
    assert cap.detail == {"pages_total": 5, "pages_converted": 2}
    assert doc.metadata.pages == 5
    doc2 = convert_path(path, max_pages=3)
    assert len([b for b in doc2.blocks if isinstance(b, PageBreak)]) == 3


def test_xfa_removed_and_acroform_table(tmp_path: Path) -> None:
    pdf = new_pdf([[(72, 700, "Application form for a berth permit.", 10, False)]])
    page = pdf.pages[0].obj
    name_field = pdf.make_indirect(
        Dictionary(
            FT=Name.Tx,
            T=String("applicant"),
            V=String("Ada Harbor"),
            Rect=Array([72, 600, 300, 620]),
            P=page,
            Subtype=Name.Widget,
            Type=Name.Annot,
        )
    )
    box = pdf.make_indirect(
        Dictionary(
            FT=Name.Btn,
            T=String("agree"),
            V=Name("/Yes"),
            Rect=Array([72, 560, 90, 578]),
            P=page,
            Subtype=Name.Widget,
            Type=Name.Annot,
        )
    )
    sig = pdf.make_indirect(
        Dictionary(
            FT=Name.Sig,
            T=String("signature"),
            Rect=Array([72, 500, 300, 540]),
            P=page,
            Subtype=Name.Widget,
            Type=Name.Annot,
        )
    )
    page.Annots = Array([name_field, box, sig])
    pdf.Root.AcroForm = Dictionary(
        Fields=Array([name_field, box, sig]), XFA=pdf.make_indirect(pikepdf.Stream(pdf, b"<xdp/>"))
    )
    doc = convert_path(save(pdf, tmp_path / "form.pdf"))
    assert "unsupported_feature" in _kinds(doc)
    table = next(b for b in doc.blocks if isinstance(b, Table) and b.attrs.get("pdf_table") == "acroform")
    rows = [[spans_text(c.spans) for c in table.cells if c.row == r] for r in range(table.n_rows)]
    assert rows == [
        ["Field", "Type", "Value", "Page"],
        ["applicant", "text", "Ada Harbor", "1"],
        ["agree", "checkbox", "[x]", "1"],
        ["signature", "signature", "(unsigned)", "1"],
    ]
    doc_off = convert_path(save(pdf, tmp_path / "form2.pdf"), {"pdf.forms": "off"})
    assert not any(isinstance(b, Table) for b in doc_off.blocks)


def test_garbage_is_conversion_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7\n" + b"garbage " * 50)
    with pytest.raises(ConversionError):
        convert_path(bad)


def test_bad_option_value_fails_fast() -> None:
    with pytest.raises(ConversionError, match=r"pdf\.ocr"):
        convert_path(FIXTURES / "simple-table" / "input.pdf", {"pdf.ocr": "sometimes"})
