"""Inline HTML to `InlineSpan`s: styles, links (absolute), footnote references, inline math, line breaks."""

from __future__ import annotations

import re

from ezmd.ir import Image, InlineSpan, InlineStyle
from ezmd_converters.web.build import STYLE_TAGS, Builder
from ezmd_converters.web.dom import BLOCK_TAGS, HtmlElement, is_element, tag_of

_WS = re.compile(r"[ \t\r\n\f\v]+")
_FN_HREF = re.compile(r"^#(fn|footnote|note|cite_note|endnote)[-_:.]?", re.I)


def tex_of(el: HtmlElement) -> str | None:
    """LaTeX source of a math element: `data-latex`, a TeX `<annotation>`, a MathJax image `alt`."""
    v = el.get("data-latex") or el.get("data-tex")
    if v and v.strip():
        return str(v).strip()
    for ann in el.iter("annotation"):
        if (ann.get("encoding") or "").lower() in ("application/x-tex", "tex", "latex"):
            return (ann.text or "").strip() or None
    if tag_of(el) == "img" and (el.get("alt") or "").strip():
        return str(el.get("alt")).strip()
    return None


def is_math(el: HtmlElement) -> bool:
    tag = tag_of(el)
    if tag in ("math", "ezmd-math", "mjx-container"):
        return True
    classes = set((el.get("class") or "").split())
    return bool(classes & {"katex", "katex-display", "MathJax", "MathJax_Display", "math", "arithmatex"}) and (
        tex_of(el) is not None
    )


def footnote_target(el: HtmlElement) -> str | None:
    """The fragment a footnote reference points at, or None when `el` is not a footnote reference."""
    if tag_of(el) != "a":
        return None
    href = (el.get("href") or "").strip()
    rel = (el.get("rel") or "").lower()
    role = (el.get("role") or "").lower()
    if href.startswith("#") and ("footnote" in rel or role == "doc-noteref" or _FN_HREF.match(href)):
        return href[1:]
    return None


class Inline:
    """Collects spans for one paragraph-like element. Inline images become separate Image blocks."""

    def __init__(self, b: Builder) -> None:
        self.b = b
        self.spans: list[InlineSpan] = []
        self.images: list[Image] = []

    def add_text(self, text: str, styles: tuple[InlineStyle, ...], href: str | None, pre: bool = False) -> None:
        if not text:
            return
        if not pre:
            text = _WS.sub(" ", text)
        self.spans.append(InlineSpan(text=text, styles=list(styles), href=href))

    def walk(
        self, el: HtmlElement, styles: tuple[InlineStyle, ...] = (), href: str | None = None, depth: int = 0
    ) -> None:
        self.add_text(el.text or "", styles, href)
        for child in el:
            if is_element(child):
                self.child(child, styles, href, depth + 1)
            self.add_text(child.tail or "", styles, href)

    def child(self, el: HtmlElement, styles: tuple[InlineStyle, ...], href: str | None, depth: int) -> None:
        tag = tag_of(el)
        if tag == "br":
            self.spans.append(InlineSpan(text="\n", styles=list(styles), href=href))
            return
        if tag in ("img", "amp-img"):
            img = self.b.image(el)
            if img is not None:
                self.images.append(img)
            return
        if tag == "ezmd-link":
            return
        if is_math(el):
            tex = el.get("data-latex") if tag == "ezmd-math" else tex_of(el)
            text = tex or " ".join((el.text_content() or "").split())
            if text:
                self.spans.append(InlineSpan(text=text, math=tex))
            return
        target = footnote_target(el)
        if target is not None:
            marker = " ".join((el.text_content() or "").split()).strip("[]") or "*"
            fid = self.b.footnote_ids.get(target) or f"fn-{_slug(target)}"
            self.spans.append(InlineSpan(text=marker, footnote_ref=fid))
            return
        if tag == "sup" and len(el) == 1 and footnote_target(el[0]) is not None and not (el.text or "").strip():
            self.child(el[0], styles, href, depth)
            return
        new_styles = styles
        st = STYLE_TAGS.get(tag)
        if st is not None and st not in styles:
            new_styles = (*styles, st)
        new_href = href
        if tag == "a":
            raw = (el.get("href") or "").strip()
            if raw and not raw.lower().startswith("javascript:"):
                new_href = raw if raw.startswith("#") else self.b.url(raw)
                if not raw.startswith("#"):
                    self.b.link_hrefs.append(new_href)
        if tag in BLOCK_TAGS:
            self.add_text(" ", styles, href)
        if depth > 120:
            self.add_text(el.text_content() or "", new_styles, new_href)
            return
        self.walk(el, new_styles, new_href, depth)
        if tag in BLOCK_TAGS:
            self.add_text(" ", styles, href)

    def finish(self) -> list[InlineSpan]:
        return normalize_spans(self.spans)


def _slug(target: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", target)[:60] or "note"


def normalize_spans(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Merge neighbours with equal styling, collapse whitespace across boundaries, trim the ends."""
    merged: list[InlineSpan] = []
    for s in spans:
        if not s.text:
            continue
        if (
            merged
            and s.math is None
            and merged[-1].math is None
            and s.footnote_ref is None
            and merged[-1].footnote_ref is None
            and merged[-1].styles == s.styles
            and merged[-1].href == s.href
        ):
            merged[-1] = merged[-1].model_copy(update={"text": merged[-1].text + s.text})
        else:
            merged.append(s)
    out: list[InlineSpan] = []
    prev_space = True
    for s in merged:
        text = s.text
        if s.math is None and s.footnote_ref is None:
            text = re.sub(r" *\n *", "\n", re.sub(r" {2,}", " ", text))
            if prev_space:
                text = text.lstrip(" ")
        if not text:
            continue
        prev_space = text.endswith((" ", "\n"))
        out.append(s.model_copy(update={"text": text}) if text != s.text else s)
    while out and out[-1].math is None and out[-1].footnote_ref is None:
        t = out[-1].text.rstrip()
        if t:
            out[-1] = out[-1].model_copy(update={"text": t})
            break
        out.pop()
    while out and out[0].math is None and out[0].footnote_ref is None and not out[0].text.strip():
        out.pop(0)
    if out and out[0].math is None and out[0].footnote_ref is None:
        out[0] = out[0].model_copy(update={"text": out[0].text.lstrip()})
    return out


def inline_spans(el: HtmlElement, b: Builder) -> tuple[list[InlineSpan], list[Image]]:
    acc = Inline(b)
    acc.walk(el)
    return acc.finish(), acc.images
