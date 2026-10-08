"""Financial-table cleanup for EDGAR HTML tables.

Filing tables are laid out for print: spacer columns with no text, the currency sign in its own cell
(`$` | `1,234`), and the closing parenthesis of a negative number or a percent sign in the next cell
(`(56` | `)`). This pass drops empty rows and columns, then folds `$` into the cell on its right and
`)`/`%` into the cell on its left, so every number survives as one exact string (part2 12g: statement
cells must be exact). Spans are recomputed over the kept columns; the input Table is not modified.
"""

from __future__ import annotations

from ezmd.ir import InlineSpan, InlineStyle, Paragraph, Table, TableCell, spans_text

_PREFIXES = frozenset({"$", "US$", "€", "£", "¥"})
_SUFFIXES = frozenset({")", "%", ")%", "%)"})


def _text(cell: TableCell) -> str:
    return spans_text(cell.spans).strip()


def _covers(cell: TableCell, axis: str) -> range:
    if axis == "col":
        return range(cell.col, cell.col + cell.col_span)
    return range(cell.row, cell.row + cell.row_span)


def _droppable(t: Table, axis: str) -> set[int]:
    """Columns (or rows) no text-bearing cell needs: every single-span cell there is empty, and each
    text-bearing spanning cell keeps at least one of its columns."""
    size = t.n_cols if axis == "col" else t.n_rows
    span = "col_span" if axis == "col" else "row_span"
    cand = set(range(size))
    for c in t.cells:
        if getattr(c, span) == 1 and _text(c):
            cand.difference_update(_covers(c, axis))
    for c in t.cells:
        cov = set(_covers(c, axis))
        if _text(c) and cov <= cand:
            cand.discard(min(cov))
    return cand


def _rebuild(t: Table, drop_cols: set[int], drop_rows: set[int], texts: dict[int, list[InlineSpan]]) -> Table:
    col_map = {c: i for i, c in enumerate(c for c in range(t.n_cols) if c not in drop_cols)}
    row_map = {r: i for i, r in enumerate(r for r in range(t.n_rows) if r not in drop_rows)}
    cells: list[TableCell] = []
    for idx, c in enumerate(t.cells):
        cols = [col_map[k] for k in _covers(c, "col") if k in col_map]
        rows = [row_map[k] for k in _covers(c, "row") if k in row_map]
        if not cols or not rows:
            continue
        cells.append(
            c.model_copy(
                update={
                    "spans": texts.get(idx, c.spans),
                    "col": cols[0],
                    "col_span": len(cols),
                    "row": rows[0],
                    "row_span": len(rows),
                }
            )
        )
    header_rows = sum(1 for r in range(t.header_rows) if r in row_map)
    merged = any(c.col_span > 1 or c.row_span > 1 for c in cells)
    return Table(
        cells=cells,
        n_rows=len(row_map),
        n_cols=len(col_map),
        caption=t.caption,
        header_rows=header_rows,
        has_merged_cells=merged,
        provenance=t.provenance,
        attrs=t.attrs,
    )


def _fold(t: Table) -> Table:
    """Fold currency-prefix columns right and suffix columns left."""
    anchors = {(c.row, c.col): i for i, c in enumerate(t.cells) if c.col_span == 1 and c.row_span == 1}
    texts: dict[int, list[InlineSpan]] = {}
    drop: set[int] = set()
    for col in range(t.n_cols):
        vals = [(i, _text(c)) for i, c in enumerate(t.cells) if c.col == col and c.col_span == 1]
        filled = [(i, v) for i, v in vals if v]
        if not filled:
            continue
        if all(v in _PREFIXES for _, v in filled) and col + 1 < t.n_cols:
            step = 1
        elif all(v in _SUFFIXES for _, v in filled) and col > 0:
            step = -1
        else:
            continue
        if col + step in drop:
            continue
        targets = [anchors.get((t.cells[i].row, col + step)) for i, _ in filled]
        if any(j is None for j in targets):
            continue
        for (_i, v), j in zip(filled, targets, strict=True):
            assert j is not None
            base = texts.get(j, t.cells[j].spans)
            joined = (v + spans_text(base).strip()) if step == 1 else (spans_text(base).strip() + v)
            texts[j] = [InlineSpan(text=joined)]
        drop.add(col)
    if not drop:
        return t
    return _rebuild(t, drop, set(), texts)


def _bold_header_rows(t: Table) -> int:
    """Leading rows whose text is all bold (filing agents style column headers instead of using `<th>`)."""
    n = 0
    for r in range(t.n_rows):
        filled = [c for c in t.cells if c.row == r and _text(c)]
        if not filled:
            break
        if not all(all(InlineStyle.BOLD in s.styles for s in c.spans if s.text.strip()) for c in filled):
            break
        n += 1
    return n if n < t.n_rows else 0


def tidy_table(t: Table) -> Table | Paragraph | None:
    """Clean a filing table. A table reduced to one cell becomes a Paragraph; an empty one disappears."""
    if not any(_text(c) for c in t.cells):
        return None
    out = _rebuild(t, _droppable(t, "col"), _droppable(t, "row"), {})
    out = _fold(out)
    if out.n_cols == 1 and out.n_rows == 1 and out.cells:
        return Paragraph(spans=out.cells[0].spans, provenance=t.provenance)
    if out.header_rows == 0:
        out = out.model_copy(update={"header_rows": _bold_header_rows(out)})
    return out
