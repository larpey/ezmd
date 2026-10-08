"""intomd.render.units: walk the Document and produce body Units in reading order.

Groups runs (transcript segments, standalone links), keeps figures atomic (image + caption + chart table),
drops page furniture, collects abstracts for the summary head, attaches anchored comments and tracked
changes to their blocks, and records footnote references per unit. Every known block type is handled;
the `intomd-unrendered` fence is reserved for objects that are not IR blocks at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from intomd.ir import (
    Block,
    CodeBlock,
    Comment,
    Equation,
    Figure,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    Link,
    ListBlock,
    PageBreak,
    Paragraph,
    Quote,
    Raw,
    Slide,
    SourceType,
    Table,
    TrackedChange,
    TranscriptSegment,
    WarningKind,
)
from intomd.render import blocks as br
from intomd.render.context import HeadingInfo, RenderContext, Unit
from intomd.render.headings import heading_markdown
from intomd.render.inline import plain_spans, render_spans
from intomd.render.tables import render_table
from intomd.render.text import fmt_time
from intomd.render.transcript import render_transcript_run

__all__ = ["BuildResult", "build_units"]

_FURNITURE = {"header", "footer", "page_number"}


@dataclass(slots=True)
class BuildResult:
    units: list[Unit]
    summary: list[str] = field(default_factory=list)


def _prepass(ctx: RenderContext) -> set[str]:
    """Footnote index, anchored annotations, furniture to keep. Returns ids handled out of band."""
    skip: set[str] = set()
    pages_by_text: dict[str, set[int]] = {}
    has_changes = has_comments = False
    for b in ctx.doc.blocks:
        if isinstance(b, Footnote):
            ctx.footnotes[b.id] = b
            skip.add(b.id)
        elif isinstance(b, Comment | TrackedChange):
            has_comments |= isinstance(b, Comment)
            has_changes |= isinstance(b, TrackedChange)
            if b.anchor_block_id:
                skip.add(b.id)
                note = br.annotation_text(ctx, b)
                if note:
                    ctx.annotations.setdefault(b.anchor_block_id, []).append(note)
        elif isinstance(b, Paragraph) and b.role in ("header", "footer"):
            key = re.sub(r"\d+", "#", plain_spans(ctx, b.spans).casefold())
            pages_by_text.setdefault(key, set()).add(b.provenance.source_page or 0)
    if has_changes:
        ctx.warn(
            WarningKind.TRACKED_CHANGES_PRESENT,
            "The source contains tracked changes; "
            + ("they are annotated." if ctx.profile.tracked_changes == "annotate" else "they were resolved."),
        )
    if has_comments:
        ctx.warn(
            WarningKind.COMMENTS_PRESENT,
            "The source contains review comments; "
            + ("they are shown inline." if ctx.profile.comments == "inline" else "they were omitted."),
        )
    many_pages = (ctx.doc.metadata.pages or 0) > 1 or len({p for s in pages_by_text.values() for p in s}) > 1
    for b in ctx.doc.blocks:
        if isinstance(b, Paragraph) and b.role in ("header", "footer"):
            key = re.sub(r"\d+", "#", plain_spans(ctx, b.spans).casefold())
            if many_pages and len(pages_by_text.get(key, set())) <= 1:
                ctx.keep_furniture.add(b.id)
    return skip


def _decorative_refs(ctx: RenderContext) -> set[str]:
    pages: dict[str, set[int]] = {}
    for b in ctx.doc.blocks:
        if isinstance(b, Image) and b.provenance.source_page is not None:
            pages.setdefault(b.ref, set()).add(b.provenance.source_page)
    return {ref for ref, ps in pages.items() if len(ps) >= 3}


def _slide_units(ctx: RenderContext, slide: Slide, has_headings: bool) -> list[Unit]:
    parent = ctx.current_heading
    level = min(6, parent.level + 1) if (has_headings and parent and parent.level <= 6) else 2
    title = f"Slide {slide.index}: {slide.title}" if slide.title else f"Slide {slide.index}"
    info = HeadingInfo(
        block_id=slide.id,
        level=level,
        original_level=level,
        title=title,
        original_title=title,
        number=None,
        anchor=f"slide-{slide.index}" if ctx.profile.anchors else None,
        path=[*(parent.path if parent and has_headings else []), title],
        time_start=slide.provenance.time_start,
        time_end=slide.provenance.time_end,
    )
    marker = f"<!-- slide {slide.index} -->\n" if ctx.profile.page_markers else ""
    return [
        Unit(
            text=marker + heading_markdown(ctx, info),
            kind="heading",
            block_ids=[slide.id],
            heading=info,
            time_start=info.time_start,
            time_end=info.time_end,
        )
    ]


def _figure_units(ctx: RenderContext, fig: Figure, children: list[Block]) -> list[Unit]:
    images = [c for c in children if isinstance(c, Image)]
    captions = [c for c in children if isinstance(c, Paragraph) and c.role == "caption"]
    caption: list[InlineSpan] | None = captions[0].spans if captions else None
    used = {c.id for c in captions[:1]}
    parts: list[Unit] = []
    for i, img in enumerate(images):
        unit = br.render_image(ctx, img, caption if i == 0 else None, [fig.id, *used] if i == 0 else None)
        if unit:
            parts.append(unit)
    for child in children:
        if isinstance(child, Table):
            parts.append(render_table(ctx, child, None if images else caption))
        elif not isinstance(child, Image) and child.id not in used:
            parts.extend(_block_units(ctx, child, False))
    if not parts:
        return []
    merged = Unit(
        text="\n\n".join(p.text for p in parts),
        kind="figure",
        block_ids=[fig.id, *[i for p in parts for i in p.block_ids]],
        page=fig.provenance.source_page or parts[0].page,
        sidecar_key=parts[0].sidecar_key,
    )
    merged.fn_refs = [r for p in parts for r in p.fn_refs]
    return [merged]


def _heading_units(ctx: RenderContext, b: Heading) -> list[Unit]:
    info = ctx.headings[b.id]
    ctx.current_heading = info
    label = b.provenance.source_label
    marker = ""
    if ctx.doc.metadata.source_type == SourceType.XLSX and label and ctx.profile.page_markers:
        marker = f'<!-- sheet "{label.replace(chr(34), chr(39))}" -->\n'
    units = [
        Unit(
            text=marker + heading_markdown(ctx, info),
            kind="heading",
            block_ids=[b.id],
            heading=info,
            page=b.provenance.source_page,
            time_start=info.time_start,
            time_end=info.time_end,
        )
    ]
    if info.overflow:
        units.append(Unit(text=info.overflow, kind="prose", block_ids=[b.id], page=b.provenance.source_page))
    return units


def _paragraph_unit(ctx: RenderContext, b: Paragraph) -> list[Unit]:
    if b.role in _FURNITURE and ctx.profile.furniture == "drop":
        keep = b.role != "page_number" and b.id in ctx.keep_furniture
        if not keep:
            ctx.furniture_removed += 1
            return []
    unit = br.render_paragraph(ctx, b)
    return [unit] if unit else []


def _annotation_unit(ctx: RenderContext, b: Comment | TrackedChange) -> list[Unit]:
    text = br.annotation_text(ctx, b)
    return [Unit(text=text, kind="prose", block_ids=[b.id], page=b.provenance.source_page)] if text else []


def _block_units(ctx: RenderContext, b: Block, has_headings: bool) -> list[Unit]:
    match b:
        case Heading():
            return _heading_units(ctx, b)
        case Paragraph():
            return _paragraph_unit(ctx, b)
        case Table():
            return [render_table(ctx, b)]
        case ListBlock():
            return [u for u in [br.render_list(ctx, b)] if u]
        case CodeBlock():
            return [br.render_code(ctx, b)]
        case Image():
            return [u for u in [br.render_image(ctx, b)] if u]
        case Equation():
            return [u for u in [br.render_equation(ctx, b)] if u]
        case Quote():
            return [u for u in [br.render_quote(ctx, b)] if u]
        case Raw():
            return [u for u in [br.render_raw(ctx, b)] if u]
        case Link():
            return [u for u in [br.render_links(ctx, [b])] if u]
        case Slide():
            return _slide_units(ctx, b, has_headings)
        case Comment() | TrackedChange():
            return _annotation_unit(ctx, b)
        case TranscriptSegment():
            return render_transcript_run(ctx, [b])
        case Footnote() | PageBreak() | Figure():
            return []
    return [Unit(text=f"```intomd-unrendered\n{type(b).__name__} {getattr(b, 'id', '')}\n```", kind="raw")]


def build_units(ctx: RenderContext, consumed: set[str]) -> BuildResult:
    skip = _prepass(ctx) | consumed
    decorative = _decorative_refs(ctx)
    blocks = ctx.doc.blocks
    has_headings = any(isinstance(b, Heading) for b in blocks)
    out = BuildResult(units=[])
    page_hint: int | None = None
    i = 0
    while i < len(blocks):
        b = blocks[i]
        i += 1
        if b.id in skip:
            continue
        if isinstance(b, PageBreak):
            page_hint = b.page_number
            continue
        if isinstance(b, Image) and b.ref in decorative:
            ctx.images_dropped_decorative += 1
            continue
        if isinstance(b, Paragraph) and b.role == "abstract" and ctx.profile.summary_blockquote:
            out.summary.append(render_spans(ctx, b.spans))
            continue
        if isinstance(b, TranscriptSegment | Link):
            run: list[Block] = [b]
            while i < len(blocks) and type(blocks[i]) is type(b) and blocks[i].id not in skip:
                run.append(blocks[i])
                i += 1
            if isinstance(b, Link):
                units = [u for u in [br.render_links(ctx, [x for x in run if isinstance(x, Link)])] if u]
            else:
                units = render_transcript_run(ctx, [x for x in run if isinstance(x, TranscriptSegment)])
        elif isinstance(b, Figure):
            children: list[Block] = []
            while i < len(blocks) and blocks[i].parent_id == b.id:
                children.append(blocks[i])
                i += 1
            units = _figure_units(ctx, b, [c for c in children if c.id not in skip])
        else:
            units = _block_units(ctx, b, has_headings)
        refs = ctx.take_refs()
        if units:
            if refs:
                units[-1].fn_refs = [*units[-1].fn_refs, *refs]
            for u in units:
                if u.page is None and u.kind != "marker":
                    u.page = page_hint if b.provenance.source_page is None else b.provenance.source_page
                if u.page is not None:
                    page_hint = u.page
                label = b.provenance.source_label
                if label and u.page is not None and label != str(u.page) and not isinstance(b, Heading):
                    u.page_label = label
            out.units.extend(units)
    return out


def time_range(start: float | None, end: float | None) -> str:
    if start is None:
        return ""
    return f"[{fmt_time(start)} - {fmt_time(end)}]" if end is not None else f"[{fmt_time(start)}]"
