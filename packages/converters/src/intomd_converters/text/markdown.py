"""text.markdown_passthrough: parse Markdown into the IR (docs/spec/part1.md P0-T06).

Uses markdown-it-py (MIT) in CommonMark mode with tables, strikethrough, footnotes, and task lists.
The goal is that rendering a Markdown input in the `full` profile reproduces its structure:
headings, paragraphs, nested lists, code, quotes, links (inline spans), images (Image blocks),
tables, footnotes, and raw HTML blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import (
    Block,
    CodeBlock,
    Document,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    InlineStyle,
    ListBlock,
    ListItem,
    Metadata,
    Paragraph,
    Provenance,
    Quote,
    Raw,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
)
from intomd.registry import ConvertOptions
from intomd_converters.text.plain import decode_text_detailed


def footnote_id(label: str) -> str:
    """Stable block id for a footnote label; InlineSpan.footnote_ref points at it."""
    return "fn-" + "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)[:64]


def _parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    md.use(footnote_plugin).use(tasklists_plugin).use(front_matter_plugin)
    return md


@dataclass(slots=True)
class _Ctx:
    source: str
    footnote_ids: dict[str, int] = field(default_factory=dict)
    """footnote label -> index into blocks, for wiring footnote_ref after finalize."""
    images: list[Image] = field(default_factory=list)

    def prov(self, tok: Token) -> Provenance:
        if tok.map:
            return Provenance(source=self.source, line_start=tok.map[0] + 1, line_end=tok.map[1])
        return Provenance(source=self.source)


def _inline_spans(
    tok: Token | None, ctx: _Ctx, *, collect_images: bool = True, first_softbreak: str = " "
) -> list[InlineSpan]:
    """Flatten an `inline` token's children into styled spans. `first_softbreak` replaces the first soft line
    break (callout titles keep their own line)."""
    if tok is None or not tok.children:
        return [InlineSpan(text=tok.content if tok else "")] if tok and tok.content else []
    spans: list[InlineSpan] = []
    styles: list[InlineStyle] = []
    href: list[str] = []
    for c in tok.children:
        t = c.type
        if t == "text":
            _push(spans, c.content, styles, href[-1] if href else None)
        elif t in ("softbreak", "hardbreak"):
            brk = "\n" if t == "hardbreak" else first_softbreak
            if t == "softbreak":
                first_softbreak = " "
            if brk == "\n\n":
                spans.append(InlineSpan(text=brk))  # a standalone span: the quote renderer splits paragraphs there
            else:
                _push(spans, brk, styles, href[-1] if href else None)
        elif t == "code_inline":
            _push(spans, c.content, [*styles, InlineStyle.CODE], href[-1] if href else None)
        elif t in ("strong_open", "em_open", "s_open"):
            styles.append({"strong_open": InlineStyle.BOLD, "em_open": InlineStyle.ITALIC}.get(t, InlineStyle.STRIKE))
        elif t in ("strong_close", "em_close", "s_close"):
            if styles:
                styles.pop()
        elif t == "link_open":
            href.append(str(c.attrGet("href") or ""))
        elif t == "link_close":
            if href:
                href.pop()
        elif t == "image":
            alt = c.content or "".join(ch.content for ch in (c.children or []))
            if collect_images:
                ctx.images.append(
                    Image(
                        ref=str(c.attrGet("src") or ""),
                        alt=alt or None,
                        attrs={"title": str(c.attrGet("title"))} if c.attrGet("title") else {},
                        provenance=Provenance(source=ctx.source),
                    )
                )
            elif alt:
                _push(spans, alt, styles, href[-1] if href else None)
        elif t == "footnote_ref":
            label = str(c.meta.get("label", c.meta.get("id", "")))
            spans.append(InlineSpan(text=f"[^{label}]", footnote_ref=footnote_id(label)))
        elif t == "html_inline":
            _push(spans, c.content, styles, href[-1] if href else None)
        else:
            if c.content:
                _push(spans, c.content, styles, href[-1] if href else None)
    return spans


def _push(spans: list[InlineSpan], text: str, styles: list[InlineStyle], href: str | None) -> None:
    if not text:
        return
    st = sorted(set(styles), key=list(InlineStyle).index)
    last = spans[-1] if spans else None
    if last and last.styles == st and last.href == href and last.footnote_ref is None and last.text.strip():
        spans[-1] = InlineSpan(text=spans[-1].text + text, styles=st, href=href)
        return
    spans.append(InlineSpan(text=text, styles=st, href=href))


def _find_close(tokens: list[Token], i: int) -> int:
    """Index of the token closing the one opened at `i` (same level, nesting -1)."""
    level = tokens[i].level
    close_type = tokens[i].type.replace("_open", "_close")
    j = i + 1
    while j < len(tokens):
        if tokens[j].type == close_type and tokens[j].level == level:
            return j
        j += 1
    return len(tokens) - 1


def _parse_list(tokens: list[Token], i: int, ctx: _Ctx) -> tuple[list[ListItem], int]:
    """Parse list items between tokens[i] (bullet/ordered_list_open) and its close."""
    end = _find_close(tokens, i)
    items: list[ListItem] = []
    j = i + 1
    while j < end:
        tok = tokens[j]
        if tok.type == "list_item_open":
            item_end = _find_close(tokens, j)
            spans: list[InlineSpan] = []
            children: list[ListItem] = []
            checked: bool | None = None
            children_ordered = False
            children_start = 1
            cls = str(tok.attrGet("class") or "")
            k = j + 1
            while k < item_end:
                t = tokens[k]
                if t.type == "inline":
                    sp = _inline_spans(t, ctx, collect_images=False)
                    if checked is None and "task-list-item" in cls and t.children:
                        first = t.children[0]
                        if first.type == "html_inline" and "checkbox" in first.content:
                            checked = "checked" in first.content
                            sp = _inline_spans(_strip_first_child(t), ctx, collect_images=False)
                    if spans:
                        spans.append(InlineSpan(text=" "))
                    spans.extend(sp)
                    if spans and spans[0].text.startswith(" "):
                        spans[0] = InlineSpan(**{**spans[0].model_dump(), "text": spans[0].text.lstrip()})
                    k += 1
                elif t.type in ("bullet_list_open", "ordered_list_open"):
                    if not children:
                        children_ordered = t.type == "ordered_list_open"
                        children_start = int(t.attrGet("start") or 1) if children_ordered else 1
                    sub, k = _parse_list(tokens, k, ctx)
                    children.extend(sub)
                elif t.type == "fence" or t.type == "code_block":
                    spans.append(InlineSpan(text=t.content.rstrip("\n"), styles=[InlineStyle.CODE]))
                    k += 1
                else:
                    k += 1
            items.append(
                ListItem(
                    spans=spans,
                    children=children,
                    children_ordered=children_ordered,
                    children_start=children_start,
                    checked=checked,
                    provenance=ctx.prov(tok),
                )
            )
            j = item_end + 1
        else:
            j += 1
    return items, end + 1


def _strip_first_child(tok: Token) -> Token:
    clone = tok.copy()
    clone.children = (tok.children or [])[1:]
    return clone


def _parse_table(tokens: list[Token], i: int, ctx: _Ctx) -> tuple[Table, int]:
    end = _find_close(tokens, i)
    cells: list[TableCell] = []
    row = -1
    col = 0
    header_rows = 0
    in_head = False
    for t in tokens[i + 1 : end]:
        if t.type == "thead_open":
            in_head = True
        elif t.type == "thead_close":
            in_head = False
        elif t.type == "tr_open":
            row += 1
            col = 0
            if in_head:
                header_rows += 1
        elif t.type == "inline":
            cells.append(
                TableCell(spans=_inline_spans(t, ctx, collect_images=False), row=row, col=col, is_header=in_head)
            )
            col += 1
    n_rows = row + 1
    n_cols = max((c.col + 1 for c in cells), default=0)
    return (
        Table(cells=cells, n_rows=n_rows, n_cols=n_cols, header_rows=header_rows, provenance=ctx.prov(tokens[i])),
        end + 1,
    )


_CALLOUT = re.compile(r"^\[![A-Za-z][\w-]*\][+-]?")
"""An Obsidian/GitHub callout marker (`> [!warning] Title`): its title line stays a paragraph of its own."""


def _callout(spans: list[InlineSpan]) -> tuple[list[InlineSpan], dict[str, str]]:
    """Move a leading callout marker (`[!warning]`, `[!note]-`) into attrs["callout"] (rendered as a label)."""
    m = _CALLOUT.match(spans[0].text) if spans else None
    if m is None:
        return spans, {}
    kind = m.group(0).split("]")[0][2:]
    attrs = {"callout": kind}
    if m.group(0).endswith(("+", "-")):
        attrs["callout_fold"] = "open" if m.group(0).endswith("+") else "closed"
    rest = spans[0].text[m.end() :].lstrip()
    head = [spans[0].model_copy(update={"text": rest})] if rest else []
    return head + spans[1:], attrs


def _blockquote_spans(tokens: list[Token], ctx: _Ctx) -> list[InlineSpan]:
    spans: list[InlineSpan] = []
    for t in tokens:
        if t.type == "inline":
            callout = not spans and _CALLOUT.match(t.content) is not None
            if spans:
                spans.append(InlineSpan(text="\n\n"))
            title_break = "\n\n" if callout else " "
            spans.extend(_inline_spans(t, ctx, collect_images=False, first_softbreak=title_break))
        elif t.type in ("fence", "code_block"):
            if spans:
                spans.append(InlineSpan(text="\n\n"))
            spans.append(InlineSpan(text=t.content.rstrip("\n"), styles=[InlineStyle.CODE]))
    return spans


def parse_markdown(text: str, source: str) -> tuple[list[Block], dict[str, str]]:
    """Return IR blocks and any YAML front matter as raw text under key 'front_matter'."""
    tokens = _parser().parse(text)
    ctx = _Ctx(source=source)
    blocks: list[Block] = []
    extras: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type
        if t == "front_matter":
            extras["front_matter"] = tok.content
            i += 1
        elif t == "heading_open":
            inline = tokens[i + 1]
            blocks.append(
                Heading(
                    level=int(tok.tag[1]),
                    spans=_inline_spans(inline, ctx, collect_images=False),
                    provenance=ctx.prov(tok),
                )
            )
            i += 3
        elif t == "paragraph_open":
            inline = tokens[i + 1]
            ctx.images.clear()
            spans = _inline_spans(inline, ctx)
            if any(s.text.strip() for s in spans):
                blocks.append(Paragraph(spans=_strip_spans(spans), provenance=ctx.prov(tok)))
            for img in ctx.images:
                img.provenance = ctx.prov(tok)
                blocks.append(img)
            ctx.images.clear()
            i += 3
        elif t in ("bullet_list_open", "ordered_list_open"):
            prov = ctx.prov(tok)
            items, i = _parse_list(tokens, i, ctx)
            start = int(tok.attrGet("start") or 1) if t == "ordered_list_open" else 1
            blocks.append(ListBlock(ordered=t == "ordered_list_open", start=start, items=items, provenance=prov))
        elif t in ("fence", "code_block"):
            lang = tok.info.strip().split()[0] if tok.info.strip() else None
            blocks.append(CodeBlock(code=tok.content.rstrip("\n"), language=lang, provenance=ctx.prov(tok)))
            i += 1
        elif t == "blockquote_open":
            end = _find_close(tokens, i)
            depth = 1
            inner = tokens[i + 1 : end]
            while inner and inner[0].type == "blockquote_open" and _find_close(inner, 0) == len(inner) - 1:
                depth += 1
                inner = inner[1:-1]
            qspans, qattrs = _callout(_blockquote_spans(inner, ctx))
            blocks.append(Quote(spans=qspans, depth=depth, provenance=ctx.prov(tok), attrs=qattrs))
            i = end + 1
        elif t == "table_open":
            table, i = _parse_table(tokens, i, ctx)
            blocks.append(table)
        elif t == "html_block":
            blocks.append(Raw(format="html", content=tok.content.rstrip("\n"), provenance=ctx.prov(tok)))
            i += 1
        elif t == "footnote_block_open":
            end = _find_close(tokens, i)
            j = i + 1
            while j < end:
                if tokens[j].type == "footnote_open":
                    fend = _find_close(tokens, j)
                    label = str(tokens[j].meta.get("label", tokens[j].meta.get("id", "")))
                    spans = []
                    for ft in tokens[j + 1 : fend]:
                        if ft.type == "inline":
                            if spans:
                                spans.append(InlineSpan(text=" "))
                            spans.extend(_inline_spans(ft, ctx, collect_images=False))
                    spans = [s for s in spans if s.footnote_ref is None or s.text]
                    blocks.append(
                        Footnote(
                            id=footnote_id(label),
                            marker=label,
                            spans=_strip_spans(spans),
                            provenance=ctx.prov(tokens[j]),
                        )
                    )
                    j = fend + 1
                else:
                    j += 1
            i = end + 1
        else:
            i += 1
    return blocks, extras


def _strip_spans(spans: list[InlineSpan]) -> list[InlineSpan]:
    out = [s for s in spans if s.text]
    if out:
        out[0] = InlineSpan(**{**out[0].model_dump(), "text": out[0].text.lstrip()})
        out[-1] = InlineSpan(**{**out[-1].model_dump(), "text": out[-1].text.rstrip()})
    return [s for s in out if s.text]


class MarkdownPassthroughConverter:
    id = "text.markdown_passthrough"
    family = "text"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/markdown",)

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if mime == "text/markdown":
            return 0.95
        if mime == "text/plain" and ref.display.lower().endswith((".md", ".markdown", ".mdx")):
            return 0.95
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raw = ref.read()
        meta = Metadata(source=ref.display, source_type=SourceType.MARKUP, mime="text/markdown")
        doc = Document(metadata=meta)
        if not raw.strip():
            doc.warnings.append(
                Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="The file contains no text.")
            )
            return doc.finalize()
        text, encoding, guessed, confidence = decode_text_detailed(raw)
        stats = CleanStats()
        text = clean_text(text, stats)
        meta.encoding = encoding
        meta.encoding_confidence = confidence
        blocks, extras = parse_markdown(text, ref.display)
        doc.blocks.extend(blocks)
        if "front_matter" in extras:
            meta.extra["front_matter"] = extras["front_matter"][:4000]
            _apply_front_matter(meta, extras["front_matter"])
        if meta.title is None:
            first = next((b for b in doc.blocks if isinstance(b, Heading)), None)
            if first is not None:
                meta.title = "".join(s.text for s in first.spans)
        if guessed:
            doc.warnings.append(
                Warning(kind=WarningKind.ENCODING_UNCERTAIN, message=f"Text encoding was detected as {encoding}.")
            )
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
        return doc.finalize()


def _apply_front_matter(meta: Metadata, fm: str) -> None:
    import yaml

    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError:
        return
    if not isinstance(data, dict):
        return
    title = data.get("title")
    if isinstance(title, str):
        meta.title = title
    author = data.get("author")
    if isinstance(author, str):
        meta.author = author
    desc = data.get("description")
    if isinstance(desc, str):
        meta.description = desc
