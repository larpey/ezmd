"""Shared state for HTML-to-IR conversion: the source, base URL, counters, and block helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezmd.ir import Block, Image, InlineSpan, InlineStyle, Provenance
from ezmd_converters.web.dom import HtmlElement, absolute, css_path

_PLACEHOLDER = re.compile(
    r"(^data:image/(gif|png|svg)|placeholder|blank\.(gif|png)|spacer\.gif|1x1|pixel\.(gif|png))", re.I
)
LAZY_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-lazy", "data-url", "data-hi-res-src")
LAZY_SRCSET = ("data-srcset", "data-lazy-srcset")
_LANG_CLASS = re.compile(
    r"(?:^|\s)(?:language|lang|highlight-source|highlight|brush|sourceCode)[-:]([A-Za-z0-9_+#.-]+)"
)
_HLJS_SKIP = frozenset(
    {"hljs", "highlight", "code", "codehilite", "sourcecode", "notranslate", "prettyprint", "nohighlight"}
)
MAX_DEPTH = 150
"""Element depth beyond which content is flattened to text (libxml2 already caps parse depth at 256)."""


@dataclass(slots=True)
class Builder:
    source: str
    base: str | None
    engine: str
    blocks: list[Block] = field(default_factory=list)
    footnote_ids: dict[str, str] = field(default_factory=dict)
    """DOM id of a footnote target -> Footnote block id."""
    images_without_alt: int = 0
    lazy_images: int = 0
    figures: int = 0
    link_hrefs: list[str] = field(default_factory=list)

    def prov(self, el: HtmlElement | None, fallback: str | None = None) -> Provenance:
        path = css_path(el) if el is not None else fallback
        return Provenance(source=self.source, path=path or fallback, engine=self.engine)

    def url(self, href: str) -> str:
        return absolute(href, self.base)

    def image(
        self,
        el: HtmlElement,
        caption: list[InlineSpan] | None = None,
        parent: str | None = None,
        *,
        captioned: bool = False,
    ) -> Image | None:
        src = pick_src(el, self)
        if not src:
            return None
        alt = el.get("alt")
        alt = alt.strip() if alt else ""
        if not alt and not caption and not captioned:
            alt = "image"
            self.images_without_alt += 1
        attrs: dict[str, str] = {}
        title = (el.get("title") or "").strip()
        if title:
            attrs["title"] = title
        return Image(
            ref=src,
            alt=alt or None,
            caption=caption,
            width=_int(el.get("width")),
            height=_int(el.get("height")),
            attrs=attrs,
            parent_id=parent,
            provenance=self.prov(el),
        )


def _int(value: str | None) -> int | None:
    if value and value.strip().isdigit():
        n = int(value.strip())
        return n if n < 100_000 else None
    return None


def _largest(srcset: str) -> str | None:
    best: tuple[float, str] | None = None
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        size = 1.0
        if len(bits) > 1:
            d = bits[1].lower()
            try:
                size = float(d[:-1]) if d[-1] in "wx" else 1.0
            except ValueError:
                size = 1.0
        if best is None or size > best[0]:
            best = (size, bits[0])
    return best[1] if best else None


def pick_src(el: HtmlElement, b: Builder) -> str | None:
    """Image URL: the largest srcset candidate (also from a parent <picture>), lazy-load attributes when `src`
    is missing or a placeholder, then `src`. Relative URLs are made absolute."""
    src = (el.get("src") or "").strip()
    lazy = next((el.get(a).strip() for a in LAZY_ATTRS if (el.get(a) or "").strip()), "")
    lazy_set = next((el.get(a) for a in LAZY_SRCSET if el.get(a)), None)
    if (not src or _PLACEHOLDER.search(src)) and (lazy or lazy_set):
        b.lazy_images += 1
        chosen = _largest(lazy_set) if lazy_set else None
        src = chosen or lazy
    else:
        srcsets = [el.get("srcset") or ""]
        picture = el.getparent()
        if picture is not None and picture.tag == "source":
            picture = picture.getparent()  # libxml2 nests <img> inside the void <source>
        if picture is not None and picture.tag == "picture":
            srcsets.extend(s.get("srcset") or "" for s in picture.iter("source"))
        joined = ", ".join(s for s in srcsets if s.strip())
        chosen = _largest(joined) if joined else None
        if chosen:
            src = chosen
    if not src or src.lower().startswith(("javascript:", "data:")):
        return None
    return b.url(src)


def code_language(el: HtmlElement) -> str | None:
    """Language from `class="language-x"`, `data-lang`, highlight.js classes, or a wrapper's class."""
    nodes = [el, *el.iter("code")]
    parent = el.getparent()
    if parent is not None:
        nodes.append(parent)
        if parent.getparent() is not None:
            nodes.append(parent.getparent())
    for node in nodes:
        for attr in ("data-lang", "data-language"):
            v = (node.get(attr) or "").strip()
            if v:
                return v.lower()
        m = _LANG_CLASS.search(node.get("class") or "")
        if m and m.group(1).lower() not in ("none", "text", "plain", "plaintext"):
            return m.group(1).lower()
    code = el.find("code")
    if code is not None:
        classes = [c for c in (code.get("class") or "").split() if c.lower() not in _HLJS_SKIP]
        if "hljs" in (code.get("class") or "").split() and len(classes) == 1:
            return classes[0].lower()
    return None


STYLE_TAGS: dict[str, InlineStyle] = {
    "b": InlineStyle.BOLD,
    "strong": InlineStyle.BOLD,
    "i": InlineStyle.ITALIC,
    "em": InlineStyle.ITALIC,
    "cite": InlineStyle.ITALIC,
    "dfn": InlineStyle.ITALIC,
    "var": InlineStyle.ITALIC,
    "code": InlineStyle.CODE,
    "kbd": InlineStyle.CODE,
    "samp": InlineStyle.CODE,
    "tt": InlineStyle.CODE,
    "s": InlineStyle.STRIKE,
    "del": InlineStyle.STRIKE,
    "strike": InlineStyle.STRIKE,
    "u": InlineStyle.UNDERLINE,
    "ins": InlineStyle.UNDERLINE,
    "sup": InlineStyle.SUPERSCRIPT,
    "sub": InlineStyle.SUBSCRIPT,
}
