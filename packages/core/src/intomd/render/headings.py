"""intomd.render.headings: title selection and the heading plan (docs/spec/part3.md section 14, "Headings").

- Exactly one H1: the title. Source headings shift down one level and are clamped to parent + 1.
- Derived numbering (`3.2`) replaces any source numbering; anchors are `sec-3-2` (the H1 is `doc`).
- Headings deeper than H6 become bold paragraphs. Text is one line, formatting stripped except code spans,
  no trailing punctuation except `?`, max 200 chars (the full text overflows into the next paragraph).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from intomd.ir import Heading, Paragraph
from intomd.render.children import CHILD_SECTION_ATTR
from intomd.render.context import HeadingInfo, RenderContext
from intomd.render.inline import plain_spans, render_spans
from intomd.render.text import slugify

__all__ = ["MAX_HEADING_CHARS", "heading_markdown", "plan_headings", "resolve_title"]

MAX_HEADING_CHARS = 200
_SOURCE_NUM = re.compile(r"^\d+(?:\.\d+)*\\?\.?\s+(?=\S)")
_TRAIL_PUNCT = re.compile(r"[.:;,!]+$")


def resolve_title(ctx: RenderContext) -> str:
    doc = ctx.doc
    if doc.metadata.title and doc.metadata.title.strip():
        return " ".join(doc.metadata.title.split())
    for b in doc.blocks:
        if ctx.is_child_block(b.id):
            break
        if isinstance(b, Heading) and b.level == 1:
            text = plain_spans(ctx, b.spans)
            if text:
                return text
        if isinstance(b, Paragraph) and b.role == "title":
            text = plain_spans(ctx, b.spans)
            if text:
                return text
    source = doc.metadata.source.rstrip("/").replace("\\", "/")
    stem = PurePosixPath(source.split("?")[0]).stem if source else ""
    return stem or "Untitled"


def _truncate(text: str) -> tuple[str, str | None]:
    if len(text) <= MAX_HEADING_CHARS:
        return text, None
    cut = text[: MAX_HEADING_CHARS - 3]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "...", text


def _consumed_ids(ctx: RenderContext, title: str) -> set[str]:
    consumed: set[str] = set()
    key = title.casefold()
    own = [b for b in ctx.doc.blocks if not ctx.is_child_block(b.id)]
    first_heading = next((b for b in own if isinstance(b, Heading)), None)
    first_text = plain_spans(ctx, first_heading.spans).casefold() if first_heading is not None else None
    if first_heading is not None and first_heading.level == 1 and first_text == key:
        consumed.add(first_heading.id)
    for b in own:
        if isinstance(b, Paragraph) and b.role == "title" and plain_spans(ctx, b.spans).casefold() == key:
            consumed.add(b.id)
    return consumed


def plan_headings(ctx: RenderContext, title: str) -> set[str]:
    """Fill `ctx.headings` and `ctx.anchors`; return ids of blocks consumed by the title."""
    consumed = _consumed_ids(ctx, title)
    # Source levels move down one only when an H1 survives below the title; when the leading H1 was
    # consumed as the title (or there was none) the clamp keeps H2 at H2, so the effective shift is 0.
    ctx.heading_shift = int(
        any(
            isinstance(b, Heading) and b.level == 1 and b.id not in consumed and not ctx.is_child_block(b.id)
            for b in ctx.doc.blocks
        )
    )
    stack: list[tuple[int, HeadingInfo]] = []
    counters = [0] * 8
    for b in ctx.doc.blocks:
        if not isinstance(b, Heading) or b.id in consumed:
            continue
        shifted = b.level + 1
        while stack and stack[-1][0] >= shifted:
            stack.pop()
        level = stack[-1][1].level + 1 if stack else 2
        original = plain_spans(ctx, b.spans)
        text = render_spans(ctx, b.spans, heading=True)
        section = CHILD_SECTION_ATTR in b.attrs
        if ctx.profile.number_headings and not section:
            text = _SOURCE_NUM.sub("", text, count=1)
        if not section:
            text = _TRAIL_PUNCT.sub("", text).strip()
        text = text.strip() or original or "Untitled section"
        if b.attrs.get("hidden") == "true":
            text += " (hidden)"
        text, overflow = _truncate(text)
        number: str | None = None
        anchor: str | None = None
        if level <= 6:
            counters[level] += 1
            for deeper in range(level + 1, 8):
                counters[deeper] = 0
            number = ".".join(str(counters[i]) for i in range(2, level + 1))
            anchor = "sec-" + number.replace(".", "-")
        parents = [info for _, info in stack]
        label = f"{number} {text}" if number and ctx.profile.number_headings else text
        info = HeadingInfo(
            block_id=b.id,
            level=level,
            original_level=b.level,
            title=text,
            original_title=original,
            number=number if ctx.profile.number_headings else None,
            anchor=anchor if ctx.profile.anchors else None,
            path=[*[p.label for p in parents if p.level <= 6], label],
            time_start=b.provenance.time_start,
            time_end=b.provenance.time_end,
            overflow=overflow,
            child=ctx.children.prefix_of(b.id),
            child_section=section,
        )
        info.number = number if ctx.profile.number_headings and level <= 6 else None
        ctx.headings[b.id] = info
        stack.append((shifted, info))
        if anchor and ctx.profile.anchors:
            for key in (b.id, slugify(original), slugify(text), b.attrs.get("id", ""), b.attrs.get("anchor", "")):
                if key and key not in ctx.anchors:
                    ctx.anchors[key] = anchor
    return consumed


def heading_markdown(ctx: RenderContext, info: HeadingInfo) -> str:
    from intomd.render.text import fmt_time

    if info.level > 6:
        return f"**{info.title}**"
    parts = ["#" * info.level, info.label]
    if info.time_start is not None and ctx.profile.transcript.chapters:
        if info.time_end is not None and ctx.profile.anchors:
            parts.append(f"[{fmt_time(info.time_start)} - {fmt_time(info.time_end)}]")
        else:
            parts.append(f"[{fmt_time(info.time_start)}]")
    if info.anchor:
        parts.append(f"{{#{info.anchor}}}")
    return " ".join(parts)
