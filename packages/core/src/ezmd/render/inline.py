"""ezmd.render.inline: InlineSpan lists to Markdown (bold, italic, code, strike, links, footnotes, math)."""

from __future__ import annotations

import re
from collections.abc import Callable

from ezmd.ir import InlineSpan, InlineStyle
from ezmd.render.context import RenderContext
from ezmd.render.links import clean_url
from ezmd.render.text import clean_text, code_span, collapse_ws, escape_inline, escape_line_start

__all__ = ["plain_spans", "render_spans"]

_MULTISPACE = re.compile(r" {2,}")
_SCRIPT_SOURCE = "0123456789+-\u2212=()"
_SUPERSCRIPT = str.maketrans(
    _SCRIPT_SOURCE, "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207a\u207b\u207b\u207c\u207d\u207e"
)
_SUBSCRIPT = str.maketrans(
    _SCRIPT_SOURCE, "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089\u208a\u208b\u208b\u208c\u208d\u208e"
)
_SCRIPT_CHARS = frozenset(_SCRIPT_SOURCE)


def _unicode_script(text: str, styles: list[InlineStyle]) -> str:
    """Without extended Markdown, a superscript or subscript made only of digits and signs becomes Unicode
    script characters (`10^20` stays readable as 10²⁰, not 1020); anything else stays plain text."""
    core = text.strip()
    if not core:
        return text
    if InlineStyle.SUPERSCRIPT in styles and set(core) <= _SCRIPT_CHARS:
        return text.translate(_SUPERSCRIPT)
    if InlineStyle.SUBSCRIPT in styles and set(core) <= _SCRIPT_CHARS:
        return text.translate(_SUBSCRIPT)
    return text


def change_view(mode: str, change: str | None) -> str:
    """How an inline tracked change shows under profile `tracked_changes`: "keep" (plain text), "skip",
    or "mark" (CriticMarkup). `accept` and `drop` show the accepted text; `reject` the original."""
    if change is None:
        return "keep"
    if mode == "annotate":
        return "mark"
    if mode == "reject":
        return "skip" if change == "insert" else "keep"
    return "keep" if change == "insert" else "skip"


def plain_spans(ctx: RenderContext, spans: list[InlineSpan]) -> str:
    """Plain text of spans with whitespace collapsed (no markup, no escaping). Inline tracked changes show
    their accepted text (or the original under `reject`)."""
    mode = "reject" if ctx.profile.tracked_changes == "reject" else "accept"
    return collapse_ws(
        "".join(clean_text(s.text) for s in spans if s.footnote_ref is None and change_view(mode, s.change) != "skip")
    ).strip()


def _critic(text: str, change: str | None) -> str:
    if change == "insert":
        return "{++" + text + "++}"
    return "{--" + text + "--}"


def _wrap(text: str, styles: list[InlineStyle], extended: bool) -> str:
    core = text.strip()
    if not core:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    if InlineStyle.SUPERSCRIPT in styles and extended:
        core = f"^{core}^"
    if InlineStyle.SUBSCRIPT in styles and extended:
        core = f"~{core}~"
    bold, italic = InlineStyle.BOLD in styles, InlineStyle.ITALIC in styles
    if bold and italic:
        core = f"***{core}***"
    elif bold:
        core = f"**{core}**"
    elif italic:
        core = f"*{core}*"
    if InlineStyle.STRIKE in styles:
        core = f"~~{core}~~"
    return f"{lead}{core}{trail}"


def _resolve_anchor(ctx: RenderContext) -> Callable[[str], str | None]:
    def resolve(fragment: str) -> str | None:
        if not ctx.profile.anchors:
            return None
        return ctx.anchors.get(fragment) or ctx.anchors.get(fragment.lower())

    return resolve


def _link(ctx: RenderContext, span: InlineSpan, inner: str, plain: str) -> str:
    href = span.href or ""
    resolver = _resolve_anchor(ctx)
    url = clean_url(href, ctx.base_url, resolver)
    if url is None:
        return inner
    url = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    ctx.links.record(plain, url, href)
    mode = ctx.profile.links
    if plain.strip() == url or plain.strip() == href.strip():
        return url
    if mode == "inline":
        lead = inner[: len(inner) - len(inner.lstrip())]
        trail = inner[len(inner.rstrip()) :]
        return f"{lead}[{inner.strip()}]({url}){trail}"
    if mode == "numbered_list" and not url.startswith("#"):
        ctx.links.number(url)
    return inner


def render_spans(ctx: RenderContext, spans: list[InlineSpan], *, heading: bool = False, line_start: bool = True) -> str:
    """Render spans to one line of Markdown. Headings keep only code spans (formatting and links stripped).
    `line_start=False` (table cells) skips the escaping of block markers at the start of the text, since a
    cell never starts a line."""
    profile = ctx.profile
    dollars = sum(s.text.count("$") for s in spans if s.math is None and InlineStyle.CODE not in s.styles)
    escape_dollar = dollars >= 2
    parts: list[str] = []
    first_is_prose: bool | None = None
    for span in spans:
        view = change_view("accept" if heading else profile.tracked_changes, span.change)
        if view == "skip":
            continue
        if view == "mark":
            inner = render_spans(ctx, [span.model_copy(update={"change": None})], line_start=False)
            if inner:
                parts.append(_critic(inner, span.change))
                first_is_prose = False if first_is_prose is None else first_is_prose
            continue
        if span.footnote_ref is not None:
            if heading or profile.footnotes == "drop":
                continue
            n = ctx.footnote_number(span.footnote_ref)
            if n is not None:
                parts.append(f"[^{n}]")
            else:  # the note itself was not extracted: keep the marker readable, not glued to the word
                marker = collapse_ws(clean_text(span.text, ctx.stats)).strip().strip("[]")
                parts.append(escape_inline(f"[{marker}]") if marker else "")
            first_is_prose = False if first_is_prose is None else first_is_prose
            continue
        raw = clean_text(span.text, ctx.stats)
        if span.math is not None:
            parts.append(f"${span.math.strip()}$")
            first_is_prose = False if first_is_prose is None else first_is_prose
            continue
        text = collapse_ws(raw)
        if not text:
            continue
        if not profile.extended_markdown:
            text = _unicode_script(text, span.styles)
        if InlineStyle.CODE in span.styles:
            lead = " " if text.startswith(" ") else ""
            trail = " " if text.endswith(" ") and text.strip() else ""
            parts.append(f"{lead}{code_span(text.strip())}{trail}" if text.strip() else text)
            first_is_prose = False if first_is_prose is None else first_is_prose
            continue
        escaped = escape_inline(text)
        if escape_dollar:
            escaped = escaped.replace("$", "\\$")
        styled = escaped if heading else _wrap(escaped, span.styles, profile.extended_markdown)
        is_plain = styled == escaped
        if span.href and not heading:
            styled = _link(ctx, span, styled, text)
            is_plain = is_plain and styled == escaped
        if first_is_prose is None and text.strip():
            first_is_prose = is_plain
        parts.append(styled)
    out = _MULTISPACE.sub(" ", "".join(parts)).strip()
    if first_is_prose and not heading and line_start:
        out = escape_line_start(out)
    return out
