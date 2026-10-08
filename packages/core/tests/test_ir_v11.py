"""IR schema 1.1 additions (D-0017 item 1): provenance fields, typed metadata, column types, nesting caps,
warning aliases."""

from __future__ import annotations

import pytest
from core_factories import SRC, P, S
from pydantic import ValidationError

from intomd.ir import (
    MAX_CHILD_DEPTH,
    MAX_NEST_DEPTH,
    Document,
    ListBlock,
    ListItem,
    Metadata,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
)
from intomd.warnings.codes import ALIASES, CODES, normalize_code, spec_for


def _meta(**kw: object) -> Metadata:
    return Metadata(source=SRC, source_type=SourceType.TEXT, **kw)  # type: ignore[arg-type]


def _nested(depth: int) -> ListItem:
    item = ListItem(spans=[S(str(depth))])
    for level in range(depth - 1, 0, -1):
        item = ListItem(spans=[S(str(level))], children=[item])
    return item


def _max_level(items: list[ListItem]) -> int:
    deepest = 0
    stack = [(it, 1) for it in items]
    while stack:
        it, level = stack.pop()
        deepest = max(deepest, level)
        stack.extend((c, level + 1) for c in it.children)
    return deepest


def test_new_fields_round_trip() -> None:
    prov = P(page_label="iv", path="docs/a.md", source_id="msg-1", char_start=3, char_end=9, source_label="Sheet1")
    table = Table(
        cells=[TableCell(spans=[S("a")], row=0, col=0), TableCell(spans=[S("1")], row=0, col=1)],
        n_rows=1,
        n_cols=2,
        column_types=["text", "currency"],
        provenance=prov,
    )
    meta = _meta(encoding="cp1252", encoding_confidence=0.82, languages=["en", "fr"], language_source="detected")
    doc = Document(metadata=meta, blocks=[table], truncated=True).finalize()
    assert doc.schema_version == "1.1"
    again = Document.model_validate_json(doc.model_dump_json())
    assert again.model_dump() == doc.model_dump()
    assert again.truncated and again.metadata.languages == ["en", "fr"]
    t = again.blocks[0]
    assert isinstance(t, Table) and t.column_types == ["text", "currency"] and t.provenance.char_end == 9


def test_schema_version_1_still_accepted() -> None:
    doc = Document.model_validate({"schema_version": "1", "metadata": {"source": SRC, "source_type": "text"}})
    assert doc.schema_version == "1"
    with pytest.raises(ValidationError):
        Document.model_validate({"schema_version": "2", "metadata": {"source": SRC, "source_type": "text"}})


def test_new_field_validation() -> None:
    with pytest.raises(ValidationError):
        P(char_start=-1)
    with pytest.raises(ValidationError):
        P(char_start=5, char_end=2)
    with pytest.raises(ValidationError):
        _meta(encoding_confidence=1.5)
    with pytest.raises(ValidationError):
        _meta(language_source="guess")
    with pytest.raises(ValidationError, match="column_types"):
        Table(cells=[], n_rows=0, n_cols=2, column_types=["text"], provenance=P())
    with pytest.raises(ValidationError):
        Table(cells=[], n_rows=0, n_cols=1, column_types=["number"], provenance=P())  # type: ignore[list-item]


def test_fifty_deep_list_finalizes_serializes_and_warns() -> None:
    doc = Document(metadata=_meta(), blocks=[ListBlock(items=[_nested(50)], provenance=P())])
    text_before = doc.plain_text()
    doc.finalize()
    block = doc.blocks[0]
    assert isinstance(block, ListBlock)
    assert _max_level(block.items) == MAX_NEST_DEPTH + 1
    assert doc.plain_text() == text_before  # text order kept
    warns = [w for w in doc.warnings if w.kind == WarningKind.NESTING_FLATTENED]
    assert len(warns) == 1 and warns[0].count == 50 - MAX_NEST_DEPTH - 1 and warns[0].severity == "info"
    again = Document.model_validate_json(doc.model_dump_json())
    assert again.plain_text() == text_before
    doc.finalize()  # idempotent: no second warning
    assert sum(w.kind == WarningKind.NESTING_FLATTENED for w in doc.warnings) == 1


def test_shallow_lists_untouched() -> None:
    doc = Document(metadata=_meta(), blocks=[ListBlock(items=[_nested(MAX_NEST_DEPTH + 1)], provenance=P())])
    doc.finalize()
    assert not doc.warnings


def test_children_depth_limit() -> None:
    def chain(depth: int) -> Document:
        doc = Document(metadata=_meta())
        for _ in range(depth):
            doc = Document(metadata=_meta(), children=[doc])
        return doc

    chain(MAX_CHILD_DEPTH).finalize()
    with pytest.raises(ValueError, match="children"):
        chain(MAX_CHILD_DEPTH + 1).finalize()


def test_aliases_normalize_and_parse() -> None:
    assert set(ALIASES).isdisjoint({k.value for k in WarningKind})
    assert normalize_code("page_limit_reached") is WarningKind.PAGE_CAP_REACHED
    assert normalize_code("truncated_max_tokens") is WarningKind.TRUNCATED
    assert normalize_code("possible_prompt_injection") is WarningKind.INJECTION_SUSPECTED
    assert normalize_code("engine_fallback") is WarningKind.ENGINE_FALLBACK
    with pytest.raises(ValueError):
        normalize_code("no_such_code")
    w = Warning.model_validate({"kind": "fallback_engine_used", "message": "m"})
    assert w.kind is WarningKind.ENGINE_FALLBACK and w.severity == CODES[WarningKind.ENGINE_FALLBACK].severity
    assert Warning(kind="hidden_sheets", message="m").kind is WarningKind.HIDDEN_SHEETS_INCLUDED  # type: ignore[arg-type]
    assert spec_for("unreadable_regions").code is WarningKind.UNREADABLE_REGION
    with pytest.raises(ValidationError):
        Warning.model_validate({"kind": "no_such_code", "message": "m"})


def test_truncating_codes() -> None:
    for kind in (WarningKind.PAGE_CAP_REACHED, WarningKind.ROW_CAP_REACHED, WarningKind.TIMEOUT_PARTIAL):
        assert CODES[kind].truncates
    assert CODES[WarningKind.TABLE_SAMPLED].truncates and CODES[WarningKind.TRUNCATED].truncates
    assert not CODES[WarningKind.ENCODING_UNCERTAIN].truncates
