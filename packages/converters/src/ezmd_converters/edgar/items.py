"""Item sectioning for EDGAR filings (part2 12c step 3): `PART I`, `Item 1A. Risk Factors`, `Item 5.02 ...`,
`SIGNATURES`, with table-of-contents duplicates removed, sub-headings inferred from bold or italic short
paragraphs, page furniture (page numbers, repeated "Table of Contents" links) removed, and provenance
rewritten to `path = item/<id>` and `source_id = <accession>`.

Works on the raw blocks of the HTML-to-IR pass, so it does not depend on which filing agent produced the
HTML. Item headings must be bold or real headings; a sentence that merely starts with "Item 7" is text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ezmd.ir import Block, Heading, InlineSpan, InlineStyle, Paragraph, Table, spans_text
from ezmd_converters.edgar.tables import tidy_table

_ITEM = re.compile(r"^item\s+(\d{1,2}[a-z]?(?:\.\d{2})?)\s*(?:[.:–—-]\s*)?(.*)$", re.I | re.S)
_PART = re.compile(r"^part\s+(i{1,3}|iv)\b\s*(?:[.:–—-]\s*)?(.*)$", re.I | re.S)
_SIGNATURES = re.compile(r"^signatures?\.?$", re.I)
_FURNITURE = re.compile(
    r"^(?:\d{1,3}|[ivxlc]{1,7}|f-\d{1,3}|page \d{1,3}|table of contents|index|"
    r"[^|]{0,80}\|\s*\d{1,3}(?:\s*\|.{0,80})?)$",
    re.I,
)
MAX_ITEM_HEADING = 300
MAX_SUBHEADING = 120
COVER = "cover"


@dataclass(frozen=True, slots=True)
class Marker:
    kind: str
    """`part`, `item`, or `signatures`."""
    key: str
    """Dedup key: `II`, `II-1A`, `5.02`, `signatures`."""
    path: str
    title: list[InlineSpan]
    rest: list[InlineSpan]
    """Body text that shared the heading's paragraph (bold title, plain body)."""


@dataclass(slots=True)
class Sectioned:
    blocks: list[Block]
    items: list[str]
    """Item ids in document order (`1`, `1A`, `5.02`)."""
    furniture_removed: int = 0
    inferred_headings: int = 0


def _norm(text: str) -> str:
    return " ".join(text.replace(chr(0xA0), " ").split())


def _bold(span: InlineSpan) -> bool:
    return InlineStyle.BOLD in span.styles


def _split_bold_prefix(spans: list[InlineSpan]) -> tuple[list[InlineSpan], list[InlineSpan]]:
    head: list[InlineSpan] = []
    for i, s in enumerate(spans):
        if _bold(s) or not s.text.strip():
            head.append(s)
            continue
        return head, spans[i:]
    return head, []


def _strip(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Plain copies (no bold) with outer whitespace trimmed, for heading text."""
    text = _norm(spans_text(spans))
    return [InlineSpan(text=text)] if text else []


def _marker(block: Block, part: str | None) -> Marker | None:
    rest: list[InlineSpan]
    if isinstance(block, Heading):
        title, rest = block.spans, []
    elif isinstance(block, Paragraph):
        title, rest = _split_bold_prefix(block.spans)
    else:
        return None
    text = _norm(spans_text(title))
    if not text or len(text) > MAX_ITEM_HEADING:
        return None
    if _SIGNATURES.match(text):
        return Marker("signatures", "signatures", "signatures", _strip(title), rest)
    m = _PART.match(text)
    if m is not None and len(text) <= MAX_SUBHEADING:
        roman = m.group(1).upper()
        return Marker("part", roman, f"part/{roman}", _strip(title), rest)
    m = _ITEM.match(text)
    if m is not None:
        item = m.group(1).upper()
        key = f"{part}-{item}" if part else item
        return Marker("item", key, f"item/{item}" if not part else f"item/{part}-{item}", _strip(title), rest)
    return None


def _markers(blocks: list[Block]) -> dict[int, Marker]:
    """Marker per block index, keeping only the last occurrence of each key (earlier ones are the table of
    contents or cross-references set as headings)."""
    found: dict[int, Marker] = {}
    part: str | None = None
    for i, b in enumerate(blocks):
        m = _marker(b, part)
        if m is None:
            continue
        if m.kind == "part":
            part = m.key
        found[i] = m
    last: dict[str, int] = {}
    for i, m in found.items():
        last[m.key] = i
    keep = set(last.values())
    return {i: m for i, m in found.items() if i in keep}


def _subheading(block: Block, infer: bool) -> Heading | None:
    if isinstance(block, Heading):
        return block.model_copy(update={"level": min(6, max(3, block.level))})
    if not infer or not isinstance(block, Paragraph):
        return None
    text = _norm(spans_text(block.spans))
    if not text or len(text) > MAX_SUBHEADING or (text.endswith((".", ",", ";", ":")) and len(text) > 60):
        return None
    meaningful = [s for s in block.spans if s.text.strip()]
    if not meaningful or any(s.href for s in meaningful):
        return None
    if all(_bold(s) for s in meaningful):
        level = 3
    elif all(InlineStyle.ITALIC in s.styles for s in meaningful):
        level = 4
    else:
        return None
    if not re.search(r"[A-Za-z]", text):
        return None
    return Heading(level=level, spans=[InlineSpan(text=text)], provenance=block.provenance)


def _is_furniture(block: Block) -> bool:
    if not isinstance(block, Paragraph):
        return False
    text = _norm(spans_text(block.spans))
    if _FURNITURE.match(text) is None:
        return False
    if text.lower() in ("table of contents", "index"):
        # Page-top navigation links are furniture; a plain "TABLE OF CONTENTS" caption is content.
        return any(s.href for s in block.spans)
    return True


def _with_prov(block: Block, path: str, accession: str | None) -> Block:
    prov = block.provenance.model_copy(update={"path": path, "source_id": accession})
    return block.model_copy(update={"provenance": prov})


def section(blocks: list[Block], *, accession: str | None, infer_headings: bool = True) -> Sectioned:
    tidied: list[Block] = []
    for b in blocks:
        if isinstance(b, Table):
            t = tidy_table(b)
            if t is not None:
                tidied.append(t)
        else:
            tidied.append(b)
    markers = _markers(tidied)
    out: list[Block] = []
    items: list[str] = []
    path = COVER
    removed = inferred = 0
    seen_marker = False
    for i, b in enumerate(tidied):
        m = markers.get(i)
        if m is not None:
            seen_marker = True
            path = m.path
            if m.kind == "item":
                items.append(m.path.removeprefix("item/"))
            out.append(_with_prov(Heading(level=2, spans=m.title, provenance=b.provenance), path, accession))
            if m.rest and _norm(spans_text(m.rest)):
                para = Paragraph(spans=m.rest, provenance=b.provenance)
                out.append(_with_prov(para, path, accession))
            continue
        if _is_furniture(b):
            removed += 1
            continue
        if seen_marker:
            h = _subheading(b, infer_headings)
            if h is not None:
                if not isinstance(b, Heading):
                    inferred += 1
                b = h
        elif isinstance(b, Heading):
            b = Paragraph(spans=b.spans, provenance=b.provenance)
        out.append(_with_prov(b, path, accession))
    return Sectioned(blocks=out, items=items, furniture_removed=removed, inferred_headings=inferred)
