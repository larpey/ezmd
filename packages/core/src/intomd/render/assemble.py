"""intomd.render.assemble: place footnotes and page markers, build the head blocks, apply token budgets.

Body grammar (docs/spec/part3.md section 14): summary blockquote, orientation line, contents, the H1 title,
the body, and (compact) the numbered `## Links` list.
"""

from __future__ import annotations

import re

from intomd.ir import SourceType, WarningKind
from intomd.render.context import RenderContext, Unit
from intomd.render.inline import render_spans
from intomd.render.tokens import count_o200k

__all__ = [
    "apply_budget",
    "apply_cursor",
    "head_units",
    "links_units",
    "place_footnotes",
    "place_page_markers",
    "title_unit",
]

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _footnote_unit(ctx: RenderContext, ids: list[str]) -> Unit | None:
    lines: list[str] = []
    for fid in sorted(ids, key=lambda f: ctx.fn_numbers[f]):
        fn = ctx.footnotes[fid]
        text = render_spans(ctx, fn.spans) or fn.marker
        lines.append(f"[^{ctx.fn_numbers[fid]}]: {text}")
        ctx.side("footnotes", {"number": ctx.fn_numbers[fid], "source_marker": fn.marker, "block_id": fid})
    ctx.take_refs()  # nested references inside definitions are numbered but not re-placed
    return Unit(text="\n".join(lines), kind="footnotes", block_ids=list(ids)) if lines else None


def place_footnotes(ctx: RenderContext, units: list[Unit]) -> list[Unit]:
    mode = ctx.profile.footnotes
    if mode == "drop":
        return units
    out: list[Unit] = []
    pending: list[tuple[str, int]] = []
    level = 1

    def flush(min_level: int) -> None:
        nonlocal pending
        ready = [fid for fid, lvl in pending if lvl >= min_level]
        pending = [(fid, lvl) for fid, lvl in pending if lvl < min_level]
        unit = _footnote_unit(ctx, ready)
        if unit:
            out.append(unit)

    for u in units:
        if u.kind == "heading" and u.heading is not None and mode == "section_end":
            flush(u.heading.level)
        if u.kind == "heading" and u.heading is not None:
            level = u.heading.level
        out.append(u)
        if not u.fn_refs:
            continue
        if mode == "inline" or (u.kind == "table" and mode == "section_end"):
            unit = _footnote_unit(ctx, u.fn_refs)
            if unit:
                out.append(unit)
        else:
            pending.extend((fid, level) for fid in u.fn_refs)
    for fid in ctx.footnotes:
        if fid not in ctx.fn_numbers:
            ctx.footnote_number(fid)
            pending.append((fid, 0))
    ctx.take_refs()
    flush(0)
    return out


def place_page_markers(ctx: RenderContext, units: list[Unit]) -> list[Unit]:
    if not ctx.profile.page_markers or ctx.doc.metadata.source_type in (SourceType.PPTX, SourceType.XLSX):
        return units
    out: list[Unit] = []
    current: int | None = None
    for u in units:
        if u.page is not None and u.page != current and u.kind not in ("marker", "footnotes"):
            label = f' label="{u.page_label}"' if u.page_label else ""
            out.append(Unit(text=f"<!-- page {u.page}{label} -->", kind="marker", page=u.page, generated=True))
            current = u.page
        out.append(u)
    return out


def title_unit(ctx: RenderContext, title: str) -> Unit:
    from intomd.render.text import escape_inline

    text = f"# {escape_inline(title)}" + (" {#doc}" if ctx.profile.anchors else "")
    return Unit(text=text, kind="heading")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def head_units(ctx: RenderContext, summary: list[str], units: list[Unit]) -> list[Unit]:
    profile = ctx.profile
    out: list[Unit] = []
    if summary and profile.summary_blockquote:
        sentences = _SENTENCE.split(" ".join(summary))
        out.append(Unit(text="> Summary: " + " ".join(sentences[:4]), kind="head"))
    headings = [u.heading for u in units if u.kind == "heading" and u.heading is not None and u.heading.level <= 6]
    tokens = sum(count_o200k(u.text) for u in units)
    triggered = len(headings) >= profile.toc_min_headings or tokens > profile.toc_min_tokens
    if profile.orientation and triggered:
        parts: list[str] = []
        top = [h.label for h in headings if h.level == 2]
        counts = [
            _plural(ctx.table_count, "table") if ctx.table_count else "",
            _plural(ctx.figure_count, "figure") if ctx.figure_count else "",
            _plural(ctx.doc.metadata.pages, "page") if ctx.doc.metadata.pages else "",
        ]
        if top:
            parts.append("Sections: " + ", ".join(top) + ".")
        tail = ", ".join(c for c in counts if c)
        if tail:
            parts.append(tail + ".")
        if parts:
            out.append(Unit(text="> " + " ".join(parts), kind="head"))
    if profile.toc == "always" or (profile.toc == "auto" and triggered):
        lines = []
        for h in headings:
            indent = "    " * (h.level - 2)
            lines.append(f"{indent}- [{h.label}](#{h.anchor})" if h.anchor else f"{indent}- {h.label}")
        if lines:
            out.append(Unit(text="## Contents\n\n" + "\n".join(lines), kind="head"))
    return out


def links_units(ctx: RenderContext) -> list[Unit]:
    if ctx.profile.links != "numbered_list" or not ctx.links.numbered:
        return []
    items = "\n".join(f"{i}. {url}" for i, url in enumerate(ctx.links.numbered, start=1))
    return [Unit(text="## Links", kind="heading"), Unit(text=items, kind="links")]


def apply_cursor(units: list[Unit], cursor: str | None) -> list[Unit]:
    if not cursor:
        return units
    for i, u in enumerate(units):
        if u.heading is not None and u.heading.anchor == cursor:
            return units[i:]
    raise ValueError(f"unknown cursor {cursor!r}")


def apply_budget(ctx: RenderContext, units: list[Unit], budget: int | None) -> tuple[list[Unit], dict[str, object]]:
    """Fit the body into `budget` o200k tokens: drop figures first (compact), then truncate trailing sections."""
    if budget is None:
        return units, {}
    sizes = [count_o200k(u.text) + 1 for u in units]
    original = sum(sizes)
    if original <= budget:
        return units, {}
    if ctx.profile.name == "compact":
        units = [u for u in units if u.kind != "figure"]
        sizes = [count_o200k(u.text) + 1 for u in units]
        if sum(sizes) <= budget:
            return units, {"reason": "max_tokens", "limit": budget, "original_tokens": original}
    total, cut = 0, 0
    for i, size in enumerate(sizes):
        if total + size > budget:
            break
        total += size
        cut = i + 1
    boundary = max((i for i in range(1, cut + 1) if i < len(units) and units[i].kind == "heading"), default=cut)
    cut = boundary if boundary > 0 else cut
    kept, dropped = units[:cut], units[cut:]
    next_heading = next((u.heading for u in dropped if u.heading is not None), None)
    ctx.truncated = True
    ctx.warn(
        WarningKind.TRUNCATED_MAX_TOKENS,
        f"Output was truncated at max_tokens={budget}.",
        limit=budget,
        original_tokens=original,
    )
    if ctx.profile.name == "agent" and next_heading is not None and next_heading.anchor:
        note = f'<!-- intomd: continued; next_cursor="{next_heading.anchor}" -->'
    else:
        note = f"<!-- intomd: truncated at max_tokens={budget}; {len(dropped)} blocks omitted -->"
    kept.append(Unit(text=note, kind="note", generated=True))
    return kept, {"reason": "max_tokens", "limit": budget, "original_tokens": original}
