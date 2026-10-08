from __future__ import annotations

import pytest
from core_factories import SRC, P, S, every_block_document
from pydantic import TypeAdapter, ValidationError

from ezmd.ir import (
    BBox,
    Block,
    ConversionResult,
    Document,
    Heading,
    InputRefInfo,
    ListBlock,
    ListItem,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
    spans_text,
)
from ezmd.warnings.codes import CODES

BLOCK = TypeAdapter(Block)


def test_every_block_type_round_trips() -> None:
    doc = every_block_document().finalize()
    types = {b.type for b in doc.blocks}
    assert len(types) == 17
    for b in doc.blocks:
        again = BLOCK.validate_json(BLOCK.dump_json(b))
        assert again == b
    again_doc = Document.model_validate_json(doc.model_dump_json())
    assert again_doc.model_dump() == doc.model_dump()


def test_finalize_assigns_ids_hash_and_is_idempotent() -> None:
    doc = every_block_document()
    doc.finalize()
    ids = [b.id for b in doc.blocks]
    assert ids[0] == "b0001"
    assert "fig1" in ids and "s1" in ids
    assert doc.content_hash.startswith("sha256:") and len(doc.content_hash) == 71
    h = doc.content_hash
    assert doc.finalize().content_hash == h
    assert [b.id for b in doc.blocks] == ids
    assert doc.finalized


def test_finalize_rejects_duplicate_ids() -> None:
    doc = Document(
        metadata=Metadata(source=SRC, source_type=SourceType.TEXT),
        blocks=[Paragraph(id="x", spans=[S("a")], provenance=P()), Paragraph(id="x", spans=[S("b")], provenance=P())],
    )
    with pytest.raises(ValueError, match="duplicate"):
        doc.finalize()


def test_finalize_rejects_dangling_parent() -> None:
    doc = Document(
        metadata=Metadata(source=SRC, source_type=SourceType.TEXT),
        blocks=[Paragraph(spans=[S("a")], parent_id="nope", provenance=P())],
    )
    with pytest.raises(ValueError, match="unknown parent"):
        doc.finalize()


def test_finalize_recurses_into_children() -> None:
    child = Document(
        metadata=Metadata(source="a!b", source_type=SourceType.TEXT), blocks=[Paragraph(spans=[S("c")], provenance=P())]
    )
    doc = Document(metadata=Metadata(source=SRC, source_type=SourceType.ARCHIVE), children=[child]).finalize()
    assert doc.children[0].content_hash.startswith("sha256:")


def test_table_rejects_out_of_shape_cells() -> None:
    with pytest.raises(ValidationError, match="exceeds table shape"):
        Table(cells=[TableCell(spans=[S("x")], row=1, col=0)], n_rows=1, n_cols=1, provenance=P())
    with pytest.raises(ValidationError):
        Table(cells=[TableCell(spans=[S("x")], row=0, col=0, col_span=2)], n_rows=1, n_cols=1, provenance=P())


def test_table_sets_merged_flag_and_grid() -> None:
    t = Table(
        cells=[TableCell(spans=[S("x")], row=0, col=0, col_span=2), TableCell(spans=[S("y")], row=1, col=1)],
        n_rows=2,
        n_cols=2,
        provenance=P(),
    )
    assert t.has_merged_cells
    g = t.grid()
    assert g[0][0] is not None and g[0][1] is None and g[1][1] is not None
    plain = Table(cells=[TableCell(spans=[S("x")], row=0, col=0)], n_rows=1, n_cols=1, provenance=P())
    assert not plain.has_merged_cells


def test_bbox_order_validated() -> None:
    with pytest.raises(ValidationError):
        BBox(x0=5, y0=0, x1=1, y1=1)


def test_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        Provenance(source=SRC, confidence=1.5)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Paragraph(spans=[], provenance=P(), bogus=1)  # type: ignore[call-arg]


def test_plain_text_ordering() -> None:
    doc = every_block_document()
    text = doc.plain_text()
    order = [
        "Title",
        "Intro bold link",
        "a\nb\n1",
        "one\none.a\ntwo",
        "print('hi')",
        "alt text",
        "note",
        "E=mc^2",
        "hello there",
        "a comment",
        "inserted",
        "quoted",
        "<b>raw</b>",
    ]
    pos = [text.index(o) for o in order]
    assert pos == sorted(pos)


def test_counts_on_every_block_type() -> None:
    c = every_block_document().counts()
    assert (c.headings, c.paragraphs, c.tables, c.table_cells) == (1, 2, 1, 3)
    assert (c.lists, c.list_items, c.code_blocks, c.images, c.figures) == (1, 3, 1, 1, 1)
    assert (c.footnotes, c.equations, c.page_breaks, c.transcript_segments) == (1, 1, 1, 1)
    assert (c.slides, c.comments, c.tracked_changes, c.links, c.quotes, c.raw) == (1, 1, 1, 2, 1, 1)
    assert c.words == len(every_block_document().plain_text().split())


def test_sections_with_leading_heading() -> None:
    doc = Document(
        metadata=Metadata(source=SRC, source_type=SourceType.TEXT),
        blocks=[
            Heading(level=1, spans=[S("A")], provenance=P()),
            Paragraph(spans=[S("a1")], provenance=P()),
            Heading(level=2, spans=[S("B")], provenance=P()),
            Paragraph(spans=[S("b1")], provenance=P()),
            Paragraph(spans=[S("b2")], provenance=P()),
        ],
    ).finalize()
    secs = doc.sections()
    assert secs[0][0].id == "b0000" and secs[0][1] == []
    assert [spans_text(h.spans) for h, _ in secs[1:]] == ["A", "B"]
    assert [len(bs) for _, bs in secs] == [0, 1, 2]


def test_sections_without_leading_heading() -> None:
    doc = Document(
        metadata=Metadata(source=SRC, source_type=SourceType.TEXT),
        blocks=[Paragraph(spans=[S("pre")], provenance=P()), Heading(level=1, spans=[S("H")], provenance=P())],
    )
    secs = doc.sections()
    assert len(secs) == 2 and len(secs[0][1]) == 1 and secs[1][1] == []


def test_list_item_nesting_round_trip() -> None:
    lb = ListBlock(items=[ListItem(spans=[S("a")], children=[ListItem(spans=[S("b")], checked=True)])], provenance=P())
    again = ListBlock.model_validate_json(lb.model_dump_json())
    assert again.items[0].children[0].checked is True


def test_warning_default_severity_from_registry() -> None:
    w = Warning(kind=WarningKind.EXTRACTION_EMPTY, message="x")
    assert w.severity == CODES[WarningKind.EXTRACTION_EMPTY].severity == "error"
    w2 = Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="info", message="x")
    assert w2.severity == "info"
    w3 = Warning.model_validate({"kind": "removed_hidden_elements", "message": "x"})
    assert w3.severity == "info"


def test_conversion_result_all_warnings() -> None:
    doc = Document(metadata=Metadata(source=SRC, source_type=SourceType.TEXT))
    doc.warnings.append(Warning(kind=WarningKind.OTHER, message="doc"))
    r = ConversionResult(
        document=doc,
        warnings=[Warning(kind=WarningKind.OTHER, message="pipe")],
        converter_id="text.plain",
        input_ref=InputRefInfo(kind="bytes", display="a.txt"),
    )
    assert [w.message for w in r.all_warnings] == ["pipe", "doc"]
    again = ConversionResult.model_validate_json(r.model_dump_json())
    assert again.input_ref.display == "a.txt"


def test_reconciled_input_kinds_accepted() -> None:
    for k in ("transcript_segments", "captions_json3", "media_upload"):
        assert InputRefInfo(kind=k, display="x").kind == k  # type: ignore[arg-type]
