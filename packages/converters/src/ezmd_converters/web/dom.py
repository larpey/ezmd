"""DOM helpers for the web family: decoding, safe parsing, CSS-ish locators, text normalization.

Parsing uses lxml's HTML parser with network access off and the huge-tree switch off (libxml2's default
depth and size limits stay in force; docs/spec/part1.md 8.2). HTML has no external entities to resolve.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import lxml.html  # type: ignore[import-untyped]
from lxml import etree

log = logging.getLogger(__name__)

HtmlElement = Any
"""lxml.html.HtmlElement (lxml ships no type stubs)."""

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-:.]+)""", re.I)
_HTTP_CHARSET = re.compile(r"charset\s*=\s*[\"']?([A-Za-z0-9_\-:.]+)", re.I)
_WS = re.compile(r"\s+")
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")

BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "center", "dd", "details", "dialog", "div", "dl", "dt",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup",
        "hr", "li", "main", "menu", "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot",
        "th", "thead", "tr", "ul", "picture", "math", "ezmd-math", "ezmd-link", "caption", "noscript", "iframe",
        "video", "audio", "object", "embed", "canvas", "svg",
    }
)  # fmt: skip


def decode_html(raw: bytes, headers: dict[str, str] | None = None) -> tuple[str, str, float]:
    """Decode HTML bytes: BOM, then the HTTP charset, then `<meta charset>`, then strict UTF-8, then
    charset-normalizer (part2 5c step 7 and 13.2). Returns (text, encoding, confidence)."""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if raw.startswith(bom):
            return raw.decode(enc, errors="replace"), enc.replace("-sig", ""), 1.0
    declared: list[str] = []
    ctype = next((v for k, v in (headers or {}).items() if k.lower() == "content-type"), "")
    m = _HTTP_CHARSET.search(ctype)
    if m:
        declared.append(m.group(1))
    m2 = _META_CHARSET.search(raw[:4096])
    if m2:
        declared.append(m2.group(1).decode("ascii", "ignore"))
    for enc in declared:
        try:
            return raw.decode(enc), enc.lower(), 0.9
        except (LookupError, UnicodeDecodeError):
            log.debug("declared charset %s did not decode", enc)
    try:
        return raw.decode("utf-8"), "utf-8", 1.0
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    best = from_bytes(raw[: 1 << 20]).best()
    if best is not None:
        enc = best.encoding
        return raw.decode(enc, errors="replace"), enc, max(0.0, min(1.0, 1.0 - float(best.chaos)))
    return raw.decode("utf-8", errors="replace"), "utf-8", 0.0


def truncate_on_tag(text: str, max_chars: int) -> str:
    """Cut `text` to at most `max_chars`, backing up to the last tag start so no tag is split."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind("<", 0, max_chars)
    return text[: cut if cut > 0 else max_chars]


def parse_html(text: str) -> HtmlElement:
    """Parse to an lxml tree rooted at <html>. Comments are kept so hygiene can count and remove them."""
    parser = lxml.html.HTMLParser(remove_comments=False, remove_pis=True, no_network=True, huge_tree=False)
    text = _XML_DECL.sub("", text.replace(chr(0), ""), count=1)
    if not text.strip():
        text = "<html><body></body></html>"
    try:
        root = lxml.html.document_fromstring(text, parser=parser)
    except (etree.ParserError, ValueError):
        root = lxml.html.document_fromstring("<html><body></body></html>", parser=parser)
    return root


def body_of(root: HtmlElement) -> HtmlElement:
    body = root.find("body")
    if body is None:
        body = root
    return body


def tag_of(el: HtmlElement) -> str:
    tag = el.tag
    return tag.lower() if isinstance(tag, str) else ""


def is_element(node: Any) -> bool:
    return isinstance(getattr(node, "tag", None), str)


def collapse(text: str) -> str:
    return _WS.sub(" ", text).strip()


def match_key(text: str) -> str:
    """Whitespace-free lowercase key used to match extractor output back into the DOM."""
    return _WS.sub("", text).lower()


def text_of(el: HtmlElement) -> str:
    return str(el.text_content() or "")


def css_path(el: HtmlElement) -> str:
    """CSS-ish locator from <body> down: `body > main > article > p:nth-of-type(7)` (part2 5c step 15)."""
    parts: list[str] = []
    node = el
    while node is not None and is_element(node):
        tag = tag_of(node)
        if tag in ("html",):
            break
        parent = node.getparent()
        if tag == "body" or parent is None:
            parts.append(tag)
            break
        same = [c for c in parent if is_element(c) and tag_of(c) == tag]
        parts.append(f"{tag}:nth-of-type({same.index(node) + 1})" if len(same) > 1 else tag)
        node = parent
    return " > ".join(reversed(parts))


def base_url(root: HtmlElement, url: str | None) -> str | None:
    """`<base href>` resolved against the final URL, else the final URL. None when neither is absolute."""
    base_el = root.find(".//head/base[@href]")
    if base_el is None:
        base_el = root.find(".//base[@href]")
    href = (base_el.get("href") or "").strip() if base_el is not None else ""
    if href:
        joined = str(urljoin(url or "", str(href)))
        if urlsplit(joined).scheme in ("http", "https"):
            return joined
    if url and urlsplit(url).scheme in ("http", "https"):
        return url
    return None


def absolute(href: str, base: str | None) -> str:
    """Resolve `href` against `base`; scheme-bearing hrefs and a missing base leave it unchanged."""
    href = href.strip()
    if not href or base is None or re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
        return href
    return urljoin(base, href)


def same_origin(a: str, b: str) -> bool:
    sa, sb = urlsplit(a), urlsplit(b)
    return (sa.scheme, sa.hostname, sa.port) == (sb.scheme, sb.hostname, sb.port)


def drop(el: HtmlElement) -> None:
    """Remove `el` but keep its tail text attached to the previous node."""
    parent = el.getparent()
    if parent is None:
        return
    el.drop_tree()
