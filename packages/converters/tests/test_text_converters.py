from __future__ import annotations

import pytest

from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import CodeBlock, Footnote, Heading, Image, ListBlock, Paragraph, Quote, Raw, Table, WarningKind
from intomd.registry import ConvertOptions
from intomd_converters.text.markdown import MarkdownPassthroughConverter, parse_markdown
from intomd_converters.text.plain import PlainTextConverter, decode_text


def _conv_plain(data: bytes, name: str = "a.txt") -> tuple[list[object], list[WarningKind]]:
    ref = InputRef.from_bytes(data, filename=name)
    detect(ref)
    doc = PlainTextConverter().convert(ref, ConvertOptions())
    return list(doc.blocks), [w.kind for w in doc.warnings]


def test_plain_paragraphs_and_line_provenance() -> None:
    blocks, warns = _conv_plain(b"first line\nsecond line\n\n\nthird para\n")
    assert [type(b) for b in blocks] == [Paragraph, Paragraph]
    p0, p1 = blocks
    assert isinstance(p0, Paragraph) and isinstance(p1, Paragraph)
    assert p0.spans[0].text == "first line\nsecond line"
    assert (p0.provenance.line_start, p0.provenance.line_end) == (1, 2)
    assert p1.provenance.line_start == 5
    assert warns == []


def test_plain_setext_headings_only() -> None:
    blocks, _ = _conv_plain(b"Title\n=====\n\nShort line\n\nSub\n---\n\nbody\n")
    kinds = [(type(b).__name__, getattr(b, "level", None)) for b in blocks]
    assert kinds == [("Heading", 1), ("Paragraph", None), ("Heading", 2), ("Paragraph", None)]


def test_plain_control_chars_warned() -> None:
    blocks, warns = _conv_plain(b"hello\x01 wor\x00ld\xe2\x80\x8b\n")
    assert isinstance(blocks[0], Paragraph) and blocks[0].spans[0].text == "hello world"
    assert warns == [WarningKind.REMOVED_HIDDEN_ELEMENTS]


def test_plain_empty_has_warning() -> None:
    ref = InputRef.from_bytes(b"  \n", filename="a.txt")
    detect(ref)
    doc = PlainTextConverter().convert(ref, ConvertOptions())
    assert doc.blocks == [] and doc.warnings[0].kind == WarningKind.EXTRACTION_EMPTY


def test_decode_text() -> None:
    assert decode_text("é".encode())[1] == "utf-8"
    assert decode_text(b"\xef\xbb\xbfhi") == ("hi", "utf-8-sig", False)
    text, enc, uncertain = decode_text("Prévoir une réunion à l'entrepôt.".encode("latin-1"))
    assert not uncertain and "réunion" in text, enc
    assert decode_text("hi".encode("utf-16"))[0] == "hi"


def test_markdown_structure() -> None:
    md = (
        "# T\n\nPara with **b** and [l](https://x.org).\n\n- a\n  - b\n- [x] c\n\n```py\nx = 1\n```\n\n"
        "> q1\n>\n> > nested\n\n| h1 | h2 |\n|---|---|\n| 1 | 2 |\n\n![alt](i.png)\n\nRef[^1]\n\n[^1]: Foot.\n\n"
        "<div>raw</div>\n"
    )
    blocks, _ = parse_markdown(md, "s.md")
    types = [type(b) for b in blocks]
    assert types == [Heading, Paragraph, ListBlock, CodeBlock, Quote, Table, Image, Paragraph, Raw, Footnote]
    para = blocks[1]
    assert isinstance(para, Paragraph)
    assert any(s.href == "https://x.org" for s in para.spans)
    assert any("bold" in s.styles for s in para.spans)
    lb = blocks[2]
    assert isinstance(lb, ListBlock)
    assert lb.items[0].children[0].spans[0].text == "b"
    assert lb.items[1].checked is True and lb.items[1].spans[0].text == "c"
    code = blocks[3]
    assert isinstance(code, CodeBlock) and code.language == "py" and code.code == "x = 1"
    tbl = blocks[5]
    assert isinstance(tbl, Table) and (tbl.n_rows, tbl.n_cols, tbl.header_rows) == (2, 2, 1)
    ref_para = blocks[7]
    assert isinstance(ref_para, Paragraph) and any(s.footnote_ref == "fn-1" for s in ref_para.spans)
    fn = blocks[9]
    assert isinstance(fn, Footnote) and fn.id == "fn-1" and fn.marker == "1" and fn.spans[0].text == "Foot."


def test_markdown_front_matter_title() -> None:
    ref = InputRef.from_bytes(b"---\ntitle: FM Title\n---\n\n# Heading\n\nx\n", filename="a.md")
    detect(ref)
    doc = MarkdownPassthroughConverter().convert(ref, ConvertOptions())
    assert doc.metadata.title == "FM Title"
    assert "front_matter" in doc.metadata.extra


@pytest.mark.parametrize("name", ["a.md", "a.markdown"])
def test_markdown_can_handle(name: str) -> None:
    ref = InputRef.from_bytes(b"plain words only", filename=name)
    detect(ref)
    assert MarkdownPassthroughConverter().can_handle(ref) > 0


def test_markdown_nested_ordered_list_and_quote_paragraphs() -> None:
    blocks, _ = parse_markdown("- a\n  1. x\n  2. y\n\n> p1\n>\n> p2\n", "s.md")
    lb = blocks[0]
    assert isinstance(lb, ListBlock) and lb.items[0].children_ordered and lb.items[0].children_start == 1
    q = blocks[1]
    assert isinstance(q, Quote) and [s.text for s in q.spans] == ["p1", "\n\n", "p2"]
