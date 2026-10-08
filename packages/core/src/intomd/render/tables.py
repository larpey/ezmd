"""intomd.render.tables: table representations (docs/spec/part3.md section 15).

Pipe tables for small tables, key:value records for wide or long ones, minimal HTML when merged cells
carry meaning (`merged_cells=html`), sampling (first 20 + last 5 records, summary line) for very large
tables, and RFC 4180 CSV attachments at `tables/table-NN.csv`. Cell strings are never reformatted.
"""

from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass

from intomd.ir import InlineSpan, Table, WarningKind
from intomd.render.base import Attachment
from intomd.render.context import RenderContext, Unit
from intomd.render.inline import plain_spans, render_spans
from intomd.render.tokens import count_o200k

__all__ = ["parse_number", "render_table"]

_NUMBER = re.compile(r"^\(?[-+]?[$€£¥]?\s?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?%?\)?$")
_NUMERIC_TYPES = {"int", "float", "currency", "percent", "number"}


def parse_number(text: str) -> float | None:
    s = text.strip()
    if not s or not _NUMBER.match(s):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("%", "").lstrip("$€£¥").strip()
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


@dataclass(slots=True)
class _Grid:
    md: list[list[str]]
    plain: list[list[str]]
    header_rows: int
    headers: list[str]
    numeric: list[bool]
    synthesized: bool


_BR = ""


def _cell_md(ctx: RenderContext, spans: list[InlineSpan], formula: str | None) -> str:
    marked = [s.model_copy(update={"text": s.text.replace("\n", f" {_BR} ")}) if "\n" in s.text else s for s in spans]
    text = render_spans(ctx, marked).replace("|", "\\|")
    text = re.sub(rf"\s*{_BR}\s*", "<br>", text)
    if formula and ctx.profile.formulas == "inline":
        text = f"{text} (={formula.lstrip('=')})"
    return text


def _infer_header(plain: list[list[str]]) -> bool:
    if len(plain) < 2 or not all(c.strip() for c in plain[0]):
        return False
    if any(parse_number(c) is not None for c in plain[0]):
        return False
    return any(parse_number(row[c]) is not None for row in plain[1:] for c in range(len(row)))


def _build_grid(ctx: RenderContext, table: Table) -> _Grid:
    rows, cols = table.n_rows, table.n_cols
    md = [[""] * cols for _ in range(rows)]
    plain = [[""] * cols for _ in range(rows)]
    for cell in table.cells:
        m = _cell_md(ctx, cell.spans, cell.formula)
        p = plain_spans(ctx, cell.spans)
        for r in range(cell.row, cell.row + cell.row_span):
            for c in range(cell.col, cell.col + cell.col_span):
                md[r][c], plain[r][c] = m, p
    header_rows = table.header_rows
    if header_rows == 0:
        lead = 0
        for r in range(rows):
            row_cells = [c for c in table.cells if c.row == r]
            if row_cells and all(c.is_header for c in row_cells):
                lead += 1
            else:
                break
        header_rows = lead or (1 if _infer_header(plain) else 0)
    header_rows = min(header_rows, rows)
    synthesized = header_rows == 0
    headers: list[str] = []
    for c in range(cols):
        parts: list[str] = []
        for r in range(header_rows):
            value = plain[r][c]
            if value and (not parts or parts[-1] != value):
                parts.append(value)
        name = " / ".join(parts)
        if not name or name in headers:
            name = f"col_{c + 1}"
        headers.append(name)
    types = [t.strip().lower() for t in table.attrs.get("column_types", "").split(",") if t.strip()]
    numeric: list[bool] = []
    for c in range(cols):
        if len(types) == cols:
            numeric.append(types[c] in _NUMERIC_TYPES)
            continue
        values = [plain[r][c] for r in range(header_rows, rows) if plain[r][c].strip()]
        numeric.append(c > 0 and bool(values) and all(parse_number(v) is not None for v in values))
    return _Grid(md, plain, header_rows, headers, numeric, synthesized)


def _csv(grid: _Grid) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(grid.headers)
    for row in grid.plain[grid.header_rows :]:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _kv_line(grid: _Grid, row: list[str]) -> str:
    pairs = [f"{grid.headers[c]}: {v.replace('<br>', ' ')}" for c, v in enumerate(row) if v.strip()]
    return "- " + " | ".join(pairs) if pairs else "- (empty row)"


def _pipe(grid: _Grid) -> tuple[list[str], list[str]]:
    header = "| " + " | ".join(h.replace("|", "\\|") for h in grid.headers) + " |"
    delim = "|" + "|".join("---:" if n else "---" for n in grid.numeric) + "|"
    rows = ["| " + " | ".join(row) + " |" for row in grid.md[grid.header_rows :]]
    return [header, delim], rows


def _html(ctx: RenderContext, table: Table, header_rows: int) -> str:
    lines = ["<table>"]
    by_row: dict[int, list[str]] = {}
    for cell in sorted(table.cells, key=lambda c: (c.row, c.col)):
        tag = "th" if cell.row < header_rows or cell.is_header else "td"
        attrs = ""
        if cell.col_span > 1:
            attrs += f' colspan="{cell.col_span}"'
        if cell.row_span > 1:
            attrs += f' rowspan="{cell.row_span}"'
        text = html.escape(plain_spans(ctx, cell.spans), quote=False)
        by_row.setdefault(cell.row, []).append(f"<{tag}{attrs}>{text}</{tag}>")
    sections = [("thead", range(header_rows)), ("tbody", range(header_rows, table.n_rows))]
    for tag, rng in sections:
        rows = [f"<tr>{''.join(by_row.get(r, []))}</tr>" for r in rng]
        if rows:
            lines.extend([f"<{tag}>", *rows, f"</{tag}>"])
    lines.append("</table>")
    return "\n".join(lines)


def _fmt_num(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}" if decimals else f"{round(value):,}"


def _summary(grid: _Grid) -> str | None:
    data = grid.plain[grid.header_rows :]
    parts = [f"{len(data):,} rows"]
    for c, is_num in enumerate(grid.numeric):
        if not is_num:
            continue
        raw = [row[c] for row in data if row[c].strip()]
        values = [v for v in (parse_number(x) for x in raw) if v is not None]
        if not values:
            continue
        decimals = max((len(x.split(".")[1].rstrip("%)")) if "." in x else 0) for x in raw)
        parts.append(
            f"{grid.headers[c]} min {_fmt_num(min(values), decimals)}, max {_fmt_num(max(values), decimals)}, "
            f"sum {_fmt_num(sum(values), decimals)}"
        )
    return "Summary: " + "; ".join(parts) if len(parts) > 1 else None


def _representation(ctx: RenderContext, table: Table, n_data: int) -> str:
    rules = ctx.profile.tables
    cap = rules.max_pipe_rows
    if table.has_merged_cells and rules.merged_cells == "html":
        return "html"
    if n_data > rules.sample_threshold_rows or (ctx.profile.name == "compact" and cap is not None and n_data > 5 * cap):
        return "sampled"
    if table.n_cols > rules.max_pipe_columns or (cap is not None and n_data > cap):
        return "kv"
    return "pipe"


def render_table(ctx: RenderContext, table: Table, caption: list[InlineSpan] | None = None) -> Unit:
    ctx.table_count += 1
    number = ctx.table_count
    grid = _build_grid(ctx, table)
    n_data = table.n_rows - grid.header_rows
    rep = _representation(ctx, table, n_data)
    rules = ctx.profile.tables
    if table.has_merged_cells and rep != "html":
        ctx.warn(
            WarningKind.TABLE_MERGED_CELLS_FLATTENED,
            f"Merged cells in table {number} were flattened.",
            block_id=table.id,
        )
    if any(c.formula for c in table.cells):
        ctx.warn(WarningKind.FORMULAS_PRESENT, "The source contains spreadsheet formulas; cached values are shown.")
    path = f"tables/table-{number:02d}.csv"
    wants_csv = table.n_cols > 6 or n_data > 50 or rep == "sampled" or rules.csv_sidecar
    if wants_csv:
        ctx.attachments.append(Attachment(path=path, mime="text/csv", data=_csv(grid)))
    cap_spans = table.caption or caption
    cap_text = render_spans(ctx, cap_spans) if cap_spans else ""
    line = f"**Table {number}: {cap_text}**" if cap_text else f"**Table {number}**"
    if rep in ("kv", "sampled"):
        line += f" ({table.n_cols} columns, {n_data:,} rows; full data: {path})" if wants_csv else ""
    elif wants_csv:
        line += f" ({path})"
    head = [line]
    if grid.synthesized:
        ctx.header_synthesized += 1
        head.append("<!-- intomd: header synthesized -->")
    if rep in ("kv", "sampled") or table.n_cols > 4:
        head.append("Columns: " + ", ".join(grid.headers))
    head_text = "\n".join(head)
    rows: list[str] | None
    if rep == "pipe":
        top, rows = _pipe(grid)
        body = "\n".join([*top, *rows])
        head_text = head_text + "\n\n" + "\n".join(top)
        text = "\n".join(head) + "\n\n" + body
    elif rep == "html":
        rows = None
        text = head_text + "\n\n" + _html(ctx, table, grid.header_rows)
    elif rep == "kv":
        rows = [_kv_line(grid, row) for row in grid.md[grid.header_rows :]]
        text = head_text + "\n\n" + "\n".join(rows)
    else:
        data = grid.md[grid.header_rows :]
        h, t = rules.sample_head_rows, rules.sample_tail_rows
        omitted = len(data) - h - t
        note = (
            f"({omitted:,} rows omitted; full data in {path})"
            if ctx.profile.name == "compact"
            else f"<!-- intomd: {omitted:,} rows omitted; full data in {path} -->"
        )
        rows = None
        lines = [*(_kv_line(grid, r) for r in data[:h]), note, *(_kv_line(grid, r) for r in data[-t:])]
        summary = _summary(grid)
        text = head_text + "\n\n" + "\n".join(lines) + (f"\n\n{summary}" if summary else "")
        ctx.warn(
            WarningKind.TABLE_SAMPLED,
            f"Table {number} was sampled ({omitted} of {len(data)} rows omitted).",
            block_id=table.id,
            rows=len(data),
            omitted=omitted,
        )
        ctx.truncated = True
    fn_refs = ctx.take_refs()
    entry: dict[str, object] = {
        "number": number,
        "block_id": table.id,
        "representation": rep,
        "rows": n_data,
        "columns": table.n_cols,
        "header": grid.headers,
        "column_types": ["number" if n else "text" for n in grid.numeric],
        "csv": path if wants_csv else None,
        "tokens": count_o200k(text),
        "formulas": [{"row": c.row, "col": c.col, "formula": c.formula} for c in table.cells if c.formula],
        "page": table.provenance.source_page,
    }
    key = ("tables", ctx.side("tables", entry))
    return Unit(
        text=text,
        kind="table",
        block_ids=[table.id],
        page=table.provenance.source_page,
        fn_refs=fn_refs,
        table_head=head_text,
        table_rows=rows,
        sidecar_key=key,
    )
