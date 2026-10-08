"""data.parquet: Apache Parquet metadata and samples via pyarrow (docs/spec/part2.md section 10, ColumnarConverter).

Needs the `data` extra (`pip install 'intomd[data]'`, pyarrow, Apache-2.0); without it the converter is
listed as unavailable. Reads metadata through `pyarrow.parquet.ParquetFile` and never loads the whole table:
schema, row groups, compression and created-by come from the footer; the statistics table aggregates
row-group statistics; sample rows read only the first and last row groups, and only up to `max_cols`
columns. Nested values render as compact JSON, decimals verbatim, timestamps in ISO 8601 with their zone.
Arrow IPC, Feather, ORC and partitioned datasets are not handled yet.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
from typing import Any

from intomd.core.textclean import CleanStats
from intomd.inputs import InputRef
from intomd.ir import ColumnType, Document, Heading, InlineSpan, Warning
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.data._base import DB_LIMITS, finish, mime_of, new_document, suffix_of, summary
from intomd_converters.data._common import (
    CellValue,
    DataOptions,
    columns_truncated_warning,
    display_text,
    make_table,
    mark_sampled,
    prov,
    rows_sampled_warning,
    scalar_text,
    to_json,
)

PARQUET_MIMES = ("application/vnd.apache.parquet", "application/x-parquet")


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, bytes):
        return f"<binary {len(value)} bytes>"
    return value


def _utc_text(value: Any) -> Any:
    """ISO text for a naive datetime that holds a UTC instant (zone-aware columns are cast to naive UTC)."""
    return value.isoformat() + "Z" if isinstance(value, dt.datetime) else value


def _pylist(data: Any) -> list[dict[str, Any]]:
    """Rows as dicts. Zone-aware timestamp columns are cast to naive UTC first and rendered with a `Z`
    suffix, so no time zone database (tzdata, absent on Windows) is needed."""
    import pyarrow as pa  # type: ignore[import-not-found,import-untyped,unused-ignore]
    import pyarrow.types as pt  # type: ignore[import-not-found,import-untyped,unused-ignore]

    table = data if isinstance(data, pa.Table) else pa.Table.from_batches([data])
    zoned = [f.name for f in table.schema if pt.is_timestamp(f.type) and f.type.tz]
    if zoned:
        fields = [pa.field(f.name, pa.timestamp(f.type.unit)) if f.name in zoned else f for f in table.schema]
        table = table.cast(pa.schema(fields))
    rows: list[dict[str, Any]] = table.to_pylist()
    if zoned:
        rows = [{k: _utc_text(v) if k in zoned else v for k, v in r.items()} for r in rows]
    return rows


def _stat_value(st: Any, which: str) -> Any:
    """Row-group statistic as a comparable value. Zone-aware timestamps (which pyarrow cannot convert without
    tzdata, absent on Windows) are rebuilt from the raw integer as naive UTC datetimes."""
    try:
        return getattr(st, which)
    except Exception:
        raw = getattr(st, f"{which}_raw")
        try:
            unit = _MICROS_PER_UNIT.get(json.loads(st.logical_type.to_json()).get("timeUnit", ""))
        except (ValueError, AttributeError):
            unit = None
        if isinstance(raw, int) and unit is not None:
            return dt.datetime(1970, 1, 1) + dt.timedelta(microseconds=raw * unit)
        return raw


_MICROS_PER_UNIT = {"milliseconds": 1000.0, "microseconds": 1.0, "nanoseconds": 0.001}


def _stat_text(value: Any) -> str:
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        return value.isoformat() + "Z"
    return scalar_text(_plain(value))


def _cell(value: Any, stats: CleanStats) -> CellValue:
    v = _plain(value)
    if v is None:
        return CellValue("null")
    if isinstance(v, dict | list):
        return display_text(to_json(v), stats)
    return display_text(scalar_text(v), stats)


def _column_type(arrow_type: Any) -> ColumnType:
    import pyarrow.types as pt  # type: ignore[import-not-found,import-untyped,unused-ignore]

    if pt.is_boolean(arrow_type):
        return "bool"
    if pt.is_integer(arrow_type):
        return "int"
    if pt.is_floating(arrow_type) or pt.is_decimal(arrow_type):
        return "float"
    if pt.is_timestamp(arrow_type) or pt.is_date(arrow_type):
        return "date"
    return "text"


class ParquetConverter:
    id = "data.parquet"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ("data",)
    mimes: tuple[str, ...] = PARQUET_MIMES
    limits = DB_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        d = ref.detected
        if d is None:
            return 0.0
        if d.mime in PARQUET_MIMES:
            return 1.0
        if suffix_of(ref) == ".parquet" and mime_of(ref) == "application/octet-stream":
            return 0.3
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        import pyarrow as pa  # type: ignore[import-not-found,import-untyped,unused-ignore]
        import pyarrow.parquet as pq  # type: ignore[import-not-found,import-untyped,unused-ignore]

        opts = DataOptions.from_options(options)
        try:
            pf = pq.ParquetFile(ref.path())
        except (pa.ArrowException, OSError) as e:
            raise ConversionError(f"cannot read Parquet: {e}", user_message="This Parquet file is unreadable.") from e
        with pf:
            return self._build(ref, pf, opts, options)

    def _build(self, ref: InputRef, pf: Any, opts: DataOptions, options: ConvertOptions) -> Document:
        md = pf.metadata
        schema = pf.schema_arrow
        stats = CleanStats()
        warnings: list[Warning] = []
        source = ref.display
        doc = new_document(ref)
        compression = sorted(
            {md.row_group(i).column(j).compression for i in range(md.num_row_groups) for j in range(md.num_columns)}
        )
        doc.metadata.extra.update(
            {
                "format": "Parquet",
                "rows": md.num_rows,
                "row_groups": md.num_row_groups,
                "columns": len(schema),
                "created_by": str(md.created_by or ""),
            }
        )
        summary(
            doc,
            f"Parquet file with {md.num_rows:,} rows, {len(schema)} columns and {md.num_row_groups} row "
            f"group(s); compression {', '.join(compression) or 'none'}; written by {md.created_by or 'unknown'}.",
        )
        doc.blocks.append(Heading(level=2, spans=[InlineSpan(text="Schema")], provenance=prov(source, "/schema")))
        doc.blocks.append(
            make_table(
                ["Column", "Type", "Nullable"],
                [
                    [
                        display_text(f.name, stats),
                        display_text(str(f.type), stats),
                        CellValue("yes" if f.nullable else "no"),
                    ]
                    for f in schema
                ],
                prov(source, "/schema"),
                column_types=["text", "text", "text"],
            )
        )
        self._statistics(doc, md, source, stats)
        names = [f.name for f in schema]
        if len(names) > opts.max_cols:
            warnings.append(columns_truncated_warning("The Parquet file", len(names), opts.max_cols))
            names = names[: opts.max_cols]
        options.ctx.check_deadline()
        total = md.num_rows
        sampled = total > opts.head_rows + opts.tail_rows
        head = self._head(pf, names, opts.head_rows if sampled else total)
        tail = self._tail(pf, md.num_row_groups, names, opts.tail_rows) if sampled else []
        doc.blocks.append(Heading(level=2, spans=[InlineSpan(text="Sample rows")], provenance=prov(source, "/sample")))
        rows = [[_cell(r.get(n), stats) for n in names] for r in [*head, *tail]]
        types = [_column_type(schema.field(n).type) for n in names]
        table = make_table(names, rows, prov(source, f"{source}:0:0"), column_types=types)
        doc.blocks.append(table)
        if sampled:
            omitted = total - len(head) - len(tail)
            doc.blocks.append(mark_sampled(table, total=total, omitted=omitted, after_row=len(head)))
            warnings.append(rows_sampled_warning("The Parquet file", total, omitted, opts))
        return finish(doc, stats, warnings)

    @staticmethod
    def _head(pf: Any, names: list[str], n: int) -> list[dict[str, Any]]:
        """The first `n` rows, reading batches in file order only until `n` rows are collected."""
        out: list[dict[str, Any]] = []
        if n <= 0:
            return out
        for batch in pf.iter_batches(batch_size=n, columns=names):
            out.extend(_pylist(batch))
            if len(out) >= n:
                break
        return out[:n]

    @staticmethod
    def _tail(pf: Any, groups: int, names: list[str], n: int) -> list[dict[str, Any]]:
        """The last `n` rows, reading row groups from the end only until `n` rows are collected."""
        out: list[dict[str, Any]] = []
        g = groups - 1
        while len(out) < n and g >= 0:
            out = _pylist(pf.read_row_group(g, columns=names)) + out
            g -= 1
        return out[-n:] if n else []

    @staticmethod
    def _statistics(doc: Document, md: Any, source: str, stats: CleanStats) -> None:
        rows: list[list[CellValue]] = []
        for j in range(md.num_columns):
            mins: list[Any] = []
            maxs: list[Any] = []
            nulls = 0
            known = False
            for i in range(md.num_row_groups):
                col = md.row_group(i).column(j)
                st = col.statistics
                if st is None:
                    continue
                known = True
                if st.has_null_count:
                    nulls += st.null_count
                if st.has_min_max:
                    mins.append(_stat_value(st, "min"))
                    maxs.append(_stat_value(st, "max"))
            if not known:
                continue
            path = md.row_group(0).column(j).path_in_schema
            try:
                lo, hi = (_stat_text(min(mins)), _stat_text(max(maxs))) if mins else ("", "")
            except TypeError:
                lo, hi = "", ""
            rows.append(
                [display_text(path, stats), display_text(lo, stats), display_text(hi, stats), CellValue(str(nulls))]
            )
        if not rows:
            return
        doc.blocks.append(
            Heading(level=2, spans=[InlineSpan(text="Statistics")], provenance=prov(source, "/statistics"))
        )
        doc.blocks.append(
            make_table(
                ["Column", "Min", "Max", "Nulls"],
                rows,
                prov(source, "/statistics"),
                column_types=["text", "text", "text", "int"],
            )
        )
