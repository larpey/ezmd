from __future__ import annotations

import io
import zipfile
from collections.abc import Callable

import pytest

from intomd.ir import (
    CodeBlock,
    Comment,
    Document,
    Footnote,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Table,
    TrackedChange,
    WarningKind,
)
from intomd.registry import ConversionError
from intomd_converters.office._package import OfficePackage
from intomd_converters.office.docx import DocxConverter
from intomd_converters.office.omml import omml_to_latex

Run = Callable[..., Document]


def _zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data.encode("utf-8") if isinstance(data, str) else data)
    return buf.getvalue()


def test_tracked_changes_and_comments(run: Run, fixture_bytes: Callable[[str], bytes]) -> None:
    doc = run(DocxConverter(), fixture_bytes("docx-review"), "review.docx")
    inline = {
        sp.text.strip(): sp for b in doc.blocks if isinstance(b, Paragraph) for sp in b.spans if sp.change is not None
    }
    assert inline["annual"].change == "insert" and inline["annual"].change_author == "Alice Moreau"
    assert inline["quickly"].change == "delete" and inline["quickly"].change_author == "Bob Tanaka"
    assert inline["The board reviews it in June."].change == "insert"
    assert inline["Travel costs are reviewed quarterly."].change_id == "moveTo:8"
    para = next(b for b in doc.blocks if isinstance(b, Paragraph) and any(sp.text == "annual " for sp in b.spans))
    assert [sp.text for sp in para.spans][:3] == ["The committee approved the ", "annual ", "budget "]
    blocks = {"".join(s.text for s in c.spans).strip(): c for c in doc.blocks if isinstance(c, TrackedChange)}
    assert blocks["This paragraph was added during review."].attrs["scope"] == "paragraph"
    assert blocks["Travel costs are reviewed quarterly."].attrs == {"move": "from", "scope": "paragraph"}
    assert blocks["must not"].change == "format"
    ids = {b.id for b in doc.blocks}
    assert all(c.author and c.created and c.anchor_block_id in ids for c in blocks.values())

    comments = {c.author: c for c in doc.blocks if isinstance(c, Comment)}
    assert set(comments) == {"Carol Diaz", "Alice Moreau", "Bob Tanaka"}
    assert comments["Carol Diaz"].anchor_text == "budget" and comments["Carol Diaz"].resolved is False
    assert comments["Alice Moreau"].reply_to == comments["Carol Diaz"].id
    assert comments["Bob Tanaka"].resolved is True
    assert comments["Bob Tanaka"].anchor_text == "Hiring is paused until the audit closes."
    fn = next(b for b in doc.blocks if isinstance(b, Footnote))
    assert fn.id == "fn-1" and "board's 2025 policy" in fn.spans[0].text
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    assert len(lists) == 1 and [len(i.children) for i in lists[0].items] == [0, 2, 0]
    assert doc.metadata.title == "Quarterly Review Memo" and doc.metadata.author == "Alice Moreau"
    assert all(b.provenance.path for b in doc.blocks)


def test_track_changes_off_merges_insertions(run: Run, fixture_bytes: Callable[[str], bytes]) -> None:
    doc = run(DocxConverter(), fixture_bytes("docx-review"), "review.docx", tracked_changes=False, comments=False)
    assert not any(isinstance(b, TrackedChange | Comment) for b in doc.blocks)
    text = doc.plain_text()
    assert "approved the annual budget after" in text and "quickly" not in text


def test_structure(run: Run, fixture_bytes: Callable[[str], bytes]) -> None:
    doc = run(DocxConverter(), fixture_bytes("docx-structure"), "structure.docx")
    heads = [(b.level, b.spans[0].text) for b in doc.blocks if isinstance(b, Heading)]
    assert heads == [
        (1, "Field Guide to Ponds"),
        (1, "Introduction"),
        (1, "Habitats"),
        (2, "Plants"),
        (3, "Survey method"),
        (4, "Appendix"),
    ]
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    assert not lists[0].ordered and lists[0].items[0].children_ordered
    assert lists[0].items[1].children[0].children[0].spans[0].text == "Fragrant water lily"
    assert lists[1].ordered and len(lists[1].items) == 3
    table = next(b for b in doc.blocks if isinstance(b, Table))
    assert table.header_rows == 1 and table.has_merged_cells
    spans = {(c.row, c.col): (c.row_span, c.col_span) for c in table.cells}
    assert spans[(1, 0)] == (2, 1) and spans[(3, 0)] == (1, 2) and (2, 0) not in spans
    assert table.caption and table.caption[0].text == "Reed counts by zone"
    assert any(isinstance(b, Quote) for b in doc.blocks)
    code = next(b for b in doc.blocks if isinstance(b, CodeBlock))
    assert code.code == "count = sum(zone_counts)\nprint(count)"
    math = [s for b in doc.blocks if isinstance(b, Paragraph) for s in b.spans if s.math]
    assert math and math[0].math == r"\frac{a}{b}+{x}^{2}"
    text = doc.plain_text()
    assert "IGNORE PREVIOUS" not in text and "white words" not in text
    assert "Never sample alone after dark." in text
    kinds = {w.kind: w for w in doc.warnings}
    assert kinds[WarningKind.REMOVED_HIDDEN_ELEMENTS].count == 2
    assert WarningKind.TEXTBOX_CONTENT_RELOCATED in kinds
    assert WarningKind.HEADING_INFERRED_FROM_FORMATTING in kinds
    notes = {b.id: b.marker for b in doc.blocks if isinstance(b, Footnote)}
    assert notes == {"fn-1": "1", "en-1": "i"}
    link = next(s for b in doc.blocks if isinstance(b, Paragraph) for s in b.spans if s.href)
    assert link.href == "https://example.org/ponds"


def test_keep_hidden_records_text(run: Run, fixture_bytes: Callable[[str], bytes]) -> None:
    doc = run(DocxConverter(), fixture_bytes("docx-structure"), "s.docx", keep_hidden=True, infer_headings=False)
    assert "IGNORE PREVIOUS INSTRUCTIONS" in str(doc.metadata.extra["hidden_text"])
    assert not any(w.kind == WarningKind.HEADING_INFERRED_FROM_FORMATTING for w in doc.warnings)


def test_macro_and_external_relationships_removed(run: Run, fixture_bytes: Callable[[str], bytes]) -> None:
    doc = run(DocxConverter(), fixture_bytes("docx-macro"), "m.docm")
    w = next(w for w in doc.warnings if w.kind == WarningKind.REMOVED_SCRIPT_OR_MACRO)
    assert w.detail["macros"] == 1 and w.detail["external_relationships"] == 2
    hrefs = [s.href for b in doc.blocks if isinstance(b, Paragraph) for s in b.spans if s.href]
    assert hrefs == ["https://intranet.example.com/forms"]
    pkg = OfficePackage(fixture_bytes("docx-macro"))
    clean = zipfile.ZipFile(io.BytesIO(pkg.sanitized_bytes()))
    names = clean.namelist()
    assert "word/vbaProject.bin" not in names
    assert b"vbaProject" not in clean.read("word/_rels/document.xml.rels")
    assert b"attachedTemplate" not in clean.read("word/_rels/settings.xml.rels")
    assert b"/word/vbaProject.bin" not in clean.read("[Content_Types].xml")


def test_zip_limits() -> None:
    with pytest.raises(ConversionError, match="not a zip"):
        OfficePackage(b"plain text")
    with pytest.raises(ConversionError, match="OLE2"):
        OfficePackage(bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]) + b"x" * 100)
    bomb = _zip({"word/document.xml": b"\x20" * (5 * 1024 * 1024)})
    with pytest.raises(ConversionError, match="compression ratio"):
        OfficePackage(bomb)
    many = _zip({f"f{i}.xml": b"x" for i in range(10_001)})
    with pytest.raises(ConversionError, match="entries"):
        OfficePackage(many)


def test_total_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTOMD_ARCHIVE_MAX_BYTES", "100")
    with pytest.raises(ConversionError, match="uncompressed size"):
        OfficePackage(_zip({"a.xml": b"y" * 200}))


def test_doctype_refused(run: Run) -> None:
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><w:document xmlns:w="w">&a;</w:document>'
    data = _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": evil})
    with pytest.raises(ConversionError, match="DOCTYPE"):
        run(DocxConverter(), data, "x.docx")
    with pytest.raises(ConversionError, match="DOCTYPE"):
        OfficePackage(data).sanitized_bytes()


def test_missing_body_and_parts(run: Run) -> None:
    with pytest.raises(ConversionError, match="missing"):
        run(DocxConverter(), _zip({"a.txt": "x"}), "x.docx")
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    data = _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": f"<w:document {ns}/>"})
    with pytest.raises(ConversionError, match="no w:body"):
        run(DocxConverter(), data, "x.docx")
    empty = _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": f"<w:document {ns}><w:body/></w:document>"})
    doc = run(DocxConverter(), empty, "x.docx")
    assert doc.blocks == [] and doc.warnings[-1].kind == WarningKind.EXTRACTION_EMPTY


def test_size_cap(run: Run, monkeypatch: pytest.MonkeyPatch, fixture_bytes: Callable[[str], bytes]) -> None:
    from intomd.context import Limits

    monkeypatch.setattr(DocxConverter, "limits", Limits(max_bytes=10))
    with pytest.raises(ConversionError, match="exceeds"):
        run(DocxConverter(), fixture_bytes("docx-review"), "r.docx")


def test_omml_subset() -> None:
    from lxml import etree

    m = "http://schemas.openxmlformats.org/officeDocument/2006/math"

    def conv(inner: str) -> tuple[str, bool]:
        el = etree.fromstring(f'<m:oMath xmlns:m="{m}">{inner}</m:oMath>')
        r = omml_to_latex(el)
        return r.latex, r.partial

    def r(t: str) -> str:
        return f"<m:r><m:t>{t}</m:t></m:r>"

    assert conv(f"<m:rad><m:deg/><m:e>{r('x')}</m:e></m:rad>") == (r"\sqrt{x}", False)
    assert conv(f"<m:rad><m:deg>{r('3')}</m:deg><m:e>{r('y')}</m:e></m:rad>")[0] == r"\sqrt[3]{y}"
    nary = (
        f'<m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr><m:sub>{r("i=1")}</m:sub>'
        f"<m:sup>{r('n')}</m:sup><m:e>{r('i')}</m:e></m:nary>"
    )
    assert conv(nary)[0] == r"\sum_{i=1}^{n} i"
    assert conv(f"<m:d><m:e>{r('a')}</m:e><m:e>{r('b')}</m:e></m:d>")[0] == r"\left(a,b\right)"
    row1 = f"<m:mr><m:e>{r('1')}</m:e><m:e>{r('0')}</m:e></m:mr>"
    row2 = f"<m:mr><m:e>{r('0')}</m:e><m:e>{r('1')}</m:e></m:mr>"
    mat = f"<m:m>{row1}{row2}</m:m>"
    assert conv(mat)[0] == r"\begin{matrix}1 & 0 \\ 0 & 1\end{matrix}"
    assert conv(f"<m:func><m:fName>{r('sin')}</m:fName><m:e>{r('θ')}</m:e></m:func>")[0] == r"\sin \theta"
    assert (
        conv(f"<m:sSubSup><m:e>{r('x')}</m:e><m:sub>{r('i')}</m:sub><m:sup>{r('2')}</m:sup></m:sSubSup>")[0]
        == "{x}_{i}^{2}"
    )
    assert conv(f"<m:bar><m:e>{r('z')}</m:e></m:bar>")[0] == r"\overline{z}"
    assert conv(f"<m:groupChr><m:e>{r('q')}</m:e></m:groupChr>") == ("q", True)
