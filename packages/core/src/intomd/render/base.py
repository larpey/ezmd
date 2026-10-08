"""intomd.render.base: renderer interface and the output data classes every renderer shares.

docs/spec/part1.md section 6 defines the contract; docs/spec/part3.md section D defines the format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from intomd.ir import ConversionResult, Warning
from intomd.profiles import Profile

__all__ = ["Attachment", "Chunk", "RenderedOutput", "Renderer", "TokenCounter"]


@dataclass(slots=True)
class Chunk:
    id: str
    text: str
    """Chunk body including its breadcrumb and heading context, excluding the HTML comment markers."""
    section_id: str | None
    breadcrumb: str
    tokens: int
    """o200k_base count of `text`."""
    page_start: int | None
    page_end: int | None
    time_start: float | None
    time_end: float | None
    block_ids: list[str]
    part: str | None = None
    """`i/n` when an oversized table was split by rows."""
    oversized: bool = False
    merged_preamble: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "text": self.text,
            "section_id": self.section_id,
            "breadcrumb": self.breadcrumb,
            "tokens": self.tokens,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "block_ids": list(self.block_ids),
            "part": self.part,
            "oversized": self.oversized,
            "merged_preamble": self.merged_preamble,
        }


@dataclass(slots=True)
class Attachment:
    """A file the renderer produced alongside the Markdown (CSV sidecar for a table)."""

    path: str
    """Relative path as referenced from the Markdown ('tables/table-03.csv')."""
    mime: str
    data: bytes


@dataclass(slots=True)
class RenderedOutput:
    markdown: str
    """The complete output file (frontmatter plus body for `md`; the JSON text for `json`)."""
    frontmatter: dict[str, object]
    sidecar: dict[str, object] | None
    chunks: list[Chunk]
    attachments: list[Attachment] = field(default_factory=list)
    tokens: int = 0
    """cl100k_base token count of `markdown` (HTTP header X-Markdown-Tokens)."""
    truncated: bool = False
    warnings: list[Warning] = field(default_factory=list)
    injection_risk: str = "none"
    """none | low | medium | high; computed by the injection scanner over the body."""
    body: str = ""
    """Everything after the frontmatter block."""


class Renderer(Protocol):
    format: str
    """'md', 'json' or 'txt'."""

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput: ...


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...
