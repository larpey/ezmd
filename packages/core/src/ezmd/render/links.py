"""ezmd.render.links: link normalization (docs/internal/spec/part3.md section 14, "Links").

URLs are resolved against the source URL, tracking parameters are stripped, `mailto:` links become text,
and anchor-only links are rewritten to derived heading anchors when the target can be identified.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

__all__ = ["LinkCollector", "LinkRecord", "clean_url", "strip_tracking"]

_TRACKING = re.compile(r"^(utm_[a-z0-9_]*|fbclid|gclid|mc_cid|mc_eid|ref|igshid)$", re.I)


def strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)]
    query = urlencode(kept, doseq=True) if kept else ""
    if len(kept) == len(parse_qsl(parts.query, keep_blank_values=True)):
        query = parts.query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


_URL_JUNK = re.compile(r"[\x00-\x20\x7f]")
"""Whitespace and control characters, which browsers drop inside a URL (`java<TAB>script:` is `javascript:`)."""
_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):", re.I)
EMITTED_SCHEMES = frozenset({"http", "https"})
"""Schemes the renderer emits as links. Everything else (javascript, vbscript, data, file, ...) is plain
text; relative links and fragments carry no scheme. An allowlist, not a denylist (D-0059)."""
LINK_SCHEMES = EMITTED_SCHEMES | {"mailto", "tel"}
"""Schemes a converter may keep on a span; the renderer still shows mailto/tel as plain text."""


def link_scheme(href: str) -> str | None:
    """The scheme a browser would see in `href` (lowercase), after dropping whitespace and control
    characters; None for a relative link or a fragment."""
    m = _SCHEME.match(_URL_JUNK.sub("", href))
    return m.group(1).lower() if m else None


def safe_link(href: str) -> bool:
    """True when `href` is relative, a fragment, or uses one of `LINK_SCHEMES`."""
    scheme = link_scheme(href)
    return scheme is None or scheme in LINK_SCHEMES


def clean_url(href: str, base: str | None, resolve_anchor: Callable[[str], str | None]) -> str | None:
    """Return the URL to emit, or None when the link must be rendered as plain text."""
    href = href.strip()
    if not href:
        return None
    scheme = link_scheme(href)
    if scheme is not None and scheme not in EMITTED_SCHEMES:
        return None
    if href.startswith("#"):
        anchor = resolve_anchor(href[1:])
        return f"#{anchor}" if anchor else None
    if base and re.match(r"^https?://", base, re.I) and not re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I):
        href = urljoin(base, href)
    return strip_tracking(href)


@dataclass(slots=True)
class LinkRecord:
    text: str
    href: str
    original: str


@dataclass(slots=True)
class LinkCollector:
    """Collects every emitted link for the ledger and numbers URLs for the compact `## Links` list."""

    records: list[LinkRecord] = field(default_factory=list)
    numbered: list[str] = field(default_factory=list)

    def record(self, text: str, href: str, original: str) -> None:
        self.records.append(LinkRecord(text, href, original))

    def number(self, href: str) -> int:
        if href not in self.numbered:
            self.numbered.append(href)
        return self.numbered.index(href) + 1
