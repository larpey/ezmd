"""JSON, JSON Lines, YAML and TOML through the shared tree renderer."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from intomd.ir import CodeBlock, Document, Heading, ListBlock, Paragraph, Table, WarningKind
from intomd.registry import ConversionError
from intomd_converters.data._common import RawNumber, to_json
from intomd_converters.data._tree import clip, pointer_child
from intomd_converters.data.json_conv import JsonConverter
from intomd_converters.data.toml_conv import TomlConverter
from intomd_converters.data.yaml_conv import YamlConverter

NL = chr(10)
Convert = Callable[..., Document]


def _tables(doc: Document) -> list[Table]:
    """Data tables only: schema, structure and namespace summaries are left out."""
    out = []
    for b in doc.blocks:
        if isinstance(b, Table):
            first = next((c for c in b.cells if c.row == 0 and c.col == 0), None)
            if first is None or first.spans[0].text not in ("Path", "Element path", "Prefix"):
                out.append(b)
    return out


def _cells(t: Table) -> list[list[str]]:
    return [["".join(s.text for s in c.spans) if c else "" for c in row] for row in t.grid()]


def _kinds(doc: Document) -> list[WarningKind]:
    return [w.kind for w in doc.warnings]


def _headings(doc: Document) -> list[tuple[int, str]]:
    return [(b.level, b.spans[0].text) for b in doc.blocks if isinstance(b, Heading)]


# ---------------------------------------------------------------- JSON


def test_json_records_keep_number_spelling(convert: Convert) -> None:
    data = (
        b'[{"id": 12345678901234567890, "v": 1.10, "big": 1e400, "n": null, "o": {"a": {"b": 1}}}, '
        b'{"id": 2, "v": 3, "big": 0, "n": 1}]'
    )
    doc = convert(JsonConverter(), data, "r.json")
    (t,) = _tables(doc)
    rows = _cells(t)
    assert rows[0] == ["id", "v", "big", "n", "o.a.b"]
    assert rows[1] == ["12345678901234567890", "1.10", "1e400", "null", "1"]
    assert rows[2] == ["2", "3", "0", "1", ""]
    assert t.column_types == ["int", "float", "float", "int", "int"]
    assert t.provenance.path == "/"


def test_json_nested_object_layout(convert: Convert) -> None:
    data = json.dumps({"name": "x", "db": {"host": "h", "pool": {"max": 3}}, "tags": ["a", "b"]}).encode()
    doc = convert(JsonConverter(), data, "c.json")
    assert _headings(doc) == [(1, "c.json"), (2, "Schema"), (2, "Data"), (3, "db"), (4, "pool"), (3, "tags")]
    first, db, pool, last = _tables(doc)
    assert _cells(first) == [["Key", "Value"], ["name", "x"]]
    assert _cells(db) == [["Key", "Value"], ["host", "h"]]
    assert _cells(last) == [["Key", "Value"], ["tags", '["a", "b"]']]
    tags = next(b for b in doc.blocks if isinstance(b, Heading) and b.spans[0].text == "tags")
    assert tags.provenance.path == "/tags" and doc.blocks.index(tags) + 1 == doc.blocks.index(last)
    assert _cells(pool) == [["Key", "Value"], ["max", "3"]]
    assert pool.provenance.path == "/db/pool"
    assert isinstance(doc.blocks[1], Paragraph)  # summary line


def test_json_scalar_list_and_code_fallback(convert: Convert) -> None:
    data = json.dumps({"items": list(range(30)), "mixed": [1, {"a": 2}]}).encode()
    doc = convert(JsonConverter(), data, "l.json")
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    assert len(lists) == 1 and len(lists[0].items) == 30
    assert lists[0].items[3].provenance is not None and lists[0].items[3].provenance.path == "/items/3"
    code = [b for b in doc.blocks if isinstance(b, CodeBlock)]
    assert code and code[0].language == "json" and '"a": 2' in code[0].code


def test_json_deep_nesting_truncated(convert: Convert) -> None:
    deep = "[" * 200 + "1" + "]" * 200
    doc = convert(JsonConverter(), deep.encode(), "d.json")
    assert WarningKind.DEPTH_TRUNCATED in _kinds(doc)
    assert doc.blocks  # rendered without recursion errors


def test_json_extreme_nesting_is_a_clean_error(convert: Convert) -> None:
    deep = "[" * 100_000 + "]" * 100_000
    with pytest.raises(ConversionError):
        convert(JsonConverter(), deep.encode(), "d.json")


def test_json_records_sampled(convert: Convert) -> None:
    data = json.dumps([{"i": i} for i in range(1500)]).encode()
    doc = convert(JsonConverter(), data, "s.json")
    (t,) = _tables(doc)
    rows = _cells(t)
    assert t.n_rows == 1 + 100 + 20
    assert rows[100] == ["99"] and rows[101] == ["1480"] and rows[-1] == ["1499"]
    assert t.attrs == {"rows_total": "1500", "rows_omitted": "1380", "omitted_after_row": "100"}
    note = doc.blocks[doc.blocks.index(t) + 1]
    assert isinstance(note, Paragraph) and "1,380 rows omitted after row 100" in note.spans[0].text
    assert WarningKind.ROWS_SAMPLED in _kinds(doc)


def test_json_columns_truncated(convert: Convert) -> None:
    data = json.dumps([{f"k{i}": i for i in range(60)}]).encode()
    doc = convert(JsonConverter(), data, "w.json")
    assert _tables(doc)[0].n_cols == 50 and WarningKind.COLUMNS_TRUNCATED in _kinds(doc)


def test_json_api_error_first(convert: Convert) -> None:
    data = json.dumps({"data": [], "error": {"code": 401, "message": "no"}}).encode()
    doc = convert(JsonConverter(), data, "e.json")
    assert WarningKind.API_ERROR_PAYLOAD in _kinds(doc)
    assert _headings(doc)[3] == (3, "error")


def test_jsonl_partial_last_line(convert: Convert) -> None:
    data = (NL.join(json.dumps({"a": i}) for i in range(4)) + NL + '{"a": 9').encode()
    doc = convert(JsonConverter(), data, "x.jsonl")
    assert _tables(doc)[0].n_rows == 5
    w = next(w for w in doc.warnings if w.kind == WarningKind.MARKUP_PARTIAL)
    assert w.detail["lines"] == "5"


def test_json_falls_back_to_lines(convert: Convert) -> None:
    data = b'{"a": 1}\n{"a": 2}\n'
    doc = convert(JsonConverter(), data, "x.json")
    assert doc.metadata.extra["format"] == "JSON Lines"


def test_json_invalid_raises(convert: Convert) -> None:
    with pytest.raises(ConversionError):
        convert(JsonConverter(), b"{not json", "bad.json")


def test_json_bom_and_scalar(convert: Convert) -> None:
    doc = convert(JsonConverter(), bytes([0xEF, 0xBB, 0xBF]) + b'"hello"', "s.json")
    assert isinstance(doc.blocks[-1], Paragraph) and doc.blocks[-1].spans[0].text == "hello"


def test_json_empty_containers(convert: Convert) -> None:
    assert "(empty list)" in convert(JsonConverter(), b"[]", "e.json").plain_text()
    assert "(empty object)" in convert(JsonConverter(), b"{}", "e.json").plain_text()


def test_pointer_escaping_and_to_json() -> None:
    assert pointer_child("/", "a/b~c") == "/a~1b~0c"
    assert to_json({"x": [RawNumber("1.10"), None, True]}) == '{"x": [1.10, null, true]}'


def test_clip_handles_cycles_with_node_budget() -> None:
    a: list[object] = []
    a.append(a)
    res = clip(a, max_depth=64, max_nodes=1000)
    assert res.depth_cut == 1 and res.shown_depth == 64
    # The cut subtree is the list itself: measuring stops at the revisit and reports a lower bound.
    assert res.depth == 65 and res.depth_exact is False


def test_clip_measures_true_depth_below_the_cap() -> None:
    value: dict[str, object] = {"leaf": 1}
    for i in range(16):
        value = {f"n{i}": value, "x": [i]}
    res = clip(value, max_depth=12, max_nodes=10_000)
    assert res.shown_depth == 12 and res.depth == 17 and res.depth_exact
    assert res.depth_cut > 0


def test_clip_measure_respects_node_budget() -> None:
    deep: list[object] = []
    cur = deep
    for _ in range(200):
        nxt: list[object] = []
        cur.append(nxt)
        cur = nxt
    res = clip(deep, max_depth=5, max_nodes=50)
    assert res.shown_depth == 5 and res.depth_exact is False and 5 < res.depth < 200


def test_schema_reports_truncated_container_type(convert: Convert) -> None:
    value = "1"
    for i in range(6):
        value = '{"k' + str(i) + '": ' + value + "}"
    doc = convert(JsonConverter(), value.encode(), "d.json", max_depth=3)
    text = doc.plain_text()
    assert "object (truncated)" in text
    assert doc.metadata.extra["depth"] == 6 and doc.metadata.extra["depth_cap"] == 3
    assert "nesting depth 6 (shown to 3 levels)" in text


# ---------------------------------------------------------------- YAML


def test_yaml_unsafe_tag_is_inert(convert: Convert) -> None:
    data = b'cmd: !!python/object/apply:os.system ["echo hi"]\nother: !Ref Thing\n'
    doc = convert(YamlConverter(), data, "u.yaml")
    rows = _cells(_tables(doc)[0])
    assert rows[1] == ["cmd", '!!python/object/apply:os.system ["echo hi"]']
    assert rows[2] == ["other", "!Ref Thing"]
    w = next(w for w in doc.warnings if w.kind == WarningKind.YAML_UNSAFE_TAGS)
    assert w.count == 2


def test_yaml_anchors_and_verbatim_numbers(convert: Convert) -> None:
    data = b"base: &b\n  t: 1.50\n  d: 2026-01-02\nuse:\n  <<: *b\n  n: 0x1F\n"
    doc = convert(YamlConverter(), data, "a.yaml")
    assert doc.metadata.extra["anchors_expanded"] is True
    use = _cells(_tables(doc)[1])
    assert use[1:] == [["t", "1.50"], ["d", "2026-01-02"], ["n", "0x1F"]]


def test_yaml_multi_document(convert: Convert) -> None:
    data = b"kind: A\n---\nkind: B\n"
    doc = convert(YamlConverter(), data, "m.yaml")
    assert _headings(doc)[1:] == [(2, "Schema"), (2, "Data"), (3, "Document 1"), (3, "Document 2"), (2, "Source")]


def test_yaml_alias_bomb_is_bounded(convert: Convert) -> None:
    lines = ['a: &a ["x","x","x","x","x","x","x","x","x","x"]']
    for i in range(1, 9):
        prev, cur = chr(96 + i), chr(97 + i)
        lines.append(f"{cur}: &{cur} [{', '.join('*' + prev for _ in range(10))}]")
    doc = convert(YamlConverter(), (NL.join(lines) + NL).encode(), "bomb.yaml", max_nodes=5000)
    assert WarningKind.SIZE_CAP in _kinds(doc)


def test_yaml_comments_kept_as_source(convert: Convert) -> None:
    doc = convert(YamlConverter(), b"# note\na: 1\n", "c.yaml")
    code = [b for b in doc.blocks if isinstance(b, CodeBlock)]
    assert code and code[0].language == "yaml" and "# note" in code[0].code


def test_yaml_invalid_raises(convert: Convert) -> None:
    with pytest.raises(ConversionError):
        convert(YamlConverter(), b"a: [1, 2\n", "bad.yaml")


def test_yaml_partial_stream_warns(convert: Convert) -> None:
    doc = convert(YamlConverter(), b"a: 1\n---\nb: [\n", "p.yaml")
    assert WarningKind.MARKUP_PARTIAL in _kinds(doc)


# ---------------------------------------------------------------- TOML


def test_toml_tables_and_arrays(convert: Convert) -> None:
    data = b'x = 1.10\nwhen = 2026-01-02T03:04:05Z\n[a.b]\nk = "v"\n[[r]]\nn = 1\n[[r]]\nn = 2\n'
    doc = convert(TomlConverter(), data, "c.toml")
    first = _cells(_tables(doc)[0])
    assert first[1:] == [["x", "1.10"], ["when", "2026-01-02T03:04:05Z"]]
    assert _headings(doc)[1:] == [(2, "a"), (3, "b"), (2, "r"), (2, "Source")]
    assert _cells(_tables(doc)[-1]) == [["n"], ["1"], ["2"]]
    code = [b for b in doc.blocks if isinstance(b, CodeBlock)]
    assert code[-1].language == "toml" and code[-1].provenance.line_end == 8


def test_toml_invalid_raises(convert: Convert) -> None:
    with pytest.raises(ConversionError):
        convert(TomlConverter(), b"x = = 1\n", "bad.toml")


def test_global_safe_loader_untouched() -> None:
    import yaml

    with pytest.raises(yaml.YAMLError):
        yaml.safe_load("x: !!python/object/apply:os.system ['true']")
    assert yaml.safe_load("v: 1.50") == {"v": 1.5}


def test_json_sparse_objects_are_not_records(convert: Convert) -> None:
    data = json.dumps({"things": [{"a": 1}, {"b": 2}, {"c": 3}]}).encode()
    doc = convert(JsonConverter(), data, "s.json")
    assert (4, "things 2") in _headings(doc)


def test_json_key_order_preserved(convert: Convert) -> None:
    data = b'{"first": 1, "nested": {"x": 1}, "last": 2}'
    doc = convert(JsonConverter(), data, "o.json")
    first, nested, last = _tables(doc)
    assert _cells(first)[1:] == [["first", "1"]] and _cells(last)[1:] == [["last", "2"]]
    assert doc.blocks.index(first) < doc.blocks.index(nested) < doc.blocks.index(last)


def test_schema_table(convert: Convert) -> None:
    data = json.dumps({"rows": [{"a": 1, "b": None}, {"a": 2.5, "b": "x"}]}).encode()
    doc = convert(JsonConverter(), data, "s.json")
    schema = next(b for b in doc.blocks if isinstance(b, Table))
    rows = _cells(schema)
    assert rows[0] == ["Path", "Types", "Count", "Null %", "Examples"]
    assert ["/rows/*/a", "integer, number", "2", "0", "1, 2.5"] in rows
    assert ["/rows/*/b", "null, string", "2", "50", "x"] in rows


def test_scalar_run_after_nested_gets_other_keys_heading(convert: Convert) -> None:
    data = b'{"a": {"x": 1}, "b": 1, "c": 2, "d": {"y": 2}, "e": 3}'
    doc = convert(JsonConverter(), data, "o.json")
    assert _headings(doc)[3:] == [(3, "a"), (3, "Other keys"), (3, "d"), (3, "e")]
