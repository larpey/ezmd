"""Shared thread model for social and forum sources (docs/spec/part2.md 7c step 1).

Every adapter produces a root post plus a tree of `ThreadNode`s; the shared renderer turns that into IR. The
spec names the module `ezmd_social.model`; in this repository it lives in the converters package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Flag = Literal["op", "mod", "deleted", "removed", "collapsed", "dead"]


@dataclass(frozen=True, slots=True)
class ThreadNode:
    id: str
    author: str | None
    created: datetime | None
    body: str
    """Plain text (Markdown for Reddit, text extracted from HTML for HN); the full adapters (P3-T02) parse it."""
    depth: int = 0
    parent_id: str | None = None
    score: int | None = None
    permalink: str | None = None
    author_id: str | None = None
    edited: bool = False
    flags: tuple[Flag, ...] = ()
    children: tuple[ThreadNode, ...] = ()


@dataclass(frozen=True, slots=True)
class Thread:
    source: str
    """`reddit` or `hackernews`."""
    root: ThreadNode
    title: str
    url: str | None = None
    """Link-post target (the story URL), when the post is a link."""
    collapsed: int = 0
    """Comments hidden behind `more` stubs that were not expanded."""
    extra: dict[str, str] = field(default_factory=dict)

    def walk(self) -> list[ThreadNode]:
        """Comments depth-first in display order (the root post excluded)."""
        out: list[ThreadNode] = []
        stack = list(reversed(self.root.children))
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(node.children))
        return out
