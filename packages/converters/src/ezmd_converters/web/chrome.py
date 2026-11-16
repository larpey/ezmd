"""Text inside the regions boilerplate removal takes as page chrome (footers, asides, complementary regions).

Two things live there that a reader needs (D-0081):

- `chrome_footnotes`: notes the body points at. A disclosure footer that reads "2. Fees from your carrier may
  apply" next to body text "Text alerts are free²" is the second footnote of the page, wherever the site put it.
  A removed leaf block counts as a note when it opens with a marker (a leading `<sup>`, `2.`, `2)`, a superscript
  digit, `*` or a dagger) and the same marker occurs in the body outside chrome as a `<sup>` or a superscript
  character. They are appended as `Footnote` blocks unless the extracted text already holds them.
- `chrome_prose`: other long prose removed from inside the content area (`main`, `article`), measured so the loss
  is reported (`boilerplate_prose_removed`) instead of silent. Consent and cookie banners, dialogs, forms, link
  lists and the site's own footer and sidebars are not counted: those are the chrome removal exists for, and they
  repeat on every page of a site.

Both compare the body before and after `strip_boilerplate` on the same copy, so they see exactly what the
structural pass took and nothing the extractor chose to drop.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass

from ezmd.ir import InlineSpan
from ezmd_converters.web.boilerplate import _COOKIE, MAX_ANCHOR_LINK_DENSITY, link_density, strip_boilerplate, words
from ezmd_converters.web.build import Builder
from ezmd_converters.web.dom import HtmlElement, collapse, is_element, tag_of, text_of
from ezmd_converters.web.inline import inline_spans

_MARK_ATTR = "data-ezmd-chrome-i"
_LEAVES = ("p", "li", "dd", "dt", "td", "div", "span", "small", "section")
_INNER_BLOCKS = ("p", "li", "dd", "dt", "td", "div", "section", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6")
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_SUP_CHARS = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_LEADING_MARK = re.compile(r"^\s*(\d{1,2}|[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,2}|\*{1,3}|†|‡)(?:[.)]\s*|\s+)(?=\S)")
_MARKER_TEXT = re.compile(r"^(\d{1,2}|\*{1,3}|†|‡)$")
_DIALOG_CLASS = re.compile(r"(^|[-_ ])(modal|popup|dialog|overlay|interstitial|speedbump|speed-bump)([-_ ]|$)", re.I)
MIN_PROSE_WORDS = 40
"""Words a removed block needs before its loss is reported: one sentence of disclosure, not a link label."""


@dataclass(slots=True)
class Note:
    marker: str
    element: HtmlElement


def removed_by_boilerplate(body: HtmlElement) -> tuple[set[HtmlElement], list[HtmlElement]]:
    """Elements of `body` that `strip_boilerplate(aggressive=False)` removes, and the leaf blocks among them in
    document order. `body` itself is not changed: the pass runs on a copy whose elements carry their index."""
    marked = deepcopy(body)
    originals: dict[str, HtmlElement] = {}
    for i, (copy_el, orig_el) in enumerate(zip(marked.iter(), body.iter(), strict=True)):
        if is_element(copy_el):
            copy_el.set(_MARK_ATTR, str(i))
            originals[str(i)] = orig_el
    strip_boilerplate(marked, aggressive=False)
    kept = {el.get(_MARK_ATTR) for el in marked.iter() if is_element(el)}
    removed = {orig for key, orig in originals.items() if key not in kept}
    leaves = [
        el for el in body.iter(*_LEAVES) if el in removed and next(el.iterdescendants(*_INNER_BLOCKS), None) is None
    ]
    return removed, leaves


def _in_chrome_kind(el: HtmlElement) -> bool:
    """Inside a dialog, a form, or a cookie or consent banner: chrome by purpose, not by place."""
    for node in (el, *el.iterancestors()):
        if not is_element(node):
            continue
        attrs = f"{node.get('class') or ''} {node.get('id') or ''}"
        role = (node.get("role") or "").lower()
        if tag_of(node) in ("dialog", "form", "button") or role in ("dialog", "alertdialog"):
            return True
        if _COOKIE.search(attrs) or _DIALOG_CLASS.search(attrs):
            return True
    return False


def _in_content_area(el: HtmlElement) -> bool:
    """Inside `<main>`, `<article>` or `[role=main]`. A site's own footer and sidebars repeat on every page (the
    legal line, the promo cards), so a warning about them fires everywhere and says nothing about this page; a
    footer or aside inside the article is the region whose removal can take the page's own text."""
    return any(
        is_element(a) and (tag_of(a) in ("main", "article") or (a.get("role") or "").lower() == "main")
        for a in el.iterancestors()
    )


def _inside(el: HtmlElement, blocks: set[HtmlElement]) -> bool:
    return any(a in blocks for a in (el, *el.iterancestors()))


def _in_site_footer(el: HtmlElement) -> bool:
    """Inside a `<footer>` or `[role=contentinfo]`: the site's legal lines, which some sites put inside `<main>`."""
    return any(
        is_element(a) and (tag_of(a) == "footer" or (a.get("role") or "").lower() == "contentinfo")
        for a in el.iterancestors()
    )


def _body_markers(body: HtmlElement, notes: set[HtmlElement]) -> set[str]:
    """Footnote markers the page uses outside the candidate notes themselves: short `<sup>` text and superscript
    digits. References can sit in removed regions too (a hero heading inside `role=banner`), so only the notes'
    own markers are left out."""
    markers: set[str] = set()
    for sup in body.iter("sup"):
        if _inside(sup, notes):
            continue
        text = collapse(text_of(sup)).strip(" ,;()[]")
        for part in re.split(r"[,\s]+", text):
            if _MARKER_TEXT.match(part):
                markers.add(part)
    for node in body.iter():
        if not is_element(node) or tag_of(node) in ("script", "style") or _inside(node, notes):
            continue
        for chunk in (node.text or "", node.tail or ""):
            for run in _SUP_CHARS.findall(chunk):
                markers.add(run.translate(_SUPERSCRIPTS))
    return markers


def _leading_marker(el: HtmlElement) -> str | None:
    first = next((c for c in el if is_element(c)), None)
    if first is not None and tag_of(first) == "sup" and not (el.text or "").strip():
        text = collapse(text_of(first)).strip(" .)")
        return text if _MARKER_TEXT.match(text) else None
    found = _LEADING_MARK.match(collapse(text_of(el)))
    return found.group(1).translate(_SUPERSCRIPTS) if found else _list_marker(el)


def _list_marker(el: HtmlElement) -> str | None:
    """The number an `<ol>` gives the item holding `el` when `el` opens that item: footers often number notes
    with the list itself, so the text carries no marker."""
    li = el if tag_of(el) == "li" else next(el.iterancestors("li"), None)
    if li is None:
        return None
    if li is not el:
        first = next(
            (
                x
                for x in li.iterdescendants(*_LEAVES)
                if next(x.iterdescendants(*_INNER_BLOCKS), None) is None and collapse(text_of(x))
            ),
            None,
        )
        if first is not el:
            return None  # el is not the leaf that opens the item (component wrappers can nest it deep)
    ol = li.getparent()
    if ol is None or tag_of(ol) != "ol":
        return None
    try:
        start = int(ol.get("start") or 1)
    except ValueError:
        start = 1
    items = [c for c in ol if is_element(c) and tag_of(c) == "li"]
    return str(start + items.index(li))


def chrome_footnotes(body: HtmlElement, leaves: list[HtmlElement]) -> list[Note]:
    """Removed blocks (`leaves`) that are notes the body points at, in page order, one per marker."""
    candidates = [(el, m) for el in leaves if not _in_chrome_kind(el) and (m := _leading_marker(el)) is not None]
    markers = _body_markers(body, {el for el, _ in candidates})
    notes: list[Note] = []
    seen: set[str] = set()
    for el, marker in candidates:
        if marker not in markers or marker in seen or len(words(text_of(el))) < 4:
            continue
        seen.add(marker)
        notes.append(Note(marker=marker, element=el))
    return notes


def note_spans(note: Note, b: Builder) -> list[InlineSpan]:
    """The note's inline content without its leading marker (the Footnote block carries the marker)."""
    el = deepcopy(note.element)
    first = next((c for c in el if is_element(c)), None)
    if first is not None and tag_of(first) == "sup" and not (el.text or "").strip():
        first.drop_tree()  # lxml keeps the sup's tail text in place
    else:
        el.text = _LEADING_MARK.sub("", el.text or "", count=1)
    spans = inline_spans(el, b)[0]
    if spans and spans[0].text:
        spans[0].text = spans[0].text.lstrip(" .)")
    return [s for s in spans if s.text or s.href]


def chrome_prose(leaves: list[HtmlElement], *, exclude: set[HtmlElement]) -> list[str]:
    """Texts of removed blocks with at least MIN_PROSE_WORDS words that are not dialogs, forms, consent banners
    or link lists, and not in `exclude` (notes already kept)."""
    out: list[str] = []
    for el in leaves:
        if el in exclude or _in_chrome_kind(el) or link_density(el) >= MAX_ANCHOR_LINK_DENSITY:
            continue
        if not _in_content_area(el) or _in_site_footer(el):
            continue
        text = collapse(text_of(el))
        if len(words(text)) >= MIN_PROSE_WORDS:
            out.append(text)
    return out
