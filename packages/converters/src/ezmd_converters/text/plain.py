"""text.plain: plain text and any `text/*` not claimed by a more specific converter.

docs/spec/part1.md P0-T06: decode with charset detection (charset-normalizer, MIT), split paragraphs
on blank lines, promote setext-style underlined headings (`===` -> level 1, `---` -> level 2) and
short ALL-CAPS lines standing alone between blank lines (docs/spec/part2.md 4c step 22 rule 3: under 60
characters, at least 3 words or a trailing colon) to level-2 headings, keep blocks indented by 4+ spaces
or a tab as code (rule 5) unless they read as an indented quote or sub-list, turn runs of 3+ lines whose
columns line up on 2+ space gaps into tables (rule 6), keep outline items on their own lines (rule 4, through
text.lines), emit Paragraph blocks with line provenance, and strip NUL/control/invisible characters with a
warning count. Outline numbering is not turned into nested List blocks and the Markdown-routing rule is not
implemented (docs/converters/text.md, Known limitations).
"""

from __future__ import annotations

import re

from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef
from ezmd.ir import (
    CodeBlock,
    Document,
    Heading,
    InlineSpan,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
)
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.text.lines import LINE_BREAKS_ATTR, LINE_BREAKS_HARD, join_lines

_UNDERLINE = re.compile(r"^(=+|-+)\s*$")
_MAX_HEADING_CHARS = 200
_MAX_CAPS_HEADING_CHARS = 60
_TAB = chr(9)
_NL = chr(10)
_SENTENCE_END = (".", "!", "?")
_GAP = re.compile(r"\S(?: ?\S)*")
"""A whitespace-table cell: non-space runs separated by at most one space (two or more spaces end a cell)."""
_LIST_ITEM = re.compile(r"^(?:[-*+•]|\d{1,3}(?:\.\d{1,3})+[.)]?|\d{1,3}[.)])\s+\S")
_CODE_CHARS = frozenset("{}()[];=<>/$#|&*_~`@^" + chr(92))
_MIN_TABLE_ROWS = 3
_COLUMN_SLACK = 1


def _indented(line: str) -> bool:
    return line.startswith(("    ", _TAB)) and bool(line.strip())


def _reads_as_text(block: list[str]) -> bool:
    """An indented block that is a sub-list or a quoted passage, not code (rule 5 is about code)."""
    stripped = [x.strip() for x in block if x.strip()]
    if not stripped:
        return False
    if all(_LIST_ITEM.match(x) for x in stripped):
        return True
    joined = " ".join(stripped)
    symbols = sum(1 for c in joined if c in _CODE_CHARS)
    words = joined.split()
    closes = joined.rstrip(chr(34) + chr(0x201D) + chr(39) + chr(0x2019) + ")").endswith(_SENTENCE_END)
    return closes and len(words) >= 8 and symbols <= len(joined) // 50


def _caps_heading(lines: list[str], i: int) -> bool:
    """Rule 3: a short ALL-CAPS line with blank lines (or the file edge) on both sides."""
    text = lines[i].strip()
    if not text or len(text) >= _MAX_CAPS_HEADING_CHARS or text != text.upper() or not any(c.isalpha() for c in text):
        return False
    if text.endswith(_SENTENCE_END):  # a shouted sentence ("DO NOT LEAVE BOATS UNATTENDED.") is not a heading
        return False
    if not (len(text.split()) >= 3 or text.endswith(":")):
        return False
    before = lines[i - 1] if i > 0 else ""
    after = lines[i + 1] if i + 1 < len(lines) else ""
    return not before.strip() and not after.strip()


def _cells(line: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(0)) for m in _GAP.finditer(line)]


def _whitespace_table(run: list[str]) -> list[list[str]] | None:
    """Rule 6: 3+ lines that each split on 2+ space gaps into the same number (2+) of cells whose start
    columns line up with the first line's. Tabs are expanded first. Returns the rows, or None."""
    lines = [x.expandtabs(8).rstrip() for x in run]
    if len(lines) < _MIN_TABLE_ROWS or any(_LIST_ITEM.match(x.strip()) for x in lines):
        return None
    head = _cells(lines[0])
    if len(head) < 2:
        return None
    starts = [c for c, _ in head]
    rows: list[list[str]] = []
    for line in lines:
        cells = _cells(line)
        if len(cells) != len(head):
            return None
        if any(abs(c - s) > _COLUMN_SLACK for (c, _), s in zip(cells, starts, strict=True)):
            return None
        rows.append([t for _, t in cells])
    return rows


def _table_block(rows: list[list[str]], source: str, start: int, end: int) -> Table:
    cells = [
        TableCell(spans=[InlineSpan(text=text)], row=r, col=c, is_header=r == 0)
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    return Table(
        cells=cells,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        header_rows=1,
        provenance=Provenance(source=source, line_start=start, line_end=end),
        attrs={"detected": "whitespace-aligned"},
    )


def _dedent(line: str) -> str:
    return line[1:] if line.startswith(_TAB) else line[4:]


def decode_text_detailed(raw: bytes) -> tuple[str, str, bool, float]:
    """Decode bytes to str. Returns (text, encoding, uncertain, confidence). BOMs win; then strict UTF-8; then
    charset-normalizer; finally UTF-8 with replacement."""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            return raw.decode(enc, errors="replace"), enc, False, 1.0
    try:
        return raw.decode("utf-8"), "utf-8", False, 1.0
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    # `uncertain` follows docs/spec/part2.md 13.2: only when detection confidence is low (< 0.7)
    # and the decode still contains replacement characters. A clean Latin-1/cp1252 decode is not
    # uncertain (D-0015).
    best = from_bytes(raw).best()
    if best is not None:
        text = str(best)
        confidence = max(0.0, min(1.0, 1.0 - float(best.chaos)))
        return text, best.encoding, confidence < 0.7 and "\ufffd" in text, confidence
    text = raw.decode("utf-8", errors="replace")
    return text, "utf-8", "\ufffd" in text, 0.0


def decode_text(raw: bytes) -> tuple[str, str, bool]:
    """Decode bytes to str. Returns (text, encoding, uncertain); see `decode_text_detailed`."""
    text, encoding, uncertain, _confidence = decode_text_detailed(raw)
    return text, encoding, uncertain


class PlainTextConverter:
    id = "text.plain"
    family = "text"
    priority = 0
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/plain", "text/*")

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if mime == "text/plain":
            return 0.9
        if mime is not None and mime.startswith("text/") and mime != "text/x-uri":
            return 0.3
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raw = ref.read()
        source = ref.display
        meta = Metadata(source=source, source_type=SourceType.TEXT, mime=ref.detected.mime if ref.detected else None)
        doc = Document(metadata=meta)
        if not raw.strip():
            doc.warnings.append(
                Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="The file contains no text.")
            )
            return doc.finalize()
        if (
            b"\x00" in raw[:8192]
            and raw.count(b"\x00") > len(raw) // 10
            and not raw.startswith((b"\xff\xfe", b"\xfe\xff"))
        ):
            raise ConversionError(
                "input looks binary (many NUL bytes)", user_message="This file does not look like text."
            )
        text, encoding, guessed, confidence = decode_text_detailed(raw)
        stats = CleanStats()
        text = clean_text(text, stats)
        if guessed:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.ENCODING_UNCERTAIN,
                    message=f"Text encoding was detected as {encoding}; some characters may be wrong.",
                    detail={"encoding": encoding},
                )
            )
        meta.encoding = encoding
        meta.encoding_confidence = confidence
        doc.blocks.extend(_blocks(text, source))
        if stats.total:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                    severity="info",
                    message=f"Removed {stats.total} control or invisible characters.",
                    count=stats.total,
                    detail={"control": stats.control, "invisible": stats.invisible, "surrogates": stats.surrogates},
                )
            )
        first = next((b for b in doc.blocks if isinstance(b, Heading)), None)
        if first is not None:
            meta.title = "".join(s.text for s in first.spans)
        return doc.finalize()


def _blocks(text: str, source: str) -> list[Heading | Paragraph | CodeBlock | Table]:
    lines = text.split("\n")
    out: list[Heading | Paragraph | CodeBlock | Table] = []
    para: list[str] = []
    start = 0

    def flush(end_line: int) -> None:
        # One Paragraph per blank-line run. Hard-wrapped lines join (text.lines: full-width or lowercase
        # continuation, never into list items or code); lines that do not join are kept as hard line breaks.
        nonlocal para
        rows = _whitespace_table(para)
        if rows is not None:
            out.append(_table_block(rows, source, start + 1, end_line))
            para = []
            return
        logical = join_lines(para)
        if logical:
            # A run that is one wrapped paragraph keeps its source newlines (the renderer joins them); a run
            # with real line breaks keeps one line per logical line, wraps joined with a space.
            hard = len(logical) > 1
            attrs = {LINE_BREAKS_ATTR: LINE_BREAKS_HARD} if hard else {}
            body = "\n".join(x.text for x in logical) if hard else "\n".join(para).strip("\n")
            out.append(
                Paragraph(
                    spans=[InlineSpan(text=body)],
                    provenance=Provenance(source=source, line_start=start + 1, line_end=end_line),
                    attrs=attrs,
                )
            )
        para = []

    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        is_setext = (
            not para
            and line.strip()
            and len(line.strip()) <= _MAX_HEADING_CHARS
            and nxt is not None
            and _UNDERLINE.match(nxt) is not None
            and len(nxt.strip()) >= 3
        )
        if is_setext:
            assert nxt is not None
            level = 1 if nxt.strip().startswith("=") else 2
            out.append(
                Heading(
                    level=level,
                    spans=[InlineSpan(text=line.strip())],
                    provenance=Provenance(source=source, line_start=i + 1, line_end=i + 2),
                )
            )
            i += 2
            continue
        if not line.strip():
            flush(i)
            i += 1
            continue
        if not para and _caps_heading(lines, i):
            out.append(
                Heading(
                    level=2,
                    spans=[InlineSpan(text=line.strip())],
                    provenance=Provenance(source=source, line_start=i + 1, line_end=i + 1),
                )
            )
            i += 1
            continue
        if not para and _indented(line):
            j = i
            while j < len(lines) and (_indented(lines[j]) or (not lines[j].strip() and _more_indented(lines, j))):
                j += 1
            if _reads_as_text(lines[i:j]):
                # An indented quote or sub-list: ordinary text, so take the run without its indentation.
                start = i
                para.extend(x.strip() for x in lines[i:j] if x.strip())
                i = j
                continue
            code = _NL.join(_dedent(x.rstrip()) for x in lines[i:j]).strip(_NL)
            out.append(
                CodeBlock(code=code, language=None, provenance=Provenance(source=source, line_start=i + 1, line_end=j))
            )
            i = j
            continue
        if not para:
            start = i
        para.append(line.rstrip())
        i += 1
    flush(len(lines))
    return out


def _more_indented(lines: list[str], j: int) -> bool:
    """A blank line inside an indented block continues it when the next non-blank line is indented too."""
    k = j
    while k < len(lines) and not lines[k].strip():
        k += 1
    return k < len(lines) and _indented(lines[k])
