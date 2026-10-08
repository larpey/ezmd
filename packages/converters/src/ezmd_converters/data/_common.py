"""Shared helpers for the data family: options, decoding, table construction, value formatting.

Values are never reformatted: numbers keep their source spelling (`RawNumber`), strings are cleaned of
control and invisible characters only, and long strings are cut for display with the full value kept in
`TableCell.raw_value`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields
from typing import Any

from ezmd.core.textclean import CleanStats, clean_text
from ezmd.ir import ColumnType, InlineSpan, Paragraph, Provenance, Table, TableCell, Warning, WarningKind
from ezmd.registry import ConvertOptions

MAX_CELL_CHARS = 500
"""Longer strings are shown cut with an ellipsis; the full value stays in raw_value (Part 2 10c step 6)."""
MAX_RAW_CHARS = 100_000
"""Upper bound on raw_value so a single huge string cannot bloat the sidecar without limit."""
ELLIPSIS = chr(0x2026)


class RawNumber(str):
    """A number kept as its source spelling (`1.10`, `1e400`, 19-digit ids never round-trip through float)."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class DataOptions:
    """`options.extra["data.<name>"]` values with the Part 2 10h defaults."""

    max_bytes: int = 50 * 1024 * 1024
    max_rows: int = 1000
    head_rows: int = 100
    tail_rows: int = 20
    max_cols: int = 50
    schema_depth: int = 3
    schema_sample: int = 10_000
    schema_max_paths: int = 200
    max_depth: int = 64
    max_nodes: int = 200_000
    csv_max_rows: int = 10_000
    csv_max_cols: int = 256
    sqlite_max_bytes: int = 2 * 1024 * 1024 * 1024
    statement_timeout_s: float = 5.0
    stats_max_rows: int = 1_000_000

    @classmethod
    def from_options(cls, options: ConvertOptions) -> DataOptions:
        values: dict[str, Any] = {}
        for f in fields(cls):
            raw = options.extra.get(f"data.{f.name}")
            if raw is None or isinstance(raw, bool):
                continue
            if isinstance(raw, int | float) and raw > 0:
                values[f.name] = type(getattr(cls(), f.name))(raw)
        return cls(**values)


def prov(source: str, path: str, *, line_start: int | None = None, line_end: int | None = None) -> Provenance:
    return Provenance(source=source, path=path, line_start=line_start, line_end=line_end)


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

_BOMS: tuple[tuple[bytes, str], ...] = (
    (bytes([0xEF, 0xBB, 0xBF]), "utf-8-sig"),
    (bytes([0xFF, 0xFE, 0x00, 0x00]), "utf-32"),
    (bytes([0x00, 0x00, 0xFE, 0xFF]), "utf-32"),
    (bytes([0xFF, 0xFE]), "utf-16"),
    (bytes([0xFE, 0xFF]), "utf-16"),
)


PREFERRED_ENCODINGS = ("cp1252", "latin_1", "iso8859_15")
NEAR_CHAOS = 0.1


@dataclass(slots=True)
class Decoded:
    text: str
    encoding: str
    confidence: float
    bom: bool
    uncertain: bool


def decode_bytes(raw: bytes) -> Decoded:
    """BOM first, then strict UTF-8, then charset-normalizer on the first 1 MB, then UTF-8 with replacement
    (Part 2 13.2)."""
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            return Decoded(raw.decode(enc, errors="replace"), enc, 1.0, True, False)
    try:
        return Decoded(raw.decode("utf-8"), "utf-8", 1.0, False, False)
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    matches = list(from_bytes(raw[: 1 << 20]))
    best = matches[0] if matches else None
    if best is not None:
        # Short inputs are ambiguous between single-byte code pages; among near-equal candidates prefer the
        # Western defaults spreadsheet exports use (D: docs/decisions/P1-T05-data.md).
        near = [m for m in matches if m.chaos <= best.chaos + NEAR_CHAOS]
        best = next((m for p in PREFERRED_ENCODINGS for m in near if m.encoding == p), best)
    if best is not None and best.encoding:
        confidence = max(0.0, min(1.0, 1.0 - float(best.chaos)))
        try:
            text = raw.decode(best.encoding, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        replaced = chr(0xFFFD) in text
        return Decoded(text, best.encoding, confidence, False, confidence < 0.7 and replaced)
    text = raw.decode("utf-8", errors="replace")
    return Decoded(text, "utf-8", 0.0, False, chr(0xFFFD) in text)


def encoding_warning(d: Decoded) -> Warning | None:
    if not d.uncertain:
        return None
    return Warning(
        kind=WarningKind.ENCODING_UNCERTAIN,
        message=f"Text encoding was detected as {d.encoding}; some characters may be wrong.",
        detail={"encoding": d.encoding},
    )


def hidden_chars_warning(stats: CleanStats) -> Warning | None:
    if not stats.total:
        return None
    return Warning(
        kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
        severity="info",
        message=f"Removed {stats.total} control or invisible characters.",
        count=stats.total,
        detail={"control": stats.control, "invisible": stats.invisible, "surrogates": stats.surrogates},
    )


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------


def is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def scalar_text(value: object) -> str:
    """Display text of a scalar in JSON spelling (true/false/null); strings and RawNumbers verbatim."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        return repr(value)
    return str(value)


def to_json(value: object, *, indent: int | None = None, max_depth: int = 64) -> str:
    """Serialize parsed data back to JSON text, keeping RawNumber spellings verbatim. Containers deeper than
    `max_depth` become the string "…" so hostile nesting cannot exhaust the stack."""
    out: list[str] = []
    _emit_json(value, out, indent, 0, max_depth, set())
    return "".join(out)


def _emit_json(value: object, out: list[str], indent: int | None, level: int, max_depth: int, seen: set[int]) -> None:
    if isinstance(value, RawNumber):
        out.append(str(value))
        return
    if is_scalar(value):
        if isinstance(value, float) and value != value:  # NaN has no JSON spelling
            out.append('"NaN"')
            return
        out.append(json.dumps(value, ensure_ascii=False) if not isinstance(value, float) else repr(value))
        return
    if level >= max_depth or id(value) in seen:
        out.append(json.dumps(ELLIPSIS, ensure_ascii=False))
        return
    seen.add(id(value))
    nl = "" if indent is None else "\n" + " " * (indent * (level + 1))
    end = "" if indent is None else "\n" + " " * (indent * level)
    sep = ", " if indent is None else ","
    if isinstance(value, dict):
        if not value:
            out.append("{}")
        else:
            out.append("{")
            for i, (k, v) in enumerate(value.items()):
                out.append((sep if i else "") + nl + json.dumps(str(k), ensure_ascii=False) + ": ")
                _emit_json(v, out, indent, level + 1, max_depth, seen)
            out.append(end + "}")
    elif isinstance(value, list | tuple):
        if not value:
            out.append("[]")
        else:
            out.append("[")
            for i, v in enumerate(value):
                out.append((sep if i else "") + nl)
                _emit_json(v, out, indent, level + 1, max_depth, seen)
            out.append(end + "]")
    else:
        out.append(json.dumps(str(value), ensure_ascii=False))
    seen.discard(id(value))


@dataclass(slots=True)
class CellValue:
    text: str
    raw: str | None = None


def cell_value(value: object, stats: CleanStats, *, max_depth: int = 64) -> CellValue:
    """Display text for any parsed value: scalars verbatim, containers as compact JSON, long text cut."""
    text = scalar_text(value) if is_scalar(value) else to_json(value, max_depth=max_depth)
    return display_text(text, stats)


def display_text(text: str, stats: CleanStats) -> CellValue:
    cleaned = clean_text(text, stats)
    raw: str | None = text if cleaned != text else None
    if len(cleaned) > MAX_CELL_CHARS:
        raw = text[:MAX_RAW_CHARS]
        cleaned = cleaned[: MAX_CELL_CHARS - 1] + ELLIPSIS
    return CellValue(cleaned, raw)


# ---------------------------------------------------------------------------
# Column types
# ---------------------------------------------------------------------------

_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")
_FLOAT_COMMA = re.compile(r"^[-+]?\d+,\d+$")
_PERCENT = re.compile(r"^[-+]?\d+(\.\d+)?%$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[-+]\d{2}:?\d{2})?)?$")
_BOOL = frozenset({"true", "false"})


def text_type(value: str, *, comma_decimal: bool = False) -> ColumnType | None:
    """Type of one string value, or None when empty (empty cells never decide a column's type)."""
    s = value.strip()
    if not s:
        return None
    if _INT.match(s):
        return "int"
    if _FLOAT.match(s) or (comma_decimal and _FLOAT_COMMA.match(s)):
        return "float"
    if _PERCENT.match(s):
        return "percent"
    if _DATE.match(s):
        return "date"
    if s.lower() in _BOOL:
        return "bool"
    return "text"


def value_type(value: object, *, typed_strings: bool = False) -> ColumnType | None:
    """Type of one parsed value (JSON/YAML/TOML/SQLite). None for null. Strings are `text` unless they are ISO
    dates; with `typed_strings` (XML, where every value is text) they are typed like CSV cells."""
    if value is None:
        return None
    if isinstance(value, str) and not isinstance(value, RawNumber):
        if typed_strings:
            return text_type(value)
        return "date" if _DATE.match(value.strip()) else "text"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, RawNumber):
        return "int" if _INT.match(value) else "float"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "text"


def merge_types(types: Iterable[ColumnType | None]) -> ColumnType:
    """One column type from per-value types: a single type wins, int+float is float, anything else is text."""
    seen = {t for t in types if t is not None}
    if not seen:
        return "text"
    if len(seen) == 1:
        return next(iter(seen))
    if seen <= {"int", "float"}:
        return "float"
    return "text"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def make_table(
    header: Sequence[str],
    rows: Sequence[Sequence[CellValue]],
    provenance: Provenance,
    *,
    column_types: Sequence[ColumnType] | None = None,
    caption: str | None = None,
    attrs: dict[str, str] | None = None,
) -> Table:
    """A Table with one header row. Rows shorter than the header are padded with empty cells."""
    n_cols = len(header)
    cells: list[TableCell] = [
        TableCell(spans=[InlineSpan(text=h)], row=0, col=c, is_header=True) for c, h in enumerate(header)
    ]
    for r, row in enumerate(rows, start=1):
        for c in range(n_cols):
            v = row[c] if c < len(row) else CellValue("")
            cells.append(TableCell(spans=[InlineSpan(text=v.text)], row=r, col=c, raw_value=v.raw))
    return Table(
        cells=cells,
        n_rows=len(rows) + 1,
        n_cols=n_cols,
        header_rows=1,
        column_types=list(column_types) if column_types is not None else None,
        caption=[InlineSpan(text=caption)] if caption else None,
        provenance=provenance,
        attrs=attrs or {},
    )


def kv_table(pairs: Sequence[tuple[str, CellValue]], provenance: Provenance, *, caption: str | None = None) -> Table:
    return make_table(
        ["Key", "Value"],
        [[CellValue(k), v] for k, v in pairs],
        provenance,
        column_types=["text", "text"],
        caption=caption,
    )


def sample_indexes(n: int, opts: DataOptions) -> tuple[list[int], int]:
    """Row indexes to keep for `n` rows and how many were omitted: all rows up to max_rows, else head and tail."""
    if n <= opts.max_rows:
        return list(range(n)), 0
    head = list(range(min(opts.head_rows, n)))
    tail = list(range(max(len(head), n - opts.tail_rows), n))
    return head + tail, n - len(head) - len(tail)


def mark_sampled(table: Table, *, total: int | None, omitted: int | None, after_row: int) -> Paragraph:
    """Record a head + tail sample on `table` and return the note paragraph that follows it.

    The Table holds only real rows (no marker row, so row counts, column types and the CSV attachment stay
    clean); `attrs` carry `rows_total`, `rows_omitted` and `omitted_after_row` (1-based data row after which
    the gap falls) for renderers and the sidecar.
    """
    table.attrs = {
        **table.attrs,
        "rows_total": "" if total is None else str(total),
        "rows_omitted": "" if omitted is None else str(omitted),
        "omitted_after_row": str(after_row),
    }
    tail = table.n_rows - 1 - after_row
    if omitted is None or total is None:
        text = f"(Sample: the first {after_row:,} and the last {tail:,} rows; more rows were omitted between them.)"
    else:
        text = (
            f"(Sample: the first {after_row:,} and the last {tail:,} of {total:,} rows; "
            f"{omitted:,} rows omitted after row {after_row:,}.)"
        )
    return Paragraph(spans=[InlineSpan(text=text)], provenance=table.provenance.model_copy())


def rows_sampled_warning(where: str, total: int, omitted: int, opts: DataOptions) -> Warning:
    return Warning(
        kind=WarningKind.ROWS_SAMPLED,
        message=(
            f"{where} has {total:,} rows; showing the first {opts.head_rows} and last {opts.tail_rows} "
            f"({omitted:,} omitted). Raise data.max_rows to include more."
        ),
        count=omitted,
        detail={"rows": total, "omitted": omitted},
    )


def columns_truncated_warning(where: str, total: int, kept: int) -> Warning:
    return Warning(
        kind=WarningKind.COLUMNS_TRUNCATED,
        message=f"{where} has {total} columns; only the first {kept} are shown. Raise data.max_cols to include more.",
        count=total - kept,
        detail={"columns": total, "kept": kept},
    )
