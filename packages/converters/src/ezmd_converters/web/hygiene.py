"""Prompt-injection hygiene pass over the DOM (docs/spec/part2.md 5c step 8, part3.md section 18 phase 1).

Runs before any extractor. Removes content a reader of the rendered page cannot see: HTML comments,
`<noscript>`, `<template>`, elements with the `hidden` attribute or `aria-hidden="true"`, inline-CSS hidden
elements (display:none, visibility:hidden, opacity:0, zero size, off-screen positioning, text colored like its
declared background or transparent), elements whose class or id is a hidden pattern or is hidden by a simple
rule in the page's own `<style>`, and 1 px tracking images. Zero-width, bidi-control, and tag characters are
stripped from text nodes. Visible text is never rewritten. Removed text is kept (capped) so the injection
scanner can score it and the sidecar shows it.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[import-untyped]

from ezmd.core.textclean import CleanStats, clean_text
from ezmd_converters.web.dom import HtmlElement, collapse, is_element, tag_of

_TAG_RUN = re.compile("[" + chr(0xE0000) + "-" + chr(0xE007F) + "]+")
HIDDEN_TEXT_CAP = 10 * 1024
"""Bytes of removed text kept for the sidecar and the scanner (part2 5c step 8)."""

_HIDDEN_TOKENS = frozenset(
    {
        "hidden", "d-none", "is-hidden", "display-none", "u-hidden", "invisible", "visually-hidden", "sr-only",
        "screen-reader-text", "hide", "hidden-xs-up", "offscreen", "off-screen",
    }
)  # fmt: skip
_VIDEO_HOSTS = re.compile(r"^https?://(www\.)?(youtube\.com|youtube-nocookie\.com|youtu\.be|player\.vimeo\.com)/", re.I)
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SIMPLE_SELECTOR = re.compile(r"^[.#][A-Za-z0-9_-]+$")
_OFFSCREEN = re.compile(
    r"(?:^|;)\s*(?:left|top|right|text-indent|margin-left|margin-top)\s*:\s*-\s*(\d+(?:\.\d+)?)(px|em|rem)?"
)
_CLIP = re.compile(r"clip\s*:\s*rect\(\s*0(px)?[\s,]+0(px)?[\s,]+0(px)?[\s,]+0(px)?\s*\)|clip-path\s*:\s*inset\(\s*50%")
_WHITE = {"white", "#fff", "#ffffff", "rgb(255,255,255)", "rgba(255,255,255,1)", "hsl(0,0%,100%)"}
_SILENT_TAGS = ("script", "style", "link", "object", "embed", "svg", "canvas", "video", "audio", "track")


@dataclass(slots=True)
class HygieneReport:
    by_type: Counter[str] = field(default_factory=Counter)
    hidden_text: list[str] = field(default_factory=list)
    chars: CleanStats = field(default_factory=CleanStats)
    _kept_bytes: int = 0

    @property
    def elements(self) -> int:
        return sum(self.by_type.values())

    def record(self, kind: str, text: str) -> None:
        text = collapse(text)
        if not text:
            return
        self.by_type[kind] += 1
        self.keep(text)

    def keep(self, text: str) -> None:
        """Add `text` to the capped hidden text without counting an element (tag-character runs)."""
        room = HIDDEN_TEXT_CAP - self._kept_bytes
        if room <= 0:
            return
        piece = text.encode("utf-8")[:room].decode("utf-8", "ignore")
        self.hidden_text.append(piece)
        self._kept_bytes += len(piece.encode("utf-8")) + 1

    def hidden_joined(self) -> str:
        return "\n".join(self.hidden_text)


def _style(el: HtmlElement) -> str:
    return re.sub(r"\s+", "", (el.get("style") or "").lower())


def _norm_color(value: str) -> str:
    v = value.strip().lower().replace(" ", "").replace("!important", "")
    if v in _WHITE:
        return "#ffffff"
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        return "#" + "".join(ch * 2 for ch in v[1:])
    return v


def _decl(style: str, prop: str) -> str | None:
    m = re.search(rf"(?:^|;){prop}:([^;]+)", style)
    return m.group(1) if m else None


def _background(el: HtmlElement) -> str | None:
    node = el
    while node is not None and is_element(node):
        st = _style(node)
        bg = _decl(st, "background-color") or _decl(st, "background")
        if bg:
            return _norm_color(bg.split()[0] if " " in bg else bg)
        node = node.getparent()
    return None


def _style_reason(el: HtmlElement) -> str | None:
    st = _style(el)
    if not st:
        return None
    if "display:none" in st:
        return "display_none"
    if re.search(r"visibility:(hidden|collapse)", st):
        return "visibility_hidden"
    if re.search(r"(?:^|;)opacity:0(\.0+)?(;|$)", st):
        return "opacity_zero"
    if re.search(r"font-size:0(px|em|rem|pt|%)?(;|$)", st):
        return "zero_size"
    if re.search(r"(?:^|;)(max-)?height:0(px)?(;|$)", st) and "overflow:hidden" in st:
        return "zero_size"
    if re.search(r"(?:^|;)width:0(px)?(;|$)", st) and re.search(r"(?:^|;)height:0(px)?(;|$)", st):
        return "zero_size"
    m = _OFFSCREEN.search(st)
    if m:
        amount = float(m.group(1)) * (16 if (m.group(2) or "px") in ("em", "rem") else 1)
        if amount >= 999:
            return "off_screen"
    if _CLIP.search(st) and "position:absolute" in st:
        return "off_screen"
    color = _decl(st, "color")
    if color:
        c = _norm_color(color)
        if c == "transparent" or re.fullmatch(r"rgba\([^)]*,0(\.0+)?\)", c):
            return "same_color_text"
        bg = _background(el)
        if bg is not None and bg == c:
            return "same_color_text"
    return None


def stylesheet_hidden_selectors(root: HtmlElement) -> tuple[set[str], set[str]]:
    """Classes and ids hidden by simple rules in the page's own `<style>` blocks (`.x{display:none}`)."""
    classes: set[str] = set()
    ids: set[str] = set()
    for st in root.iter("style"):
        css = re.sub(r"/\*.*?\*/", "", st.text or "", flags=re.S)
        for sel, body in _CSS_RULE.findall(css):
            b = re.sub(r"\s+", "", body.lower())
            if "display:none" not in b and not re.search(r"visibility:hidden", b):
                continue
            for s in sel.split(","):
                s = s.strip()
                if _SIMPLE_SELECTOR.match(s):
                    (classes if s[0] == "." else ids).add(s[1:])
    return classes, ids


def _attr_reason(el: HtmlElement, css_classes: set[str], css_ids: set[str]) -> str | None:
    tag = tag_of(el)
    if tag in ("noscript", "template"):
        return tag
    if el.get("hidden") is not None:
        return "hidden_attribute"
    if (el.get("aria-hidden") or "").strip().lower() == "true":
        return "aria_hidden"
    reason = _style_reason(el)
    if reason:
        return reason
    tokens = set((el.get("class") or "").split())
    if tokens & _HIDDEN_TOKENS or (el.get("id") or "") in _HIDDEN_TOKENS:
        return "hidden_class"
    if tokens & css_classes or (el.get("id") and el.get("id") in css_ids):
        return "stylesheet_hidden"
    if tag == "img":
        w, h = el.get("width") or "", el.get("height") or ""
        if (w.strip() in ("0", "1", "1px", "0px")) or (h.strip() in ("0", "1", "1px", "0px")):
            return "tracking_pixel"
    return None


def capture_math_scripts(root: HtmlElement) -> None:
    """MathJax v2 keeps LaTeX in `<script type="math/tex">`; keep it as an `<ezmd-math>` marker before scripts
    are removed (part2 5b step 3)."""
    for sc in list(root.iter("script")):
        typ = (sc.get("type") or "").lower()
        if not typ.startswith("math/tex"):
            continue
        marker = etree.Element("ezmd-math")
        marker.set("data-latex", (sc.text or "").strip())
        # The TeX is also the marker's text so extractors that drop unknown tags (Trafilatura) keep it and
        # the extracted block still matches its DOM element by text (tei.DomIndex).
        marker.text = marker.get("data-latex")
        marker.set("data-display", "block" if "mode=display" in typ else "inline")
        marker.tail = sc.tail
        _drop_math_preview(sc)
        sc.getparent().replace(sc, marker)


def _drop_math_preview(script: HtmlElement) -> None:
    """MathJax v2 puts a `span.MathJax_Preview` (plain-text fallback) right before each math script; with the TeX
    kept, the preview would print the formula twice."""
    prev = script.getprevious()
    if prev is None or not is_element(prev) or "MathJax_Preview" not in (prev.get("class") or "").split():
        return
    if (prev.tail or "").strip():
        return
    _remove(prev)


def pre_clean(root: HtmlElement) -> HygieneReport:
    """Strip hidden and non-content nodes in place. Returns what was removed."""
    report = HygieneReport()
    css_classes, css_ids = stylesheet_hidden_selectors(root)
    capture_math_scripts(root)
    for c in list(root.iter(etree.Comment)):
        report.record("html_comment", c.text or "")
        _remove(c)
    for pi in list(root.iter(etree.ProcessingInstruction)):
        _remove(pi)
    for tag in _SILENT_TAGS:
        for el in list(root.iter(tag)):
            if el.getparent() is not None:
                _remove(el)
    for fr in list(root.iter("iframe")):
        src = (fr.get("src") or "").strip()
        if _VIDEO_HOSTS.match(src):
            marker = etree.Element("ezmd-link")
            marker.set("href", src)
            marker.set("title", fr.get("title") or "Embedded video")
            marker.tail = fr.tail
            fr.getparent().replace(fr, marker)
        else:
            _remove(fr)
    body = root.find("body")
    stack: list[HtmlElement] = [body if body is not None else root]
    while stack:
        el = stack.pop()
        for child in list(el):
            if not is_element(child):
                continue
            reason = _attr_reason(child, css_classes, css_ids)
            if reason is not None:
                text = child.text_content() or ""
                if reason == "tracking_pixel":
                    text = child.get("alt") or ""
                if not (reason == "aria_hidden" and _math_rendering(child)):
                    report.record(reason, text)
                _remove(child)
            else:
                stack.append(child)
    _clean_text_nodes(root, report)
    return report


def _math_rendering(el: HtmlElement) -> bool:
    """KaTeX and MathJax mark their visual rendering aria-hidden next to a MathML/TeX copy; removing it is
    routine de-duplication, not hidden content, so it is not counted."""
    classes = el.get("class") or ""
    parent = el.getparent()
    pclasses = (parent.get("class") or "") if parent is not None else ""
    return "katex" in classes or "MathJax" in classes or "katex" in pclasses or tag_of(el).startswith("mjx-")


def _remove(node: HtmlElement) -> None:
    parent = node.getparent()
    if parent is None:
        return
    tail = node.tail
    prev = node.getprevious()
    parent.remove(node)
    if tail:
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail


def _clean(value: str, stats: CleanStats) -> str:
    return unicodedata.normalize("NFC", clean_text(value, stats))


def _keep_tag_runs(value: str, report: HygieneReport) -> None:
    """Unicode tag characters smuggle invisible ASCII; keep each removed run raw in the hidden text so the
    renderer's scanner can decode it (part3 18)."""
    for run in _TAG_RUN.findall(value):
        report.keep(run)


def _clean_text_nodes(root: HtmlElement, report: HygieneReport) -> None:
    stats = report.chars
    for el in root.iter():
        if not is_element(el):
            continue
        if el.text:
            _keep_tag_runs(el.text, report)
            el.text = _clean(el.text, stats)
        if el.tail:
            _keep_tag_runs(el.tail, report)
            el.tail = _clean(el.tail, stats)
        for attr in ("alt", "title"):
            v = el.get(attr)
            if v:
                _keep_tag_runs(v, report)
                el.set(attr, _clean(v, stats))
