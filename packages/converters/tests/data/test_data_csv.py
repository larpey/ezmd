from __future__ import annotations

import pytest
from conftest import Convert

from ezmd.ir import Document, Heading, Table, WarningKind
from ezmd.registry import ConversionError
from ezmd_converters.data.csv_conv import CsvConverter, sniff_dialect

NL = chr(10)
TAB = chr(9)
BOM = bytes([0xEF, 0xBB, 0xBF])


def _table(doc: Document) -> Table:
    tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert len(tables) == 1
    return tables[0]


def _rows(t: Table) -> list[list[str]]:
    grid = t.grid()
    return [["".join(s.text for s in c.spans) if c else "" for c in row] for row in grid]


def _kinds(doc: Document) -> list[WarningKind]:
    return [w.kind for w in doc.warnings]


def test_bom_semicolon_quoted_newline(convert: Convert) -> None:
    data = BOM + ("id;name;amount" + NL + '1;"A; B";1,50' + NL + '2;"x' + NL + 'y";2,00' + NL).encode()
    doc = convert(CsvConverter(), data, "a.csv")
    t = _table(doc)
    assert _rows(t) == [["id", "name", "amount"], ["1", "A; B", "1,50"], ["2", "x" + NL + "y", "2,00"]]
    assert t.header_rows == 1 and t.column_types == ["int", "text", "float"]
    assert t.provenance.path == "A1:C3"
    assert doc.metadata.encoding == "utf-8-sig" and doc.metadata.extra["delimiter"] == "semicolon"
    assert isinstance(doc.blocks[0], Heading) and doc.blocks[0].spans[0].text == "a.csv"
    assert _kinds(doc) == []


@pytest.mark.parametrize(("delim", "name"), [(",", "comma"), ("|", "pipe"), (TAB, "tab")])
def test_delimiters(convert: Convert, delim: str, name: str) -> None:
    lines = [delim.join(["k", "v", "w"])] + [delim.join([f"r{i}", str(i), f"{i}.5"]) for i in range(5)]
    doc = convert(CsvConverter(), (NL.join(lines) + NL).encode(), "a.csv")
    assert doc.metadata.extra["delimiter"] == name
    assert _table(doc).n_cols == 3


def test_tsv_forces_tab(convert: Convert) -> None:
    data = ("a,b" + TAB + "c" + NL + "1,2" + TAB + "3" + NL).encode()
    doc = convert(CsvConverter(), data, "x.tsv")
    assert _rows(_table(doc))[1] == ["1,2", "3"]
    assert doc.metadata.extra["format"] == "TSV"


def test_synthetic_header_when_first_row_is_data(convert: Convert) -> None:
    doc = convert(CsvConverter(), b"1,2,3\n4,5,6\n7,8,9\n", "n.csv")
    t = _table(doc)
    assert _rows(t)[0] == ["A", "B", "C"] and t.n_rows == 4
    assert t.attrs["header_synthesized"] == "true"


def test_ragged_rows_padded_and_overflowed(convert: Convert) -> None:
    doc = convert(CsvConverter(), b"a,b,c\n1,2\n3,4,5,6\n7,8,9\n", "r.csv")
    rows = _rows(_table(doc))
    assert rows[1] == ["1", "2", ""] and rows[2] == ["3", "4", "5,6"]
    w = next(w for w in doc.warnings if w.kind == WarningKind.RAGGED_ROWS)
    assert w.count == 2


def test_row_cap(convert: Convert) -> None:
    data = ("h,v" + NL + NL.join(f"r{i},{i}" for i in range(20)) + NL).encode()
    doc = convert(CsvConverter(), data, "c.csv", csv_max_rows=5)
    assert _table(doc).n_rows == 6
    assert WarningKind.ROW_CAP_REACHED in _kinds(doc) and doc.truncated


def test_column_cap(convert: Convert) -> None:
    data = (",".join(f"c{i}" for i in range(10)) + NL + ",".join(str(i) for i in range(10)) + NL).encode()
    doc = convert(CsvConverter(), data, "c.csv", csv_max_cols=4)
    assert _table(doc).n_cols == 4 and WarningKind.COLUMNS_TRUNCATED in _kinds(doc)


def test_latin1_and_utf16(convert: Convert) -> None:
    e, a = chr(0xE9), chr(0xE0)
    rows = [f"Ren{e}e,caf{e} pr{e}s de la gare", f"Andr{e},d{e}j{a} vu {a} Paris", f"Zo{e},th{e} et g{a}teau"]
    text = "name,note" + NL + NL.join(rows) + NL
    for enc in ("latin-1", "utf-16"):
        doc = convert(CsvConverter(), text.encode(enc), "e.csv")
        assert _rows(_table(doc))[2] == [f"Andr{e}", f"d{e}j{a} vu {a} Paris"], enc


def test_control_chars_removed_and_counted(convert: Convert) -> None:
    doc = convert(CsvConverter(), b"a,b\nx\x01y,2\n", "c.csv")
    assert _rows(_table(doc))[1] == ["xy", "2"]
    assert WarningKind.REMOVED_HIDDEN_ELEMENTS in _kinds(doc)


def test_long_cell_cut_with_raw_value(convert: Convert) -> None:
    long = "z" * 900
    doc = convert(CsvConverter(), f"a,b\n1,{long}\n".encode(), "c.csv")
    cell = next(c for c in _table(doc).cells if c.row == 1 and c.col == 1)
    assert len(cell.spans[0].text) == 500 and cell.raw_value == long


def test_empty_input_raises(convert: Convert) -> None:
    with pytest.raises(ConversionError):
        convert(CsvConverter(), b"   \n", "e.csv")


def test_sniffer_fallback_on_single_column() -> None:
    d = sniff_dialect("alpha" + NL + "beta" + NL)
    assert d.delimiter in (",", ";", TAB, "|")


def test_can_handle() -> None:
    from ezmd.inputs import Detected, InputRef

    ref = InputRef.from_bytes(b"a,b", filename="x.csv")
    ref.detected = Detected(mime="text/csv", extension=".csv", confidence=1.0)
    assert CsvConverter().can_handle(ref) == 0.95
    ref.detected = Detected(mime="text/plain", extension=".csv", confidence=0.6)
    assert CsvConverter().can_handle(ref) == 0.6
    ref.detected = Detected(mime="application/pdf", extension=".csv", confidence=1.0)
    assert CsvConverter().can_handle(ref) == 0.0
