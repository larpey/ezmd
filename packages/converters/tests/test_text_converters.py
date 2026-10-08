from __future__ import annotations

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import CodeBlock, Footnote, Heading, Image, ListBlock, Paragraph, Quote, Raw, Table, WarningKind
from ezmd.registry import ConvertOptions
from ezmd_converters.text.markdown import MarkdownPassthroughConverter, parse_markdown
from ezmd_converters.text.plain import PlainTextConverter, decode_text


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


def test_encoding_recorded_in_typed_metadata() -> None:
    latin = "Prévoir une réunion à l'entrepôt avant la fin du mois.".encode("latin-1")
    for conv, name in ((PlainTextConverter(), "a.txt"), (MarkdownPassthroughConverter(), "a.md")):
        ref = InputRef.from_bytes(latin, filename=name)
        detect(ref)
        meta = conv.convert(ref, ConvertOptions()).metadata
        assert meta.encoding and meta.encoding != "utf-8" and "encoding" not in meta.extra
        assert meta.encoding_confidence is not None and 0.0 <= meta.encoding_confidence <= 1.0
    ref = InputRef.from_bytes(b"plain ascii", filename="b.txt")
    detect(ref)
    meta = PlainTextConverter().convert(ref, ConvertOptions()).metadata
    assert (meta.encoding, meta.encoding_confidence) == ("utf-8", 1.0)


def _lines(*lines: str) -> bytes:
    return (chr(10).join(lines) + chr(10)).encode()


def test_plain_all_caps_heading_rule() -> None:
    data = _lines("intro", "", "SAFETY EQUIPMENT CHECKS", "", "body", "", "NOTES:", "", "x", "", "TWO WORDS", "", "y")
    blocks, _ = _conv_plain(data)
    heads = [b.spans[0].text for b in blocks if isinstance(b, Heading)]
    assert heads == ["SAFETY EQUIPMENT CHECKS", "NOTES:"]
    assert all(b.level == 2 for b in blocks if isinstance(b, Heading))
    # An ALL-CAPS line inside a paragraph (no blank line around it) stays text.
    blocks, _ = _conv_plain(_lines("first line", "THIS IS SHOUTED TEXT", "last line"))
    assert [type(b) for b in blocks] == [Paragraph]


def test_plain_indented_block_is_code() -> None:
    tab = chr(9)
    blocks, _ = _conv_plain(_lines("Run:", "", "    make all", "", "    make test", tab + "deploy", "", "Done."))
    assert [type(b) for b in blocks] == [Paragraph, CodeBlock, Paragraph]
    code = blocks[1]
    assert isinstance(code, CodeBlock) and code.language is None
    assert code.code == chr(10).join(["make all", "", "make test", "deploy"])
    assert (code.provenance.line_start, code.provenance.line_end) == (3, 6)
    # A continuation line indented inside a paragraph is not code.
    blocks, _ = _conv_plain(_lines("a wrapped", "    continuation"))
    assert [type(b) for b in blocks] == [Paragraph]


def test_plain_caps_heading_rejects_shouted_sentences_and_long_lines() -> None:
    long_caps = "THIS LINE IS FAR TOO LONG TO BE A HEADING BECAUSE IT RUNS ON AND ON"
    data = _lines(
        "a", "", "DO NOT LEAVE BOATS UNATTENDED.", "", "b", "", "WHY IS THE GATE OPEN?", "", long_caps, "", "c"
    )
    blocks, _ = _conv_plain(data)
    assert not [b for b in blocks if isinstance(b, Heading)]


def test_plain_indented_quote_and_sub_list_are_not_code() -> None:
    quote = (
        "    The harbour was calm that morning, and every boat came home",
        "    before the tide turned, just as the old log said it would.",
    )
    blocks, _ = _conv_plain(_lines("He wrote:", "", *quote, "", "Then:", "", "    - first item", "    - second item"))
    assert not [b for b in blocks if isinstance(b, CodeBlock)]
    texts = [b.spans[0].text for b in blocks if isinstance(b, Paragraph)]
    assert texts[1].startswith("The harbour was calm") and "    " not in texts[1]
    assert "- first item" in texts[3] and "- second item" in texts[3]
    # Shell commands without sentence punctuation stay code.
    blocks, _ = _conv_plain(_lines("Run:", "", "    valve close main", "    pump drain --all", "    valve open bleed"))
    assert [type(b) for b in blocks] == [Paragraph, CodeBlock]


def test_plain_whitespace_table_and_outline_lines() -> None:
    data = _lines(
        "1. Check the lines.",
        "2. Test the posts.",
        "   2.1 Reset a breaker.",
        "3. Clear the slipway.",
        "",
        "Item         Location        Checked",
        "Life ring    Pontoon A head  daily",
        "Ladder       Each finger     weekly",
        "",
        "Two  spaced  words",
        "do not  make a table",
    )
    blocks, _ = _conv_plain(data)
    assert [type(b) for b in blocks] == [Paragraph, Table, Paragraph]
    outline = blocks[0]
    assert isinstance(outline, Paragraph)
    assert outline.spans[0].text.split(chr(10)) == [
        "1. Check the lines.",
        "2. Test the posts.",
        "2.1 Reset a breaker.",
        "3. Clear the slipway.",
    ]
    table = blocks[1]
    assert isinstance(table, Table) and (table.n_rows, table.n_cols, table.header_rows) == (3, 3, 1)
    grid = [[c.spans[0].text for c in table.cells if c.row == r] for r in range(3)]
    assert grid[1] == ["Life ring", "Pontoon A head", "daily"]
    assert (table.provenance.line_start, table.provenance.line_end) == (6, 8)


def test_markdown_callout_title_keeps_its_own_paragraph() -> None:
    nl = chr(10)
    text = nl.join(["> [!warning] Calibration due", "> The gauge drifts.", "", "> plain quote", "> continues"])
    blocks, _ = parse_markdown(text + nl, "x.md")
    callout, plain = (b for b in blocks if isinstance(b, Quote))
    assert callout.attrs == {"callout": "warning"}
    assert [s.text for s in callout.spans] == ["Calibration due", nl + nl, "The gauge drifts."]
    assert plain.attrs == {} and [s.text for s in plain.spans] == ["plain quote continues"]
    folded, *_ = (
        b for b in parse_markdown("> [!note]- Folded" + nl + "> body" + nl, "x.md")[0] if isinstance(b, Quote)
    )
    assert folded.attrs == {"callout": "note", "callout_fold": "closed"}
