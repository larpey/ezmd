"""data.csv: CSV and TSV (docs/spec/part2.md section 2c steps 35 to 37; caps from 13.4).

Decoding: BOM first (and stripped), strict UTF-8, then charset-normalizer on the first 1 MB. Dialect:
`csv.Sniffer` on the first 64 KB over `, ; \\t |`, validated by field-count consistency, falling back to
the delimiter with the most consistent per-line count; TSV mimes force a tab. Header: a first row of
non-empty, non-numeric strings above typed data, with `Sniffer.has_header` as the tie-breaker; otherwise a
synthetic `A, B, C` header row is added. Ragged rows are padded or overflow into the last column
(`ragged_rows`). Rows beyond 10,000 and columns beyond 256 are cut (`row_cap_reached`, `columns_truncated`).
Cell strings are never reformatted; `column_types` come from a 500-row sample. The renderer applies the
six-column and fifty-row rules and writes the CSV attachment.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass

from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import ColumnType, Document, Warning, WarningKind
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.data._base import CSV_LIMITS, finish, mime_of, new_document, read_capped, suffix_of
from intomd_converters.data._common import (
    CellValue,
    DataOptions,
    columns_truncated_warning,
    decode_bytes,
    display_text,
    encoding_warning,
    make_table,
    merge_types,
    prov,
    text_type,
)

CSV_MIMES = ("text/csv", "text/tab-separated-values")
CANDIDATES = (",", ";", "\t", "|")
SNIFF_BYTES = 64 * 1024
TYPE_SAMPLE_ROWS = 500
HAS_HEADER_MIN_ROWS = 5
_DELIM_NAMES = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}


@dataclass(slots=True)
class Dialect:
    delimiter: str
    quotechar: str = '"'
    sniffed: bool = True


def _consistency(sample: str, delim: str) -> tuple[float, int]:
    """(share of rows with the modal field count, modal count) when parsing `sample` with `delim`."""
    try:
        rows = list(csv.reader(io.StringIO(sample), delimiter=delim))[:200]
    except csv.Error:
        return 0.0, 0
    if len(rows) > 1 and not sample.endswith("\n"):
        rows = rows[:-1]  # the sample may cut the last row short
    counts = Counter(len(r) for r in rows if r)
    if not counts:
        return 0.0, 0
    modal, hits = counts.most_common(1)[0]
    return hits / sum(counts.values()), modal


def sniff_dialect(sample: str, *, force: str | None = None) -> Dialect:
    if force:
        return Dialect(force, sniffed=False)
    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATES))
        share, modal = _consistency(sample, sniffed.delimiter)
        if sniffed.delimiter in CANDIDATES and modal >= 2 and share >= 0.9:
            return Dialect(sniffed.delimiter, sniffed.quotechar or '"')
    except csv.Error:
        pass
    best = max(CANDIDATES, key=lambda d: (_consistency(sample, d)[1] >= 2, *_consistency(sample, d)))
    return Dialect(best, sniffed=False)


def _is_header(rows: list[list[str]], sample: str, comma_decimal: bool) -> bool:
    if len(rows) < 2:
        return False
    first = rows[0]
    if not all(c.strip() for c in first):
        return False
    if any(text_type(c, comma_decimal=comma_decimal) in ("int", "float", "percent") for c in first):
        return False
    body = rows[1 : 1 + TYPE_SAMPLE_ROWS]
    typed = any(text_type(c, comma_decimal=comma_decimal) not in (None, "text") for r in body for c in r)
    if typed or len(set(first)) < len(first):
        return typed
    if len(rows) < HAS_HEADER_MIN_ROWS:
        return True  # too few rows for Sniffer.has_header to be meaningful; most CSVs carry a header
    try:
        return csv.Sniffer().has_header(sample)
    except csv.Error:
        return True


def _col_name(i: int) -> str:
    name = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        name = chr(65 + rem) + name
    return name


class CsvConverter:
    id = "data.csv"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = CSV_MIMES
    limits = CSV_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        mime = mime_of(ref)
        if mime in CSV_MIMES:
            return 0.95
        if suffix_of(ref) in (".csv", ".tsv", ".tab") and mime in ("text/plain", None):
            return 0.6
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = DataOptions.from_options(options)
        decoded = decode_bytes(read_capped(ref, 200 * 1024 * 1024, "CSV"))
        stats = CleanStats()
        text = clean_text(decoded.text, stats)
        if not text.strip():
            raise ConversionError("empty CSV", user_message="The file contains no rows.")
        warnings: list[Warning] = []
        enc = encoding_warning(decoded)
        if enc is not None:
            warnings.append(enc)
        tsv = mime_of(ref) == "text/tab-separated-values" or suffix_of(ref) in (".tsv", ".tab")
        sample = text[:SNIFF_BYTES]
        dialect = sniff_dialect(sample, force="\t" if tsv else None)
        comma_decimal = dialect.delimiter == ";"
        rows, line_spans, cut, error = self._read(text, dialect, opts, options)
        if not rows:
            raise ConversionError("no CSV rows", user_message="The file contains no rows.")
        if error is not None:
            warnings.append(
                Warning(
                    kind=WarningKind.MARKUP_PARTIAL,
                    message=f"CSV parsing stopped early ({error[:200]}); later rows were not converted.",
                )
            )
        header_present = _is_header(rows, sample, comma_decimal)
        width = len(rows[0]) if header_present else Counter(len(r) for r in rows).most_common(1)[0][0]
        ragged = 0
        fixed: list[list[str]] = []
        for r in rows:
            if len(r) < width:
                ragged += 1
                r = r + [""] * (width - len(r))
            elif len(r) > width:
                ragged += 1
                r = [*r[: width - 1], dialect.delimiter.join(r[width - 1 :])]
            fixed.append(r)
        if ragged:
            warnings.append(
                Warning(
                    kind=WarningKind.RAGGED_ROWS,
                    message=f"{ragged} row(s) did not have {width} fields; short rows were padded and long rows "
                    "overflowed into the last column.",
                    count=ragged,
                )
            )
        if width > opts.csv_max_cols:
            warnings.append(columns_truncated_warning("The CSV", width, opts.csv_max_cols))
            fixed = [r[: opts.csv_max_cols] for r in fixed]
            width = opts.csv_max_cols
        if header_present:
            header, body = fixed[0], fixed[1:]
        else:
            header, body = [_col_name(i) for i in range(width)], fixed
        if len(body) > opts.csv_max_rows:
            body, cut = body[: opts.csv_max_rows], True
        types: list[ColumnType] = [
            merge_types(text_type(r[c], comma_decimal=comma_decimal) for r in body[:TYPE_SAMPLE_ROWS])
            for c in range(width)
        ]
        cells = [[display_text(v, stats) for v in r] for r in body]
        doc = new_document(ref, encoding=decoded.encoding, confidence=decoded.confidence)
        if cut:
            doc.truncated = True
            warnings.append(
                Warning(
                    kind=WarningKind.ROW_CAP_REACHED,
                    message=f"Only the first {opts.csv_max_rows:,} data rows were converted. "
                    "Raise data.csv_max_rows to include more.",
                    detail={"max_rows": opts.csv_max_rows},
                )
            )
        last = _col_name(width - 1) + str(len(body) + 1)
        attrs = {"header_synthesized": "true"} if not header_present else {}
        table = make_table(
            [display_text(h, stats).text for h in header],
            [[CellValue(c.text, c.raw) for c in r] for r in cells],
            prov(ref.display, f"A1:{last}", line_start=line_spans[0], line_end=line_spans[1]),
            column_types=types,
            attrs=attrs,
        )
        doc.blocks.append(table)
        doc.metadata.extra.update(
            {
                "format": "TSV" if tsv else "CSV",
                "delimiter": _DELIM_NAMES.get(dialect.delimiter, dialect.delimiter),
                "dialect_sniffed": dialect.sniffed,
                "bom": decoded.bom,
                "rows": len(body),
                "columns": width,
                "header_row": header_present,
            }
        )
        return finish(doc, stats, warnings)

    @staticmethod
    def _read(
        text: str, dialect: Dialect, opts: DataOptions, options: ConvertOptions
    ) -> tuple[list[list[str]], tuple[int, int], bool, str | None]:
        reader = csv.reader(io.StringIO(text), delimiter=dialect.delimiter, quotechar=dialect.quotechar)
        rows: list[list[str]] = []
        cut = False
        error: str | None = None
        try:
            for row in reader:
                if not row or (len(row) == 1 and not row[0].strip()):
                    continue
                if len(rows) > opts.csv_max_rows:
                    cut = True
                    break
                rows.append(row)
                if len(rows) % 1000 == 0:
                    options.ctx.check_deadline()
        except csv.Error as e:
            if not rows:
                raise ConversionError(f"CSV parse error: {e}", user_message="This CSV could not be parsed.") from e
            error = f"line {reader.line_num}: {e}"
        return rows, (1, reader.line_num), cut, error
