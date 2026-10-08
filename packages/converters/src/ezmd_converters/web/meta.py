"""Page metadata (part2 5b step 6 and 5c step 14).

Sources and precedence: JSON-LD Article/NewsArticle/BlogPosting > `citation_*` (Highwire) > OpenGraph and
Twitter cards > Trafilatura's metadata extractor > `<title>`, `<meta name=author|description|keywords>`, and
`<time datetime>`. Language comes from `<html lang>`. The canonical URL is recorded, but it only becomes the
document source when it is same-origin with the fetched URL (a cross-origin canonical is a hijack vector).
Runs on the raw tree, before hygiene removes `<script type="application/ld+json">`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ezmd.core.textclean import clean_text
from ezmd_converters.web.dom import HtmlElement, absolute, collapse

log = logging.getLogger(__name__)

_ARTICLE_TYPES = frozenset(
    {
        "article",
        "newsarticle",
        "blogposting",
        "techarticle",
        "scholarlyarticle",
        "report",
        "webpage",
        "reportagenewsarticle",
    }
)
_MAX_JSONLD = 512 * 1024
_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


@dataclass(slots=True)
class PageMeta:
    title: str | None = None
    author: str | None = None
    authors: list[str] = field(default_factory=list)
    published: datetime | None = None
    modified: datetime | None = None
    site_name: str | None = None
    canonical_url: str | None = None
    description: str | None = None
    language: str | None = None
    keywords: list[str] = field(default_factory=list)
    next_page: str | None = None
    jsonld_paywalled: bool = False
    jsonld: list[dict[str, Any]] = field(default_factory=list)


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = collapse(clean_text(value))
    return text[:2000] or None


def parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", v)
        if not m:
            return None
        try:
            dt = datetime.fromisoformat(m.group(1))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _metas(root: HtmlElement) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in root.iter("meta"):
        key = (m.get("property") or m.get("name") or m.get("itemprop") or "").strip().lower()
        val = m.get("content")
        if key and val and key not in out:
            out[key] = val
    return out


def _flatten_jsonld(data: object, out: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(data, list):
        for d in data[:50]:
            _flatten_jsonld(d, out, depth + 1)
    elif isinstance(data, dict):
        if "@graph" in data:
            _flatten_jsonld(data["@graph"], out, depth + 1)
        out.append(data)


def jsonld_objects(root: HtmlElement) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sc in root.iter("script"):
        if (sc.get("type") or "").strip().lower() != "application/ld+json":
            continue
        raw = (sc.text or "").strip()
        if not raw or len(raw) > _MAX_JSONLD:
            continue
        try:
            _flatten_jsonld(json.loads(raw), out)
        except (ValueError, RecursionError):
            log.debug("ignoring malformed JSON-LD block")
    return out


def _types(obj: dict[str, Any]) -> set[str]:
    t = obj.get("@type")
    vals = t if isinstance(t, list) else [t]
    return {str(v).lower() for v in vals if isinstance(v, str)}


def _names(value: object) -> list[str]:
    vals = value if isinstance(value, list) else [value]
    names: list[str] = []
    for v in vals[:20]:
        name = _clean(v.get("name")) if isinstance(v, dict) else _clean(v)
        if name and name not in names:
            names.append(name)
    return names


def _free_false(obj: dict[str, Any]) -> bool:
    flag = obj.get("isAccessibleForFree")
    if flag is False or (isinstance(flag, str) and flag.strip().lower() == "false"):
        return True
    parts = obj.get("hasPart")
    parts_list = parts if isinstance(parts, list) else [parts]
    return any(isinstance(p, dict) and _free_false(p) for p in parts_list[:20])


def _first(*values: object) -> str | None:
    for v in values:
        c = _clean(v)
        if c:
            return c
    return None


def extract(root: HtmlElement, url: str | None, base: str | None) -> PageMeta:
    pm = PageMeta()
    metas = _metas(root)
    objs = jsonld_objects(root)
    pm.jsonld = objs
    article = next((o for o in objs if _types(o) & _ARTICLE_TYPES and o.get("headline")), None)
    if article is None:
        article = next((o for o in objs if _types(o) & _ARTICLE_TYPES), {})
    pm.jsonld_paywalled = any(_free_false(o) for o in objs)
    title_el = root.find(".//title")
    title_tag = _clean(title_el.text_content()) if title_el is not None else None
    traf = _trafilatura_meta(root, url)
    pm.title = _first(
        article.get("headline"), metas.get("citation_title"), metas.get("og:title"), metas.get("twitter:title"),
        _page_title(title_tag, _h1(root), traf.get("title")),
    )  # fmt: skip
    authors = _names(article.get("author")) if article.get("author") else []
    if not authors:
        cit = [
            _clean(m.get("content")) for m in root.iter("meta") if (m.get("name") or "").lower() == "citation_author"
        ]
        authors = [a for a in cit if a]
    if not authors:
        single = _first(
            metas.get("author"), metas.get("article:author"), metas.get("twitter:creator"), traf.get("author")
        )
        authors = [single] if single else []
    pm.authors = authors[:20]
    pm.author = ", ".join(authors) if authors else None
    time_el = root.find(".//time[@datetime]")
    pm.published = parse_date(
        _first(
            article.get("datePublished"), metas.get("citation_publication_date"), metas.get("citation_date"),
            metas.get("article:published_time"), traf.get("date"),
            time_el.get("datetime") if time_el is not None else None,
        )
    )  # fmt: skip
    pm.modified = parse_date(_first(article.get("dateModified"), metas.get("article:modified_time")))
    publisher = article.get("publisher")
    pub_name = publisher.get("name") if isinstance(publisher, dict) else None
    pm.site_name = _first(
        pub_name, metas.get("citation_journal_title"), metas.get("og:site_name"), traf.get("sitename")
    )
    pm.description = _first(
        article.get("description"), metas.get("og:description"), metas.get("twitter:description"),
        metas.get("description"), traf.get("description"),
    )  # fmt: skip
    canon = root.find(".//link[@rel='canonical']")
    href = (canon.get("href") or "").strip() if canon is not None else ""
    if not href:
        href = (metas.get("og:url") or "").strip()
    if href:
        resolved = absolute(href, base)
        pm.canonical_url = resolved if resolved.lower().startswith(("http://", "https://")) else None
    lang = (root.get("lang") or root.get("xml:lang") or "").strip()
    if not lang:
        lang = (metas.get("og:locale") or metas.get("content-language") or "").replace("_", "-").strip()
    pm.language = lang if _LANG.match(lang) else None
    kws = article.get("keywords")
    if isinstance(kws, list):
        pm.keywords = [k for k in (_clean(x) for x in kws[:50]) if k]
    else:
        raw_kw = _first(kws, metas.get("keywords"), metas.get("news_keywords"))
        pm.keywords = [k.strip() for k in raw_kw.split(",") if k.strip()][:50] if raw_kw else []
    nxt = root.find(".//link[@rel='next']")
    if nxt is None:
        nxt = root.find(".//a[@rel='next']")
    if nxt is not None and (nxt.get("href") or "").strip():
        pm.next_page = absolute(str(nxt.get("href")), base)
    return pm


def _page_title(title_tag: str | None, h1: str | None, traf: str | None) -> str | None:
    """Without structured metadata: the page's h1 when the <title> contains it (drops the site suffix),
    Trafilatura's title when it is the h1 or part of the <title> (it can otherwise invent one from the URL),
    else the <title>, else the h1."""
    if h1 and title_tag and h1.casefold() in title_tag.casefold():
        return h1
    if traf and ((h1 and traf.casefold() == h1.casefold()) or (title_tag and traf.casefold() in title_tag.casefold())):
        return traf
    return title_tag or h1


def _h1(root: HtmlElement) -> str | None:
    h1 = root.find(".//body//h1")
    return _clean(h1.text_content()) if h1 is not None else None


def _trafilatura_meta(root: HtmlElement, url: str | None) -> dict[str, str]:
    """Trafilatura's metadata extractor as one fallback layer; failures leave the layer empty."""
    try:
        from copy import deepcopy

        from trafilatura import extract_metadata

        doc = extract_metadata(deepcopy(root), default_url=url, extensive=False)
    except Exception as e:  # an engine bug must not fail the conversion
        log.debug("trafilatura metadata failed: %s", e)
        return {}
    out: dict[str, str] = {}
    for key in ("title", "author", "date", "sitename", "description"):
        val = getattr(doc, key, None)
        if isinstance(val, str) and val.strip():
            out[key] = val
    return out
