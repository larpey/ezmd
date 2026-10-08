"""XLSX cell helpers: value formatting, column typing, header detection, region splitting (Part 2 2c 25-28)."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from ezmd.ir import ColumnType
from ezmd_converters.office.numfmt import format_number

ERRORS = frozenset(
    {"#REF!", "#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#VALUE!", "#SPILL!", "#CALC!", "#GETTING_DATA"}
)
_CURRENCY = re.compile(r'[$€£¥₹]|\[\$[^\]]*\]|"[$€£¥]"')
_DECIMALS = re.compile(r"0\.(0+)")
DATE_HEADER = re.compile(r"(date|day|time|created|updated|modified|dob|birth|when|period|month|year)", re.I)


@dataclass(slots=True)
class XCell:
    value: object
    number_format: str
    data_type: str
    bold: bool
    formula: str | None = None
    display: str | None = None
    """Text the source application already rendered for this cell (ODS `text:p`); wins over formatting."""

    @property
    def empty(self) -> bool:
        return (self.value is None or self.value == "") and not self.formula


def is_percent(fmt: str) -> bool:
    return "%" in fmt and not fmt.startswith("@")


def is_currency(fmt: str) -> bool:
    return bool(_CURRENCY.search(fmt or ""))


def fmt_value(c: XCell) -> tuple[str, bool]:
    """Display text for a cell's cached value and whether it is an error value. Numbers are shown with their
    number format applied (as Excel displays them); the unformatted value stays in TableCell.raw_value."""
    v = c.value
    if v is None:
        return "", False
    if isinstance(v, bool):
        return ("TRUE" if v else "FALSE"), False
    if isinstance(v, dt.datetime):
        if v.time() == dt.time(0, 0):
            return v.date().isoformat(), False
        return v.isoformat(), False
    if isinstance(v, dt.date | dt.time):
        return v.isoformat(), False
    if isinstance(v, dt.timedelta):
        return str(v), False
    if isinstance(v, int | float) and c.display:
        return c.display, False
    if isinstance(v, int | float):
        if is_percent(c.number_format):
            m = _DECIMALS.search(c.number_format)
            places = len(m.group(1)) if m else 0
            return f"{v * 100:.{places}f}%", False
        shown = format_number(float(v), c.number_format)
        if shown is not None:
            return shown, False
        if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
            return str(int(v)), False
        return repr(v) if isinstance(v, float) else str(v), False
    s = str(v)
    return s, c.data_type == "e" or s in ERRORS


def kind_of(c: XCell) -> str | None:
    v = c.value
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, dt.datetime | dt.date):
        return "date"
    if isinstance(v, int | float):
        if is_percent(c.number_format):
            return "percent"
        if is_currency(c.number_format):
            return "currency"
        return "int" if isinstance(v, int) or float(v).is_integer() else "float"
    if c.data_type == "e" or str(v) in ERRORS:
        return "error"
    return "text"


def column_types(rows: list[list[XCell | None]], n_cols: int) -> list[ColumnType]:
    out: list[ColumnType] = []
    for col in range(n_cols):
        present = [r[col] for r in rows if col < len(r)]
        kinds = {k for c in present if c is not None and (k := kind_of(c)) not in (None, "error")}
        if not kinds:
            out.append("text")
        elif len(kinds) == 1:
            out.append(kinds.pop())  # type: ignore[arg-type]
        elif kinds <= {"int", "float", "currency", "percent"}:
            for k in ("currency", "percent", "float"):
                if k in kinds:
                    out.append(k)  # type: ignore[arg-type]
                    break
        else:
            out.append("text")
    return out


def header_rows(rows: list[list[XCell | None]], bold_known: bool) -> int:
    """1 when the first row is all strings and the next has a number/date/bool (or the first row is bold),
    2 when two string rows precede such a data row, else 0 (the renderer synthesizes A, B, C)."""

    def strings(r: list[XCell | None]) -> bool:
        vals = [c for c in r if c is not None and not c.empty]
        return bool(vals) and all(isinstance(c.value, str) and not c.formula for c in vals)

    def typed(r: list[XCell | None]) -> bool:
        return any(c is not None and kind_of(c) in ("int", "float", "date", "bool", "percent", "currency") for c in r)

    if not rows or len(rows) < 2:
        return 0
    if strings(rows[0]) and typed(rows[1]):
        return 1
    if len(rows) > 2 and strings(rows[0]) and strings(rows[1]) and typed(rows[2]):
        return 2
    if bold_known:
        first = [c for c in rows[0] if c is not None and not c.empty]
        if first and all(c.bold for c in first):
            return 1
    return 0


def regions(grid: list[list[XCell | None]]) -> list[tuple[int, int, int, int]]:
    """Contiguous data regions split on two or more fully empty rows or columns.
    Returns (row0, col0, row1, col1) inclusive, 0-based, in reading order."""
    nonempty_rows = [any(c is not None and not c.empty for c in r) for r in grid]
    out: list[tuple[int, int, int, int]] = []
    for r0, r1 in _bands(nonempty_rows):
        width = max((len(grid[r]) for r in range(r0, r1 + 1)), default=0)
        cols = [
            any(c < len(grid[r]) and grid[r][c] is not None and not grid[r][c].empty for r in range(r0, r1 + 1))  # type: ignore[union-attr]
            for c in range(width)
        ]
        for c0, c1 in _bands(cols):
            rows_used = [
                r
                for r in range(r0, r1 + 1)
                if any(c < len(grid[r]) and grid[r][c] is not None and not grid[r][c].empty for c in range(c0, c1 + 1))  # type: ignore[union-attr]
            ]
            if rows_used:
                out.append((rows_used[0], c0, rows_used[-1], c1))
    return out


def _bands(flags: list[bool]) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    last = -1
    gap = 0
    for i, f in enumerate(flags):
        if f:
            if start is None:
                start = i
            elif gap >= 2:
                bands.append((start, last))
                start = i
            last = i
            gap = 0
        else:
            gap += 1
    if start is not None:
        bands.append((start, last))
    return bands


def col_letter(n: int) -> str:
    """1-based column number to letters."""
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def a1(row: int, col: int) -> str:
    """0-based row/col to A1."""
    return f"{col_letter(col + 1)}{row + 1}"
