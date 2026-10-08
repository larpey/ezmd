"""ezmd.render.links: link normalization (docs/spec/part3.md section 14, "Links").

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


def clean_url(href: str, base: str | None, resolve_anchor: Callable[[str], str | None]) -> str | None:
    """Return the URL to emit, or None when the link must be rendered as plain text."""
    href = href.strip()
    if not href:
        return None
    lowered = href.lower()
    if lowered.startswith(("mailto:", "javascript:", "data:", "tel:")):
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
    """Collects every emitted link for the sidecar and numbers URLs for the compact `## Links` list."""

    records: list[LinkRecord] = field(default_factory=list)
    numbered: list[str] = field(default_factory=list)

    def record(self, text: str, href: str, original: str) -> None:
        self.records.append(LinkRecord(text, href, original))

    def number(self, href: str) -> int:
        if href not in self.numbered:
            self.numbered.append(href)
        return self.numbered.index(href) + 1
