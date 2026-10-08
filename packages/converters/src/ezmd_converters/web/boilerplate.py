"""Defuddle-style content rules implemented in Python (Defuddle itself is JavaScript; nothing is vendored).

Two operations on an already hygiene-cleaned tree:

- `strip_boilerplate(body, aggressive)`: removes navigation, banners, footers, sidebars, forms, cookie and
  consent banners, share widgets, newsletter boxes, related-post lists, comment sections, breadcrumbs, and ads,
  by tag, ARIA role, and class/id patterns. `aggressive=False` is the full-body fallback (part2 5b step 4: tags,
  roles, and cookie banners only).
- `main_content(body)`: picks the element holding the article: a single `<article>`, `<main>`,
  `[role=main]`, a known content class, else the block with the best text-density score, else `<body>`.

Elements that hold the page's `<h1>` or most of its paragraphs are never stripped by class patterns.
"""

from __future__ import annotations

import re

from ezmd_converters.web.dom import HtmlElement, collapse, is_element, tag_of, text_of
from ezmd_converters.web.hygiene import _remove

_BOILER_TAGS = ("nav", "aside", "form", "dialog", "button", "select", "input", "textarea")
_BOILER_ROLES = frozenset(
    {"navigation", "banner", "contentinfo", "complementary", "search", "dialog", "alertdialog", "menu", "menubar"}
)
_COOKIE = re.compile(r"(^|[-_ ])(cookie|consent|gdpr|ccpa|cmp)([-_ ]|$)|cookie|consent-banner|onetrust|cookiebot", re.I)
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


def _attrs(el: HtmlElement) -> str:
    return f"{el.get('class') or ''} {el.get('id') or ''}".strip()


def _protected(el: HtmlElement) -> bool:
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
    for tag in _BOILER_TAGS:
        for el in list(body.iter(tag)):
            if el.getparent() is not None and not (tag == "form" and _protected(el)):
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
            attrs = _attrs(child)
            kill = role in _BOILER_ROLES and not _protected(child)
            kill = kill or (bool(_COOKIE.search(attrs)) and not _protected(child))
            if aggressive and not kill and attrs and _BOILER_CLASS.search(attrs) and not _CONTENT_CLASS.search(attrs):
                kill = not _protected(child) and not _mostly_content(child, body)
            if kill:
                _remove(child)
                removed += 1
            else:
                stack.append(child)
    return removed


def _mostly_content(el: HtmlElement, body: HtmlElement) -> bool:
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
