"""text.plain: plain text and any `text/*` not claimed by a more specific converter.

docs/spec/part1.md P0-T06: decode with charset detection (charset-normalizer, MIT), split paragraphs
on blank lines, promote only setext-style underlined headings (`===` -> level 1, `---` -> level 2),
emit Paragraph blocks with line provenance, and strip NUL/control/invisible characters with a
warning count.
"""

from __future__ import annotations

import re

from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import Document, Heading, InlineSpan, Metadata, Paragraph, Provenance, SourceType, Warning, WarningKind
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.text.lines import LINE_BREAKS_ATTR, LINE_BREAKS_HARD, join_lines

_UNDERLINE = re.compile(r"^(=+|-+)\s*$")
_MAX_HEADING_CHARS = 200


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


def _blocks(text: str, source: str) -> list[Heading | Paragraph]:
    lines = text.split("\n")
    out: list[Heading | Paragraph] = []
    para: list[str] = []
    start = 0

    def flush(end_line: int) -> None:
        # One Paragraph per blank-line run. Hard-wrapped lines join (text.lines: full-width or lowercase
        # continuation, never into list items or code); lines that do not join are kept as hard line breaks.
        nonlocal para
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
        if not para:
            start = i
        para.append(line.rstrip())
        i += 1
    flush(len(lines))
    return out
