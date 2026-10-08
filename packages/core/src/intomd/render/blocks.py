"""intomd.render.blocks: Markdown for individual IR blocks (docs/spec/part3.md section 14).

Each function returns a `Unit` (or None when the block is dropped by the profile). Tables live in
`tables.py`, transcripts in `transcript.py`; grouping of runs and figures happens in `units.py`.
"""

from __future__ import annotations

from intomd.ir import (
    CodeBlock,
    Comment,
    Equation,
    Image,
    InlineSpan,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    Quote,
    Raw,
    TrackedChange,
    WarningKind,
)
from intomd.render.context import RenderContext, Unit
from intomd.render.inline import plain_spans, render_spans
from intomd.render.links import clean_url
from intomd.render.tables import render_table
from intomd.render.text import collapse_ws, escape_inline, fence_for

__all__ = [
    "annotation_text",
    "render_code",
    "render_equation",
    "render_image",
    "render_links",
    "render_list",
    "render_paragraph",
    "render_quote",
    "render_raw",
]

_CALLOUTS = {"note", "tip", "warning", "caution", "important", "example", "quote"}


def _with_annotations(ctx: RenderContext, block_id: str, text: str) -> str:
    notes = ctx.annotations.get(block_id)
    return f"{text} {' '.join(notes)}".strip() if notes else text


def render_paragraph(ctx: RenderContext, p: Paragraph) -> Unit | None:
    text = render_spans(ctx, p.spans)
    text = _with_annotations(ctx, p.id, text)
    if not text:
        return None
    callout = p.attrs.get("callout")
    if callout:
        label = callout.strip().title() if callout.strip().lower() not in _CALLOUTS else callout.strip().capitalize()
        return Unit(text=f"> **{label}:** {text}", kind="quote", block_ids=[p.id], page=p.provenance.source_page)
    if p.attrs.get("slide_part") == "notes":
        text = f"**Notes:** {text}"
    elif p.role == "title":
        text = f"**{plain_spans(ctx, p.spans)}**"
    elif p.role == "subtitle":
        text = f"*{text}*"
    return Unit(text=text, kind="prose", block_ids=[p.id], page=p.provenance.source_page)


def _item_lines(ctx: RenderContext, items: list[ListItem], ordered: bool, start: int, depth: int) -> list[str]:
    lines: list[str] = []
    for offset, item in enumerate(items):
        numbered = "1." if ctx.profile.compact_lists else f"{start + offset}."
        marker = numbered if ordered else "-"
        check = "" if item.checked is None else ("[x] " if item.checked else "[ ] ")
        text = render_spans(ctx, item.spans)
        lines.append(("    " * depth + f"{marker} {check}{text}").rstrip())
        if item.children:
            lines.extend(_item_lines(ctx, item.children, item.children_ordered, item.children_start, depth + 1))
    return lines


def render_list(ctx: RenderContext, block: ListBlock) -> Unit | None:
    if not block.items:
        return None
    page = block.provenance.source_page
    only = block.items[0]
    if ctx.profile.compact_lists and len(block.items) == 1 and not only.children and only.checked is None:
        text = render_spans(ctx, only.spans)
        return Unit(text=text, kind="prose", block_ids=[block.id], page=page) if text else None
    items: list[str] = []
    for offset, item in enumerate(block.items):
        lines = _item_lines(ctx, [item], block.ordered, block.start + offset, 0)
        items.append("\n".join(lines))
    return Unit(text="\n".join(items), kind="list", block_ids=[block.id], page=page, list_items=items)


def render_code(ctx: RenderContext, block: CodeBlock) -> Unit:
    code = "\n".join(line.rstrip() for line in block.code.strip("\n").split("\n"))
    fence = fence_for(code)
    lang = (block.language or "").strip().split()[0] if (block.language or "").strip() else ""
    text = f"{fence}{lang}\n{code}\n{fence}" if code else f"{fence}{lang}\n{fence}"
    if block.filename:
        text = f"File: `{block.filename}`\n\n{text}"
    return Unit(text=text, kind="code", block_ids=[block.id], page=block.provenance.source_page)


def render_equation(ctx: RenderContext, block: Equation) -> Unit | None:
    page = block.provenance.source_page
    if block.latex and block.latex.strip():
        latex = block.latex.strip()
        if latex.startswith("$$") and latex.endswith("$$") and len(latex) > 4:
            latex = latex[2:-2].strip()
        return Unit(text=f"$$\n{latex}\n$$", kind="equation", block_ids=[block.id], page=page)
    if block.text and block.text.strip():
        ctx.warn(WarningKind.EQUATION_AS_TEXT, "An equation could not be converted to LaTeX.", block_id=block.id)
        from intomd.render.text import code_span

        text = code_span(collapse_ws(block.text.strip())) + "\n<!-- intomd: equation not converted -->"
        return Unit(text=text, kind="equation", block_ids=[block.id], page=page)
    return None


def _quote_paragraphs(spans: list[InlineSpan]) -> list[list[InlineSpan]]:
    """Split quote spans into paragraphs at spans that consist only of a blank-line break."""
    groups: list[list[InlineSpan]] = [[]]
    for s in spans:
        if s.footnote_ref is None and "\n\n" in s.text and not s.text.strip():
            groups.append([])
        else:
            groups[-1].append(s)
    return [g for g in groups if g]


def render_quote(ctx: RenderContext, block: Quote) -> Unit | None:
    paras = [render_spans(ctx, g) for g in _quote_paragraphs(block.spans)]
    paras = [p for p in paras if p]
    if not paras:
        return None
    paras[-1] = _with_annotations(ctx, block.id, paras[-1])
    prefix = "> " * block.depth
    callout = block.attrs.get("callout")
    if callout:
        paras[0] = f"**{callout.strip().capitalize()}:** {paras[0]}"
    lines: list[str] = []
    for i, p in enumerate(paras):
        if i:
            lines.append(prefix.rstrip())
        lines.append(prefix + p)
    if block.attribution:
        lines.append(prefix.rstrip())
        lines.append(prefix + "Source: " + escape_inline(collapse_ws(block.attribution).strip()))
    return Unit(text="\n".join(lines), kind="quote", block_ids=[block.id], page=block.provenance.source_page)


def render_raw(ctx: RenderContext, block: Raw) -> Unit | None:
    if ctx.profile.raw_blocks == "drop" or not block.content.strip():
        return None
    content = "\n".join(line.rstrip() for line in block.content.strip("\n").split("\n"))
    fence = fence_for(content)
    fmt = block.format.strip().split()[0] if block.format.strip() else "text"
    return Unit(
        text=f"{fence}{fmt}\n{content}\n{fence}", kind="raw", block_ids=[block.id], page=block.provenance.source_page
    )


def render_links(ctx: RenderContext, links: list[Link]) -> Unit | None:
    lines: list[str] = []
    for link in links:
        label = escape_inline(collapse_ws(link.text or "").strip())
        url = clean_url(link.href, ctx.base_url, lambda frag: ctx.anchors.get(frag) if ctx.profile.anchors else None)
        if url is None:
            if label:
                lines.append(f"- {label}")
            continue
        ctx.links.record(link.text or "", url, link.href)
        mode = ctx.profile.links
        if not label or label == url:
            lines.append(f"- {url}")
        elif mode == "inline":
            lines.append(f"- [{label}]({url})")
        elif mode == "numbered_list":
            ctx.links.number(url)
            lines.append(f"- {label}")
        else:
            lines.append(f"- {label}: {url}")
    if not lines:
        return None
    return Unit(
        text="\n".join(lines), kind="links", block_ids=[b.id for b in links], page=links[0].provenance.source_page
    )


def annotation_text(ctx: RenderContext, block: Comment | TrackedChange) -> str | None:
    """CriticMarkup for a comment or tracked change, or the accepted/rejected text, per profile."""
    if isinstance(block, Comment):
        if ctx.profile.comments != "inline":
            return None
        body = plain_spans(ctx, block.spans)
        who = f"{block.author}: " if block.author else ""
        return "{>>" + who + body + "<<}" if body else None
    mode = ctx.profile.tracked_changes
    text = render_spans(ctx, block.spans)
    if not text or mode == "drop":
        return None
    if mode == "annotate":
        return {
            "insert": "{++" + text + "++}",
            "delete": "{--" + text + "--}",
            "format": "{>>format change: " + text + "<<}",
            "move": "{>>moved: " + text + "<<}",
        }[block.change]
    keep = {"accept": ("insert", "move"), "reject": ("delete", "move")}[mode]
    return text if block.change in keep else None


def _bbox(block: Image) -> str | None:
    box = block.provenance.bbox
    if box is None:
        return None
    if box.page_width and box.page_height:
        vals = (box.x0 / box.page_width, box.y0 / box.page_height, box.x1 / box.page_width, box.y1 / box.page_height)
    elif max(box.x1, box.y1) <= 1.0:
        vals = (box.x0, box.y0, box.x1, box.y1)
    else:
        return None
    return ",".join(f"{v:.2f}" for v in vals)


def render_image(
    ctx: RenderContext, block: Image, caption: list[InlineSpan] | None = None, extra_block_ids: list[str] | None = None
) -> Unit | None:
    rules = ctx.profile.images
    tiny = (block.width is not None and block.width < rules.min_pixels) or (
        block.height is not None and block.height < rules.min_pixels
    )
    if block.alt == "" or tiny or block.attrs.get("decorative") == "true":
        ctx.images_dropped_decorative += 1
        return None
    ctx.figure_count += 1
    n = ctx.figure_count
    page = block.provenance.source_page
    ref = block.ref if not block.ref.startswith("data:") else f"images/fig-{n:02d}.png"
    ref = ref.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    gen = collapse_ws(block.generated_caption or "").strip()
    alt_src = collapse_ws(block.alt or "").strip()
    alt = (alt_src or gen or f"Figure {n}").replace("[", "\\[").replace("]", "\\]")
    cap_spans = block.caption or caption
    cap = render_spans(ctx, cap_spans) if cap_spans else ""
    lines: list[str] = []
    if rules.mode != "caption_only":
        title = block.attrs.get("title")
        title_part = f' "{title.replace(chr(34), chr(39))}"' if title else ""
        lines.append(f"![{alt}]({ref}{title_part})")
    if rules.mode != "reference_only":
        if cap:
            lines.append(f"Figure {n}: {cap}")
        elif gen:
            lines.append(
                f"Figure {n} (page {page}): {escape_inline(gen)}"
                if page
                else f"Figure {n} (generated): {escape_inline(gen)}"
            )
        elif rules.mode == "caption_only":
            lines.append(f"Figure {n}: {escape_inline(alt_src)}" if alt_src else f"Figure {n}")
        elif ctx.profile.section_ids:
            lines.append(f"Figure {n}")
    if ctx.profile.image_comments and rules.mode != "caption_only":
        attrs = [ref]
        if page is not None:
            attrs.append(f"page={page}")
        bbox = _bbox(block)
        if bbox:
            attrs.append(f"bbox={bbox}")
        lines.append(f"<!-- image: {' '.join(attrs)} -->")
    if not lines:
        return None
    text = "\n".join(lines)
    ids = [block.id, *(extra_block_ids or [])]
    if block.chart_data is not None and rules.chart_table:
        table_unit = render_table(ctx, block.chart_data)
        text = f"{text}\n\n{table_unit.text}"
    entry: dict[str, object] = {
        "number": n,
        "block_id": block.id,
        "ref": block.ref,
        "alt": block.alt,
        "caption": plain_spans(ctx, cap_spans) if cap_spans else None,
        "generated_caption": block.generated_caption,
        "ocr_text": block.ocr_text,
        "page": page,
        "bbox": _bbox(block),
    }
    key = ("figures", ctx.side("figures", entry))
    return Unit(text=text, kind="figure", block_ids=ids, page=page, sidecar_key=key)
