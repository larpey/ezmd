"""Defuddle-style content rules implemented in Python (Defuddle itself is JavaScript; nothing is vendored).

Two operations on an already hygiene-cleaned tree:

- `strip_boilerplate(body, aggressive)`: removes navigation, banners, footers, sidebars, forms, cookie and
  consent banners, share widgets, newsletter boxes, related-post lists, comment sections, breadcrumbs, and ads,
  by tag, ARIA role, and class/id patterns. `aggressive=False` is the full-body fallback (part2 5b step 4: tags,
  roles, and cookie banners only).
- `main_content(body)`: picks the element holding the article: a single `<article>`, `<main>`,
  `[role=main]`, a known content class, else the block with the best text-density score, else `<body>`.

Elements that hold the page's `<h1>` or most of its paragraphs are never stripped by class patterns, and an id
that only names a section of the page's outline (`section_anchors`) says nothing about what the element is.
"""

from __future__ import annotations

import re
from itertools import islice

from ezmd_converters.web.dom import HtmlElement, collapse, is_element, tag_of, text_of
from ezmd_converters.web.hygiene import _remove

_BOILER_TAGS = ("nav", "aside", "form", "dialog", "button", "select", "input", "textarea")
_BOILER_ROLES = frozenset(
    {"navigation", "banner", "contentinfo", "complementary", "search", "dialog", "alertdialog", "menu", "menubar"}
)
_COOKIE = re.compile(
    r"cookie|(^|[-_ ])(consent|gdpr|ccpa|privacy)[-_]?(banner|bar|box|modal|popup|overlay|manager|prompt|notice-bar)"
    r"([-_ ]|$)|onetrust|cookiebot|qc-cmp|didomi|usercentrics|truste-|osano|termly",
    re.I,
)
"""Consent banners by name. Bare `consent`, `gdpr`, `ccpa` and `cmp` are not chrome: `cmp-` prefixes every Adobe
Experience Manager component (`cmp-container`, `cmp-text`), and the others name what a privacy notice is about
(`<section id="ccpa-rights">`, a biometric consent form). D-0082."""
_BOILER_CLASS = re.compile(
    r"(^|[-_ ])(nav|navbar|navigation|menu|breadcrumbs?|sidebar|side-bar|widget|share|sharing|social|"
    r"related|recommended|read-next|more-stories|newsletter|subscribe-box|signup|promo|advert|ads?|ad-slot|"
    r"sponsor|banner|masthead|site-header|site-footer|footer|comments?|comment-list|disqus|pagination|pager|"
    r"popup|modal|toolbar|skip-link|author-bio|tags-list|post-tags)([-_ ]|$)",
    re.I,
)
_CONTENT_CLASS = re.compile(
    r"(^|[-_ ])(article-body|article-content|post-content|post-body|entry-content|story-body|main-content|"
    r"markdown-body|content-body|prose|rst-content|documentation|doc-content)([-_ ]|$)",
    re.I,
)
_PARA_TAGS = ("p", "pre", "li", "blockquote", "table", "h2", "h3")
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_WORD = re.compile(r"[^\W_]+")
HEADING_WINDOW = 6
"""How many leading descendants may come before the heading that opens a section."""
MIN_OUTLINE_ANCHORS = 3
"""Plain siblings named after their heading that it takes before the ids read as an outline, not as widgets."""
MAX_ANCHOR_LINK_DENSITY = 0.5


def _attrs(el: HtmlElement, anchors: frozenset[HtmlElement] = frozenset()) -> str:
    ident = "" if el in anchors else el.get("id") or ""
    return f"{el.get('class') or ''} {ident}".strip()


def words(text: str) -> list[str]:
    """Casefolded word tokens, so a slug and the heading it came from compare equal."""
    return _WORD.findall(text.casefold())


def _opening_heading(el: HtmlElement) -> HtmlElement | None:
    if tag_of(el) in _HEADINGS:
        return el
    for node in islice(el.iterdescendants(), HEADING_WINDOW):
        if is_element(node) and tag_of(node) in _HEADINGS:
            return node
    return None


def _named_after_heading(el: HtmlElement) -> bool:
    ident = words(el.get("id") or "")
    heading = _opening_heading(el)
    if not ident or heading is None:
        return False
    return f" {' '.join(ident)} " in f" {' '.join(words(text_of(heading)))} "


def section_anchors(root: HtmlElement) -> frozenset[HtmlElement]:
    """Elements whose id is only a link target for the page's outline.

    Sites generate these ids from the heading, so `id="how-we-share-our-data"` holds the word `share` for the
    same reason the heading does, and class and id vocabularies (ours and Trafilatura's) read it as a share
    widget. An element counts when its id is a run of its own heading's words, it is not mostly links, and its
    siblings form an outline: at least MIN_OUTLINE_ANCHORS of them have ids free of those vocabularies, and they
    outnumber the rest. `<div id="related-posts"><h3>Related posts</h3>` beside `<div id="comments">` stays
    chrome, however many such widgets a page stacks."""
    groups: dict[HtmlElement, list[HtmlElement]] = {}
    for el in root.iter():
        if (
            is_element(el)
            and el.get("id")
            and _named_after_heading(el)
            and (tag_of(el) in _HEADINGS or link_density(el) < MAX_ANCHOR_LINK_DENSITY)
        ):
            groups.setdefault(el.getparent(), []).append(el)
    return frozenset(el for group in groups.values() if _is_outline(group) for el in group)


def _is_outline(group: list[HtmlElement]) -> bool:
    plain = sum(not _reads_as_chrome(el.get("id") or "") for el in group)
    return plain >= MIN_OUTLINE_ANCHORS and plain > len(group) - plain


def _reads_as_chrome(attrs: str) -> bool:
    return bool(_COOKIE.search(attrs) or _BOILER_CLASS.search(attrs))


def protected(el: HtmlElement) -> bool:
    """An element that contains the page's h1 or an <article>/<main> is content, whatever its class says."""
    tag = tag_of(el)
    if tag in ("article", "main", "body", "html"):
        return True
    return el.find(".//h1") is not None or el.find(".//article") is not None or el.find(".//main") is not None


def _header_is_boiler(el: HtmlElement) -> bool:
    """`<header>` is page chrome unless it sits inside the article (where it holds the title)."""
    node = el.getparent()
    while node is not None and is_element(node):
        if tag_of(node) in ("article", "main"):
            return False
        node = node.getparent()
    return el.find(".//h1") is None


def strip_boilerplate(body: HtmlElement, *, aggressive: bool = True) -> int:
    """Remove boilerplate in place; returns how many elements were removed."""
    removed = 0
    anchors = section_anchors(body)
    label_disclosures(body)
    for tag in _BOILER_TAGS:
        for el in list(body.iter(tag)):
            if el.getparent() is not None and not (tag == "form" and protected(el)):
                _remove(el)
                removed += 1
    for el in list(body.iter("header", "footer")):
        if el.getparent() is None:
            continue
        if (tag_of(el) == "footer" and el.find(".//h1") is None) or (tag_of(el) == "header" and _header_is_boiler(el)):
            _remove(el)
            removed += 1
    stack: list[HtmlElement] = [body]
    while stack:
        el = stack.pop()
        for child in list(el):
            if not is_element(child):
                continue
            role = (child.get("role") or "").strip().lower()
            attrs = _attrs(child, anchors)
            kill = role in _BOILER_ROLES and not protected(child)
            kill = kill or (bool(_COOKIE.search(attrs)) and not protected(child))
            if aggressive and not kill and attrs and _BOILER_CLASS.search(attrs) and not _CONTENT_CLASS.search(attrs):
                kill = not protected(child) and not mostly_content(child, body)
            if kill:
                _remove(child)
                removed += 1
            else:
                stack.append(child)
    return removed


def label_disclosures(body: HtmlElement) -> int:
    """Turn the buttons that title a section (`_is_disclosure_label`) into plain text, in place; returns how many.
    Runs on the page before any engine reads it, so Trafilatura sees the questions too."""
    panels = {str(el.get("id")): el for el in body.iter() if is_element(el) and el.get("id")}
    done = 0
    for el in list(body.iter("button")):
        if _is_disclosure_label(el, panels):
            holds_heading = next(el.iterdescendants(*_HEADINGS), None) is not None
            el.tag = "div" if holds_heading else "span" if _in_heading(el) else "p"
            el.attrib.clear()
            done += 1
    return done


def _in_heading(el: HtmlElement) -> bool:
    return any(is_element(a) and tag_of(a) in _HEADINGS for a in el.iterancestors())


def _is_disclosure_label(button: HtmlElement, panels: dict[str, HtmlElement]) -> bool:
    """A `<button>` that titles a section (an FAQ question, an accordion header): it sits inside a heading or holds
    one, or the panel it controls (`aria-controls`) holds at least five words; and its label is words, not an
    icon. Its text is the section's title, so it becomes plain text instead of going with the other buttons. A
    "Show more" or menu toggle controls a link list or nothing, and stays a button (D-0090)."""
    if len(words(text_of(button))) < 2:
        return False
    if _in_heading(button) or button.find(".//h2") is not None or button.find(".//h3") is not None:
        return True
    for ref in (button.get("aria-controls") or "").split():
        panel = panels.get(ref)
        if panel is not None and len(words(text_of(panel))) >= 5 and link_density(panel) < MAX_ANCHOR_LINK_DENSITY:
            return True
    return False


def mostly_content(el: HtmlElement, body: HtmlElement) -> bool:
    """True when `el` holds over half of the page's paragraph text (a mislabeled wrapper, not a widget)."""
    total = sum(len(collapse(text_of(p))) for p in body.iter("p")) or 1
    mine = sum(len(collapse(text_of(p))) for p in el.iter("p"))
    return mine / total > 0.5


def link_density(el: HtmlElement) -> float:
    text = len(collapse(text_of(el))) or 1
    links = sum(len(collapse(text_of(a))) for a in el.iter("a"))
    return links / text


def _score(el: HtmlElement) -> float:
    paras = list(el.iter(*_PARA_TAGS))
    text = float(sum(len(collapse(text_of(p))) for p in paras if tag_of(p) == "p"))
    text += sum(len(collapse(text_of(p))) for p in paras if tag_of(p) in ("pre", "table", "blockquote")) * 0.5
    return text * (1.0 - min(0.9, link_density(el)))


def main_content(body: HtmlElement) -> HtmlElement:
    """The element that holds the main content (Defuddle/Readability-style selection)."""
    articles = list(body.iter("article"))
    if len(articles) == 1 and len(collapse(text_of(articles[0]))) > 140:
        return articles[0]
    for xp in (".//main", ".//*[@role='main']"):
        found = body.find(xp)
        if found is not None and len(collapse(text_of(found))) > 140:
            if len(articles) > 1:
                return found
            inner = list(found.iter("article"))
            return inner[0] if len(inner) == 1 else found
    for el in body.iter():
        if is_element(el) and _CONTENT_CLASS.search(_attrs(el)) and len(collapse(text_of(el))) > 140:
            return el
    total = _score(body)
    if total <= 0:
        return body
    # The smallest container that still holds most of the scored content.
    best, best_len = body, len(text_of(body))
    for el in body.iter("div", "section", "article", "td"):
        if _score(el) >= 0.75 * total:
            n = len(text_of(el))
            if n < best_len:
                best, best_len = el, n
    return best
