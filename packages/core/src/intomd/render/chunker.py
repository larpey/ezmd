"""intomd.render.chunker: rag chunking (docs/spec/part3.md section 17, rules 1-5 and 8).

1. Split on headings first (any level), then pack units into chunks of at most `chunk_tokens` (o200k).
   Units are never split except prose longer than the budget (sentence boundaries), lists longer than the
   budget (between items) and tables larger than 4x the budget (by rows, header and caption repeated).
2. Sections shorter than `min_chunk_tokens` merge with the following section when the result still fits.
3. Optional overlap re-emits whole trailing sentences of the previous chunk.
4. Each chunk starts with a bold breadcrumb (title > heading path, plus the time range for transcripts).
5. Chunks are delimited by `<!-- chunk ... -->` / `<!-- /chunk -->` markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from intomd.render.base import Chunk
from intomd.render.context import HeadingInfo, Unit
from intomd.render.text import fmt_time
from intomd.render.tokens import count_o200k

__all__ = ["chunk_units"]

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class _Section:
    units: list[Unit]
    heading: HeadingInfo | None
    merged_preamble: bool = False

    @property
    def tokens(self) -> int:
        return sum(count_o200k(u.text) + 1 for u in self.units)


@dataclass(slots=True)
class _Draft:
    units: list[Unit] = field(default_factory=list)
    part: str | None = None
    oversized: bool = False


def _sections(units: list[Unit]) -> list[_Section]:
    sections: list[_Section] = [_Section([], None)]
    held: list[Unit] = []
    for u in units:
        if u.kind == "marker":
            held.append(u)
            continue
        if u.kind == "heading" and u.heading is not None:
            sections.append(_Section([], u.heading))
        sections[-1].units.extend([*held, u])
        held = []
    sections[-1].units.extend(held)
    return [s for s in sections if s.units]


def _merge_short(sections: list[_Section], min_tokens: int, budget: int) -> list[_Section]:
    out = list(sections)
    result: list[_Section] = []
    i = 0
    while i < len(out):
        sec = out[i]
        if sec.tokens < min_tokens and i + 1 < len(out) and sec.tokens + out[i + 1].tokens <= budget:
            nxt = out[i + 1]
            out[i + 1] = _Section(
                [*sec.units, *nxt.units],
                sec.heading or nxt.heading,
                merged_preamble=sec.heading is None or sec.merged_preamble,
            )
        else:
            result.append(sec)
        i += 1
    return result


def _split_unit(u: Unit, budget: int, first_budget: int | None = None) -> list[_Draft]:
    """Pieces of a unit larger than the budget, per the never-split rules."""
    size = count_o200k(u.text)
    if u.kind == "table" and u.table_rows and u.table_head and size > 4 * budget:
        head_tokens = count_o200k(u.table_head)
        pieces: list[list[str]] = [[]]
        used = head_tokens
        for row in u.table_rows:
            t = count_o200k(row) + 1
            if pieces[-1] and used + t > budget:
                pieces.append([])
                used = head_tokens
            pieces[-1].append(row)
            used += t
        sep = "\n" if u.table_head.rstrip().endswith("|") else "\n\n"
        n = len(pieces)
        return [
            _Draft(
                [Unit(text=u.table_head + sep + "\n".join(rows), kind="table", block_ids=u.block_ids, page=u.page)],
                part=f"{i}/{n}",
                oversized=True,
            )
            for i, rows in enumerate(pieces, 1)
        ]
    if u.kind == "prose":
        drafts: list[_Draft] = []
        cur: list[str] = []
        for sentence in _SENTENCE.split(u.text):
            limit = first_budget if (first_budget is not None and not drafts) else budget
            if cur and count_o200k(" ".join([*cur, sentence])) > limit:
                drafts.append(_Draft([Unit(" ".join(cur), "prose", u.block_ids, u.page)]))
                cur = []
            cur.append(sentence)
        if cur:
            drafts.append(_Draft([Unit(" ".join(cur), "prose", u.block_ids, u.page)]))
        return drafts
    if u.kind == "list" and u.list_items and len(u.list_items) > 1:
        drafts = []
        items: list[str] = []
        for item in u.list_items:
            if items and count_o200k("\n".join([*items, item])) > budget:
                drafts.append(_Draft([Unit("\n".join(items), "list", u.block_ids, u.page)]))
                items = []
            items.append(item)
        if items:
            drafts.append(_Draft([Unit("\n".join(items), "list", u.block_ids, u.page)]))
        return drafts
    return [_Draft([u], oversized=True)]


def _pack(section: _Section, budget: int, crumb_tokens: int) -> list[_Draft]:
    drafts: list[_Draft] = [_Draft()]
    used = crumb_tokens
    held: list[Unit] = []

    def place(units: list[Unit], size: int) -> None:
        """Append to the open draft when it fits, else start a new one."""
        nonlocal used
        if used + size <= budget:
            drafts[-1].units.extend(units)
            used += size
        else:
            drafts.append(_Draft(list(units)))
            used = crumb_tokens + size

    def place_alone(piece: _Draft) -> None:
        """Table parts and oversized units always get a chunk of their own."""
        nonlocal used
        drafts.append(piece)
        drafts.append(_Draft())
        used = crumb_tokens

    for u in section.units:
        if u.kind == "marker":
            held.append(u)
            continue
        size = count_o200k(u.text) + 1 + sum(count_o200k(m.text) + 1 for m in held)
        if size + crumb_tokens <= budget:
            place([*held, u], size)
        else:
            room = budget - used - 1 - sum(count_o200k(m.text) + 1 for m in held)
            first = room if room >= 50 else None
            for n, piece in enumerate(_split_unit(u, budget - crumb_tokens - 1, first)):
                lead = held if n == 0 else []
                if piece.part or piece.oversized:
                    piece.units[:0] = lead
                    place_alone(piece)
                else:
                    place([*lead, *piece.units], sum(count_o200k(x.text) + 1 for x in [*lead, *piece.units]))
        held = []
    if held:
        drafts[-1].units.extend(held)
    return [d for d in drafts if d.units]


def _times(units: list[Unit]) -> tuple[float | None, float | None]:
    starts = [u.time_start for u in units if u.time_start is not None]
    ends = [u.time_end for u in units if u.time_end is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def chunk_units(
    units: list[Unit], *, title: str, docid: str, chunk_tokens: int, min_chunk_tokens: int, overlap_tokens: int
) -> tuple[list[Chunk], list[str]]:
    """Return the chunks and the body pieces (marker + text + closing marker) in order."""
    sections = _merge_short(_sections(units), min_chunk_tokens, chunk_tokens)
    chunks: list[Chunk] = []
    pieces: list[str] = []
    prev_tail = ""
    for sec in sections:
        path = sec.heading.path if sec.heading else []
        base_crumb = " > ".join([title, *path])
        for draft in _pack(sec, chunk_tokens, count_o200k(f"**{base_crumb}**") + 2):
            start, end = _times(draft.units)
            crumb = base_crumb + (f" [{fmt_time(start)} - {fmt_time(end)}]" if start is not None else "")
            body = "\n\n".join(u.text for u in draft.units)
            parts = [f"**{crumb}**"]
            if overlap_tokens > 0 and prev_tail:
                parts.append(prev_tail)
            parts.append(body)
            text = "\n\n".join(parts)
            pages = [u.page for u in draft.units if u.page is not None]
            n = len(chunks) + 1
            chunk = Chunk(
                id=f"{docid}#c{n:04d}",
                text=text,
                section_id=sec.heading.anchor if sec.heading else None,
                breadcrumb=crumb,
                tokens=count_o200k(text),
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                time_start=start,
                time_end=end,
                block_ids=[b for u in draft.units for b in u.block_ids],
                part=draft.part,
                oversized=draft.oversized and count_o200k(text) > chunk_tokens,
                merged_preamble=sec.merged_preamble,
            )
            chunks.append(chunk)
            attrs = [f'id="{chunk.id}"']
            if sec.heading and sec.heading.number:
                attrs.append(f'section="{sec.heading.number}"')
            attrs.append(f'tokens="{chunk.tokens}"')
            if chunk.page_start is not None:
                attrs.append(f'page="{chunk.page_start}"')
            if start is not None:
                attrs.append(f'start="{fmt_time(start)}"')
            if end is not None:
                attrs.append(f'end="{fmt_time(end)}"')
            if chunk.part:
                attrs.append(f'part="{chunk.part}"')
            if chunk.oversized:
                attrs.append('oversized="true"')
            pieces.append(f"<!-- chunk {' '.join(attrs)} -->\n{text}\n<!-- /chunk -->")
            prev_tail = _tail(body, overlap_tokens)
    return chunks, pieces


def _tail(body: str, overlap_tokens: int) -> str:
    if overlap_tokens <= 0:
        return ""
    last = body.rsplit("\n\n", 1)[-1]
    if last.startswith(("|", "<", "- ", "```", "**Table")):
        return ""
    picked: list[str] = []
    for sentence in reversed(_SENTENCE.split(last)):
        if count_o200k(" ".join([sentence, *picked])) > overlap_tokens:
            break
        picked.insert(0, sentence)
    return " ".join(picked)
