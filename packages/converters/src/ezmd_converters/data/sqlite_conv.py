"""data.sqlite: SQLite databases via stdlib sqlite3, read-only (docs/spec/part2.md section 10, SqliteConverter).

The input is copied to a private temp file and opened as `file:...?mode=ro&immutable=1` with
`PRAGMA query_only`, `trusted_schema=OFF` and the defensive flag, so neither the original nor the copy
can be written and schema-defined functions cannot run. A progress handler enforces a per-statement
timeout (`COUNT(*)` on a huge table falls back to `max(rowid)` as an estimate) and the conversion deadline.
A header that is not `SQLite format 3` yields `sqlite_encrypted` (SQLCipher and other encrypted files).

Output: H1 file name, H2 Tables with a summary table (name, rows, columns), then per table an H3 with the
column table (name, type, not null, default, primary key, references), the index list and an H4 Sample
with the first `head_rows` and last `tail_rows` rows (all rows when they fit). Views and triggers get their
SQL as code. BLOBs render as `<blob N bytes>`.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from ezmd.context import ConvertContext
from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef
from ezmd.ir import (
    CodeBlock,
    ColumnType,
    Document,
    Heading,
    InlineSpan,
    ListBlock,
    ListItem,
    Paragraph,
    Warning,
    WarningKind,
)
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.data._base import DB_LIMITS, finish, mime_of, new_document, suffix_of, summary
from ezmd_converters.data._common import (
    CellValue,
    DataOptions,
    columns_truncated_warning,
    display_text,
    make_table,
    mark_sampled,
    merge_types,
    prov,
    rows_sampled_warning,
    scalar_text,
    value_type,
)

SQLITE_MIMES = ("application/vnd.sqlite3", "application/x-sqlite3")
SQLITE_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".db3")
MAGIC = b"SQLite format 3" + bytes([0])


class _Interrupted(Exception):
    pass


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class _Guard:
    """Progress handler: abort a statement after `statement_s` seconds or once the conversion deadline passes."""

    def __init__(self, ctx: ConvertContext, statement_s: float) -> None:
        self.ctx = ctx
        self.statement_s = statement_s
        self.started = time.monotonic()

    def reset(self) -> None:
        self.started = time.monotonic()

    def __call__(self) -> int:
        if time.monotonic() - self.started > self.statement_s:
            return 1
        left = self.ctx.remaining()
        return 1 if left is not None and left <= 0 else 0


def _open(path: Path, guard: _Guard) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True, check_same_thread=False)
    defensive = getattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE", None)
    if defensive is not None and hasattr(con, "setconfig"):
        con.setconfig(defensive, True)
    con.execute("PRAGMA query_only=1")
    con.execute("PRAGMA trusted_schema=OFF")
    con.set_progress_handler(guard, 10_000)
    con.text_factory = lambda b: b.decode("utf-8", errors="replace")
    return con


def _cell(value: Any, stats: CleanStats) -> CellValue:
    if isinstance(value, bytes | bytearray | memoryview):
        return CellValue(f"<blob {len(bytes(value))} bytes>")
    if value is None:
        return CellValue("NULL")
    return display_text(scalar_text(value), stats)


def _affinity(declared: str) -> ColumnType:
    t = declared.upper()
    if "INT" in t:
        return "int"
    if any(k in t for k in ("REAL", "FLOA", "DOUB", "NUMERIC", "DECIMAL")):
        return "float"
    if "BOOL" in t:
        return "bool"
    return "text"


class SqliteConverter:
    id = "data.sqlite"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = SQLITE_MIMES
    limits = DB_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        d = ref.detected
        if d is None:
            return 0.0
        if d.mime in SQLITE_MIMES:
            return 1.0
        if suffix_of(ref) in SQLITE_SUFFIXES and mime_of(ref) == "application/octet-stream":
            return 0.3
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = DataOptions.from_options(options)
        if ref.head(16) != MAGIC:
            doc = new_document(ref)
            doc.blocks.clear()
            doc.warnings.append(
                Warning(
                    kind=WarningKind.SQLITE_ENCRYPTED,
                    message="The file does not start with the SQLite header; it is encrypted (for example "
                    "SQLCipher) or not a SQLite database.",
                )
            )
            return doc.finalize()
        size = ref.size()
        if size > opts.sqlite_max_bytes:
            raise ConversionError(
                f"SQLite input is {size} bytes, over the {opts.sqlite_max_bytes} byte cap",
                user_message="This database is larger than the SQLite size limit.",
                retryable_with_fallback=False,
            )
        with tempfile.TemporaryDirectory(prefix="ezmd-sqlite-") as tmp:
            copy = Path(tmp) / "db.sqlite"
            shutil.copyfile(ref.path(), copy)
            guard = _Guard(options.ctx, opts.statement_timeout_s)
            try:
                con = _open(copy, guard)
            except sqlite3.Error as e:
                raise ConversionError(
                    f"cannot open SQLite: {e}", user_message="This database could not be opened."
                ) from e
            try:
                return _Builder(ref, opts, options, con, guard).build()
            except sqlite3.DatabaseError as e:
                raise ConversionError(
                    f"SQLite read failed: {e}", user_message="This database is corrupt or unreadable."
                ) from e
            finally:
                con.close()


class _Builder:
    def __init__(
        self, ref: InputRef, opts: DataOptions, options: ConvertOptions, con: sqlite3.Connection, guard: _Guard
    ) -> None:
        self.ref = ref
        self.source = ref.display
        self.opts = opts
        self.ctx = options.ctx
        self.con = con
        self.guard = guard
        self.stats = CleanStats()
        self.warnings: list[Warning] = []
        self.doc = new_document(ref)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        self.ctx.check_deadline()
        self.guard.reset()
        try:
            return list(self.con.execute(sql, params).fetchall())
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e):
                self.ctx.check_deadline()
                raise _Interrupted from e
            raise

    def build(self) -> Document:
        master = self.query("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY rowid")
        tables = [r for r in master if r[0] == "table" and not str(r[1]).startswith("sqlite_")]
        views = [r for r in master if r[0] == "view"]
        triggers = [r for r in master if r[0] == "trigger"]
        indexes = [r for r in master if r[0] == "index"]
        doc = self.doc
        doc.metadata.extra.update({"format": "SQLite", "tables": len(tables), "views": len(views)})
        summary(
            doc,
            f"SQLite database with {len(tables)} table(s), {len(views)} view(s), "
            f"{len(indexes)} index(es) and {len(triggers)} trigger(s).",
        )
        info = [(str(t[1]), self.columns(str(t[1]))) for t in tables]
        counts = [self.count(name) for name, _ in info]
        sizes = self.sizes()
        self.heading(2, "Tables", "/")
        header = ["Table", "Rows", "Columns"]
        types: list[ColumnType] = ["text", "int" if all(c.isdigit() for c in counts) else "text", "int"]
        rows = [
            [CellValue(n), CellValue(c), CellValue(str(len(cols)))] for (n, cols), c in zip(info, counts, strict=True)
        ]
        if sizes:  # dbstat is optional in SQLite builds; the column is left out when it is missing
            header.append("Size (bytes)")
            types.append("int")
            for row, (n, _cols) in zip(rows, info, strict=True):
                row.append(CellValue(sizes.get(n, "")))
        doc.blocks.append(make_table(header, rows, prov(self.source, "/"), column_types=types))
        for i, (name, cols) in enumerate(info):
            self.ctx.progress("tables", i / max(1, len(info)), name)
            self.table(name, cols, counts[i], [r for r in indexes if r[2] == name])
        self.code_section("Views", views)
        self.code_section("Triggers", triggers)
        return finish(doc, self.stats, self.warnings)

    def heading(self, level: int, text: str, path: str) -> None:
        self.doc.blocks.append(
            Heading(
                level=level, spans=[InlineSpan(text=clean_text(text, self.stats))], provenance=prov(self.source, path)
            )
        )

    def note(self, text: str, path: str) -> None:
        self.doc.blocks.append(Paragraph(spans=[InlineSpan(text=text)], provenance=prov(self.source, path)))

    def columns(self, table: str) -> list[tuple[Any, ...]]:
        return self.query(f"PRAGMA table_info({quote_ident(table)})")

    def count(self, table: str) -> str:
        try:
            return str(self.query(f"SELECT COUNT(*) FROM {quote_ident(table)}")[0][0])  # noqa: S608 quoted identifier
        except _Interrupted:
            try:
                top = self.query(f"SELECT max(rowid) FROM {quote_ident(table)}")[0][0]  # noqa: S608 quoted identifier
                return f">= {top} (estimated)" if top is not None else "unknown"
            except (_Interrupted, sqlite3.OperationalError):
                return "unknown"

    def sizes(self) -> dict[str, str]:
        """Bytes per table (pages of the table and its indexes) from `dbstat` when SQLite was built with it."""
        try:
            rows = self.query(
                "SELECT m.tbl_name, SUM(s.pgsize) FROM dbstat AS s JOIN sqlite_master AS m ON s.name = m.name "
                "GROUP BY m.tbl_name"
            )
        except (_Interrupted, sqlite3.OperationalError):
            return {}
        return {str(r[0]): str(r[1]) for r in rows if r[1] is not None}

    def table(self, name: str, cols: list[tuple[Any, ...]], count: str, indexes: list[tuple[Any, ...]]) -> None:
        self.heading(3, name, name)
        fks = {str(r[3]): f"{r[2]}({r[4]})" for r in self.query(f"PRAGMA foreign_key_list({quote_ident(name)})")}
        rows = [
            [
                display_text(str(c[1]), self.stats),
                display_text(str(c[2] or ""), self.stats),
                CellValue("yes" if c[3] else "no"),
                display_text("" if c[4] is None else str(c[4]), self.stats),
                CellValue("yes" if c[5] else "no"),
                display_text(fks.get(str(c[1]), ""), self.stats),
            ]
            for c in cols
        ]
        self.doc.blocks.append(
            make_table(
                ["Column", "Type", "Not null", "Default", "Primary key", "References"],
                rows,
                prov(self.source, name),
                column_types=["text", "text", "bool", "text", "bool", "text"],
            )
        )
        if indexes:
            items = [
                ListItem(
                    spans=[InlineSpan(text=clean_text(str(r[3] or r[1]), self.stats))],
                    provenance=prov(self.source, f"{name}/index={r[1]}"),
                )
                for r in indexes
            ]
            self.doc.blocks.append(ListBlock(items=items, provenance=prov(self.source, f"{name}/indexes")))
        names = [str(c[1]) for c in cols]
        types = [_affinity(str(c[2] or "")) for c in cols]
        if len(names) > self.opts.max_cols:
            self.warnings.append(columns_truncated_warning(f"Table {name}", len(names), self.opts.max_cols))
            names, types = names[: self.opts.max_cols], types[: self.opts.max_cols]
        if names:
            self.statistics(name, names, count)
            self.sample(name, names, types, count)

    def statistics(self, name: str, names: list[str], count: str) -> None:
        """Nulls, distinct values, min and max per column, only for tables under `stats_max_rows` rows."""
        if not count.isdigit() or int(count) == 0 or int(count) > self.opts.stats_max_rows:
            return
        parts = []
        for n in names:
            c = quote_ident(n)
            parts.append(f"COUNT(*) - COUNT({c}), COUNT(DISTINCT {c}), MIN({c}), MAX({c})")
        path = f"{name}/statistics"
        self.heading(4, "Statistics", path)
        try:
            (row,) = self.query(f"SELECT {', '.join(parts)} FROM {quote_ident(name)}")  # noqa: S608 quoted identifiers
        except _Interrupted:
            self.note("(Statistics timed out.)", path)
            return

        def bound(v: Any) -> CellValue:
            return CellValue("") if v is None or isinstance(v, bytes) else display_text(scalar_text(v), self.stats)

        rows = [
            [
                display_text(n, self.stats),
                CellValue(str(row[4 * i])),
                CellValue(str(row[4 * i + 1])),
                bound(row[4 * i + 2]),
                bound(row[4 * i + 3]),
            ]
            for i, n in enumerate(names)
        ]
        self.doc.blocks.append(
            make_table(
                ["Column", "Nulls", "Distinct", "Min", "Max"],
                rows,
                prov(self.source, path),
                column_types=["text", "int", "int", "text", "text"],
            )
        )

    def sample(self, name: str, names: list[str], types: list[ColumnType], count: str) -> None:
        path = f"{name}/sample"
        self.heading(4, "Sample", path)
        select = ", ".join(quote_ident(n) for n in names)
        q = quote_ident(name)
        head_n, tail_n = self.opts.head_rows, self.opts.tail_rows
        try:
            head = self.query(f"SELECT {select} FROM {q} LIMIT ?", (head_n + tail_n + 1,))  # noqa: S608 quoted identifiers
        except _Interrupted:
            self.note("(Sample timed out.)", path)
            return
        tail: list[tuple[Any, ...]] = []
        sampled = len(head) > head_n + tail_n
        if sampled:
            head = head[:head_n]
            try:
                last = f"SELECT {select} FROM {q} ORDER BY rowid DESC LIMIT ?"  # noqa: S608 quoted identifiers
                tail = list(reversed(self.query(last, (tail_n,))))
            except (_Interrupted, sqlite3.OperationalError):
                tail = []  # WITHOUT ROWID tables have no rowid; the head sample stands alone
        rows = [[_cell(v, self.stats) for v in r] for r in [*head, *tail]]
        observed = [merge_types(value_type(r[c]) for r in [*head, *tail]) for c in range(len(names))]
        final = [t if t != "text" else o for t, o in zip(types, observed, strict=True)]
        table = make_table(
            [clean_text(n, self.stats) for n in names], rows, prov(self.source, path), column_types=final
        )
        self.doc.blocks.append(table)
        if sampled:
            total = int(count) if count.isdigit() else None
            omitted = total - len(head) - len(tail) if total is not None else None
            self.doc.blocks.append(mark_sampled(table, total=total, omitted=omitted, after_row=len(head)))
            self.warnings.append(
                rows_sampled_warning(f"Table {name}", total or len(head) + len(tail), omitted or 0, self.opts)
            )

    def code_section(self, title: str, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        self.heading(2, title, "/")
        for r in rows:
            self.heading(3, str(r[1]), str(r[1]))
            self.doc.blocks.append(
                CodeBlock(
                    code=clean_text(str(r[3] or ""), self.stats),
                    language="sql",
                    provenance=prov(self.source, str(r[1])),
                )
            )
