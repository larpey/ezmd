"""ezmd.render.plaintext: the `txt` export (docs/spec/part3.md section 19).

Derived from the IR, not from the Markdown: headings as their text on their own line, lists as `- ` lines,
tables as tab-separated rows under their caption, transcripts as `Speaker [HH:MM:SS]: text`, images as
`[Figure N: caption]`, no markers, no frontmatter except an optional `Title: ...` line (`txt_header=true`).
"""

from __future__ import annotations

from ezmd.ir import (
    Block,
    CodeBlock,
    Comment,
    ConversionResult,
    Equation,
    Figure,
    Footnote,
    Heading,
    Image,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    Quote,
    Raw,
    Slide,
    Table,
    TrackedChange,
    TranscriptSegment,
)
from ezmd.profiles import Profile
from ezmd.render.base import RenderedOutput, TokenCounter
from ezmd.render.blocks import LINE_BREAKS_ATTR, split_lines
from ezmd.render.context import RenderContext
from ezmd.render.headings import plan_headings, resolve_title
from ezmd.render.inline import plain_spans
from ezmd.render.markdown import RenderOptions, make_context, render_markdown
from ezmd.render.text import fmt_time
from ezmd.render.tokens import TiktokenCounter
from ezmd.render.transcript import prepare_speakers, transcript_paragraphs

__all__ = ["TextRenderer", "render_text"]


def _items(ctx: RenderContext, items: list[ListItem], ordered: bool, start: int, depth: int) -> list[str]:
    lines: list[str] = []
    for i, it in enumerate(items):
        marker = f"{start + i}." if ordered else "-"
        check = "" if it.checked is None else ("[x] " if it.checked else "[ ] ")
        lines.append("    " * depth + f"{marker} {check}{plain_spans(ctx, it.spans)}".rstrip())
        lines.extend(_items(ctx, it.children, False, 1, depth + 1))
    return lines


_NL = chr(10)


def _definition_lines(ctx: RenderContext, items: list[ListItem], depth: int) -> list[str]:
    lines: list[str] = []
    for it in items:
        text = plain_spans(ctx, it.spans)
        if text:
            lines.append("    " * depth + text)
        lines.extend(_definition_lines(ctx, it.children, depth + 1))
    return lines


def _definitions(ctx: RenderContext, items: list[ListItem]) -> str:
    """Definition list (ListBlock attrs kind=definition): the term on its own line, definitions indented."""
    entries = []
    for it in items:
        lines = [plain_spans(ctx, it.spans), *_definition_lines(ctx, it.children, 1)]
        entries.append(_NL.join(line for line in lines if line.strip()))
    return (_NL * 2).join(e for e in entries if e)


def _table(ctx: RenderContext, table: Table) -> str:
    ctx.table_count += 1
    grid = [[""] * table.n_cols for _ in range(table.n_rows)]
    for c in table.cells:
        text = plain_spans(ctx, c.spans).replace("\t", " ")
        for r in range(c.row, c.row + c.row_span):
            for col in range(c.col, c.col + c.col_span):
                grid[r][col] = text
    cap = plain_spans(ctx, table.caption) if table.caption else ""
    head = f"Table {ctx.table_count}: {cap}" if cap else f"Table {ctx.table_count}"
    return head + "\n" + "\n".join("\t".join(row).rstrip() for row in grid)


def _image(ctx: RenderContext, img: Image) -> str | None:
    if img.alt == "":
        return None
    ctx.figure_count += 1
    cap = plain_spans(ctx, img.caption) if img.caption else (img.generated_caption or img.alt or "")
    return f"[Figure {ctx.figure_count}: {cap}]" if cap else f"[Figure {ctx.figure_count}]"


def _transcript(ctx: RenderContext, run: list[TranscriptSegment]) -> list[str]:
    out: list[str] = []
    for para in transcript_paragraphs(ctx, run):
        body = " ".join(p for _, p in para.pieces).replace("\\", "")
        if para.on_screen:
            out.append(body)
        elif ctx.show_speakers:
            name = ctx.speaker_names.get(para.speaker or "", para.speaker or "Unknown speaker")
            out.append(f"{name} [{fmt_time(para.start)}]: {body}")
        else:
            out.append(f"[{fmt_time(para.start)}] {body}")
    return out


def _block(ctx: RenderContext, b: Block) -> list[str]:
    match b:
        case Heading():
            info = ctx.headings.get(b.id)
            return [info.label.replace("\\", "") if info else plain_spans(ctx, b.spans)]
        case Paragraph():
            if b.role in ("header", "footer", "page_number") and ctx.profile.furniture == "drop":
                return []
            if b.attrs.get(LINE_BREAKS_ATTR) == "hard":
                return [_NL.join(plain_spans(ctx, ln) for ln in split_lines(b.spans))]
            return [plain_spans(ctx, b.spans)]
        case Quote():
            return [plain_spans(ctx, b.spans) + (f" ({b.attribution})" if b.attribution else "")]
        case ListBlock() if b.attrs.get("kind") == "definition":
            return [_definitions(ctx, b.items)]
        case ListBlock():
            return ["\n".join(_items(ctx, b.items, b.ordered, b.start, 0))]
        case CodeBlock():
            return [b.code.strip("\n")]
        case Table():
            return [_table(ctx, b)]
        case Image():
            return [t for t in [_image(ctx, b)] if t]
        case Equation():
            return [(b.latex or b.text or "").strip()]
        case Link():
            text = (b.text or "").strip()
            return [f"{text}: {b.href}" if text and text != b.href else b.href]
        case Slide():
            return [f"Slide {b.index}: {b.title}" if b.title else f"Slide {b.index}"]
        case Raw():
            return [b.content.strip("\n")] if ctx.profile.raw_blocks == "fenced" else []
        case TrackedChange():
            return [plain_spans(ctx, b.spans)] if b.change in ("insert", "move") and not b.anchor_block_id else []
        case Comment() | Footnote() | Figure():
            return []
    return []


def render_text(result_md: RenderedOutput, ctx: RenderContext, title: str) -> str:
    del result_md
    consumed = plan_headings(ctx, title)
    prepare_speakers(ctx, ctx.doc)
    parts: list[str] = [f"Title: {title}"] if ctx.profile.txt_header else []
    parts.append(title)
    blocks = ctx.doc.blocks
    i = 0
    while i < len(blocks):
        b = blocks[i]
        i += 1
        if b.id in consumed:
            continue
        if isinstance(b, TranscriptSegment):
            run = [b]
            while i < len(blocks) and isinstance(blocks[i], TranscriptSegment):
                nxt = blocks[i]
                if isinstance(nxt, TranscriptSegment):
                    run.append(nxt)
                i += 1
            parts.extend(_transcript(ctx, run))
            continue
        parts.extend(p for p in _block(ctx, b) if p.strip())
    footnotes = [b for b in blocks if isinstance(b, Footnote)]
    for n, fn in enumerate(footnotes, start=1):
        parts.append(f"[{n}] {plain_spans(ctx, fn.spans)}")
    text = "\n\n".join(parts)
    return "\n".join(line.rstrip() for line in text.split("\n")).rstrip("\n") + "\n"


class TextRenderer:
    format = "txt"

    def __init__(self, counter: TokenCounter | None = None, options: RenderOptions | None = None) -> None:
        self.counter: TokenCounter = counter or TiktokenCounter()
        self.options = options or RenderOptions()

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput:
        md = render_markdown(result, profile, self.options, self.counter)
        ctx = make_context(result, profile)
        text = render_text(md, ctx, resolve_title(ctx))
        return RenderedOutput(
            markdown=text,
            frontmatter=md.frontmatter,
            sidecar=None,
            chunks=[],
            attachments=md.attachments,
            tokens=self.counter.count(text),
            truncated=md.truncated,
            warnings=md.warnings,
            injection_risk=md.injection_risk,
            body=text,
        )
