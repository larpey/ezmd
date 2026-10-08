"""ebooks.mathspans: recover TeX math in Markdown parsed without a math plugin (notebook Markdown cells).

`text.markdown.parse_markdown` has no dollar-math plugin, so `$x$` arrives as plain text and the renderer
would escape the dollars. This pass splits `$...$` out of plain (non-code, non-link) spans into
`InlineSpan(math=...)`, and turns a paragraph that is only `$$...$$` into an Equation block. Markdown
processing already happened, so a backslash escape or an underscore pair inside the math may have been
consumed by the Markdown parser (documented limitation).
"""

from __future__ import annotations

import re

from ezmd.ir import (
    Block,
    Equation,
    Footnote,
    Heading,
    InlineSpan,
    InlineStyle,
    ListBlock,
    ListItem,
    Paragraph,
    Quote,
    Table,
)

_INLINE = re.compile(r"(?<![\\$])\$(?=[^\s$])([^$\n]+?)(?<=[^\s\\])\$(?![$\d])")
_DISPLAY = re.compile(r"^\s*\$\$(.+?)\$\$\s*$", re.DOTALL)


def split_math(spans: list[InlineSpan]) -> list[InlineSpan]:
    out: list[InlineSpan] = []
    for s in spans:
        if s.math is not None or s.href or s.footnote_ref or InlineStyle.CODE in s.styles or "$" not in s.text:
            out.append(s)
            continue
        pos = 0
        for m in _INLINE.finditer(s.text):
            if m.start() > pos:
                out.append(s.model_copy(update={"text": s.text[pos : m.start()]}))
            out.append(InlineSpan(text=m.group(0), math=m.group(1), styles=list(s.styles)))
            pos = m.end()
        if pos < len(s.text):
            out.append(s.model_copy(update={"text": s.text[pos:]}))
    return out


def _items(items: list[ListItem]) -> None:
    for it in items:
        it.spans = split_math(it.spans)
        _items(it.children)


def apply_math(blocks: list[Block]) -> list[Block]:
    out: list[Block] = []
    for b in blocks:
        if isinstance(b, Paragraph):
            plain = "".join(s.text for s in b.spans)
            m = _DISPLAY.match(plain)
            if m and all(s.math is None and not s.styles and not s.href for s in b.spans):
                out.append(Equation(latex=m.group(1).strip(), provenance=b.provenance))
                continue
        if isinstance(b, Paragraph | Heading | Quote | Footnote):
            b.spans = split_math(b.spans)
        elif isinstance(b, ListBlock):
            _items(b.items)
        elif isinstance(b, Table):
            for c in b.cells:
                c.spans = split_math(c.spans)
        out.append(b)
    return out
