"""Source adapters for sanctioned public APIs: Reddit `.json` and Hacker News via Algolia (part2 7a, 7c).

Phase 1 ships the interface, URL recognition, API URL normalization, and a minimal parser (no `morechildren`
expansion, no Markdown parsing of bodies, no listings or user pages). The full adapters are P3-T02.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from ezmd.core.textclean import clean_text
from ezmd_converters.social.model import Flag, Thread, ThreadNode

MAX_NODES = 5000
MAX_DEPTH = 64
_REDDIT_HOSTS = frozenset({"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com"})
_REDDIT_THREAD = re.compile(r"^(?:/r/[A-Za-z0-9_]{2,21})?/comments/([a-z0-9]{1,12})(?:/[^/]*)?/?$")
_REDDIT_SHORT = re.compile(r"^/([a-z0-9]{1,12})/?$")
_HN_ITEM_API = re.compile(r"^/api/v1/items/(\d{1,10})$")
REDDIT_SORTS = frozenset({"confidence", "top", "new", "old", "controversial", "qa"})
_TAGS = re.compile(r"<[^>]+>")
_P = re.compile(r"<p>|<br\s*/?>", re.I)


class AdapterError(ValueError):
    """The payload is not what the adapter expects (HTML instead of JSON, wrong shape)."""


class SocialAdapter(Protocol):
    name: str

    def thread_id(self, url: str) -> str | None:
        """The post id when `url` is a thread this adapter handles, else None. Pure string work."""
        ...

    def api_url(self, url: str, *, sort: str = "confidence") -> str:
        """The sanctioned API URL that returns the thread as JSON."""
        ...

    def parse(self, payload: bytes, url: str) -> Thread:
        """Thread from the API response. Raises AdapterError."""
        ...


def _ts(value: Any) -> datetime | None:
    if isinstance(value, int | float) and value > 0:
        return datetime.fromtimestamp(float(value), tz=UTC)
    return None


def _clean(text: Any) -> str:
    return clean_text(str(text)).strip() if text else ""


def _html_text(html: Any) -> str:
    """HN bodies are `<p>`, `<i>`, `<a>`, `<pre><code>` only: paragraphs to blank lines, tags dropped."""
    if not html:
        return ""
    import html as htmllib

    text = _P.sub("\n\n", str(html))
    return _clean(htmllib.unescape(_TAGS.sub("", text)))


def _load(payload: bytes) -> Any:
    head = payload.lstrip()[:1]
    if head not in (b"{", b"["):
        raise AdapterError("response is not JSON (blocked or rate limited?)")
    try:
        return json.loads(payload)
    except ValueError as e:
        raise AdapterError(f"invalid JSON: {e}") from e


class RedditAdapter:
    name = "reddit"

    def thread_id(self, url: str) -> str | None:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if host == "redd.it":
            m = _REDDIT_SHORT.match(parts.path)
            return m.group(1) if m else None
        if host not in _REDDIT_HOSTS:
            return None
        m = _REDDIT_THREAD.match(parts.path.removesuffix(".json"))
        return m.group(1) if m else None

    def api_url(self, url: str, *, sort: str = "confidence") -> str:
        tid = self.thread_id(url)
        if tid is None:
            raise AdapterError(f"not a Reddit thread URL: {url}")
        sort = sort if sort in REDDIT_SORTS else "confidence"
        return f"https://www.reddit.com/comments/{tid}.json?raw_json=1&limit=500&sort={sort}"

    def parse(self, payload: bytes, url: str) -> Thread:
        data = _load(payload)
        if not (isinstance(data, list) and len(data) == 2):
            raise AdapterError("expected a two-element Reddit listing")
        try:
            post = data[0]["data"]["children"][0]["data"]
            forest = data[1]["data"]["children"]
        except (KeyError, IndexError, TypeError) as e:
            raise AdapterError("unexpected Reddit listing shape") from e
        state = {"nodes": 0, "collapsed": 0}
        op = post.get("author")
        children = tuple(self._nodes(forest, 0, f"t3_{post.get('id')}", op, state))
        root = ThreadNode(
            id=str(post.get("id") or ""),
            author=op,
            created=_ts(post.get("created_utc")),
            body=_clean(post.get("selftext")),
            score=post.get("score") if isinstance(post.get("score"), int) else None,
            permalink=f"https://www.reddit.com{post.get('permalink', '')}" if post.get("permalink") else None,
            children=children,
        )
        link = None if post.get("is_self", True) else (post.get("url") or None)
        return Thread(
            source=self.name,
            root=root,
            title=_clean(post.get("title")) or "Reddit thread",
            url=link,
            collapsed=state["collapsed"],
            extra={"subreddit": str(post.get("subreddit") or "")},
        )

    def _nodes(self, items: Any, depth: int, parent: str, op: Any, state: dict[str, int]) -> list[ThreadNode]:
        out: list[ThreadNode] = []
        if not isinstance(items, list) or depth > MAX_DEPTH:
            return out
        for item in items:
            if not isinstance(item, dict):
                continue
            kind, d = item.get("kind"), item.get("data") or {}
            if kind == "more":
                state["collapsed"] += int(d.get("count") or len(d.get("children") or []))
                continue
            if kind != "t1" or state["nodes"] >= MAX_NODES:
                continue
            state["nodes"] += 1
            body = _clean(d.get("body"))
            flags: list[Flag] = []
            if body in ("[deleted]", "[removed]"):
                flags.append("deleted" if body == "[deleted]" else "removed")
            if op and d.get("author") == op:
                flags.append("op")
            if d.get("distinguished") == "moderator":
                flags.append("mod")
            replies = d.get("replies")
            kids = replies.get("data", {}).get("children") if isinstance(replies, dict) else None
            out.append(
                ThreadNode(
                    id=str(d.get("id") or ""),
                    author=None if d.get("author") in (None, "[deleted]") else str(d.get("author")),
                    created=_ts(d.get("created_utc")),
                    body=body,
                    depth=depth,
                    parent_id=parent,
                    score=d.get("score") if isinstance(d.get("score"), int) else None,
                    edited=bool(d.get("edited")),
                    flags=tuple(flags),
                    children=tuple(self._nodes(kids, depth + 1, f"t1_{d.get('id')}", op, state)),
                )
            )
        return out


class HackerNewsAdapter:
    name = "hackernews"

    def thread_id(self, url: str) -> str | None:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if host == "news.ycombinator.com" and parts.path == "/item":
            ids = parse_qs(parts.query).get("id", [""])
            return ids[0] if ids[0].isdigit() and len(ids[0]) <= 10 else None
        if host == "hn.algolia.com":
            m = _HN_ITEM_API.match(parts.path)
            return m.group(1) if m else None
        return None

    def api_url(self, url: str, *, sort: str = "confidence") -> str:
        tid = self.thread_id(url)
        if tid is None:
            raise AdapterError(f"not a Hacker News item URL: {url}")
        return f"https://hn.algolia.com/api/v1/items/{tid}"

    def parse(self, payload: bytes, url: str) -> Thread:
        data = _load(payload)
        if not isinstance(data, dict) or "id" not in data:
            raise AdapterError("expected an Algolia item object")
        state = {"nodes": 0}
        op = data.get("author")
        root = ThreadNode(
            id=str(data["id"]),
            author=op,
            created=_ts(data.get("created_at_i")),
            body=_html_text(data.get("text")),
            score=data.get("points") if isinstance(data.get("points"), int) else None,
            permalink=f"https://news.ycombinator.com/item?id={data['id']}",
            children=tuple(self._nodes(data.get("children"), 0, str(data["id"]), op, state)),
        )
        return Thread(
            source=self.name,
            root=root,
            title=_clean(data.get("title")) or "Hacker News item",
            url=data.get("url") or None,
            extra={"type": str(data.get("type") or "")},
        )

    def _nodes(self, items: Any, depth: int, parent: str, op: Any, state: dict[str, int]) -> list[ThreadNode]:
        out: list[ThreadNode] = []
        if not isinstance(items, list) or depth > MAX_DEPTH:
            return out
        for d in items:
            if not isinstance(d, dict) or state["nodes"] >= MAX_NODES:
                continue
            state["nodes"] += 1
            flags: list[Flag] = []
            if d.get("text") is None and d.get("author") is None:
                flags.append("dead")
            if op and d.get("author") == op:
                flags.append("op")
            out.append(
                ThreadNode(
                    id=str(d.get("id") or ""),
                    author=d.get("author"),
                    created=_ts(d.get("created_at_i")),
                    body=_html_text(d.get("text")),
                    depth=depth,
                    parent_id=parent,
                    flags=tuple(flags),
                    children=tuple(self._nodes(d.get("children"), depth + 1, str(d.get("id")), op, state)),
                )
            )
        return out


ADAPTERS: tuple[SocialAdapter, ...] = (RedditAdapter(), HackerNewsAdapter())
