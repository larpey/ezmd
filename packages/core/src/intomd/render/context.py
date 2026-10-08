"""intomd.render.context: per-render mutable state and the `Unit` building block.

Block renderers turn IR blocks into `Unit`s (one Markdown block each, already escaped). The assembler then
places page markers and footnote definitions between units, the chunker groups them, and the sidecar
records byte offsets per unit. Units are the atoms nothing may split (figures, tables, transcript paragraphs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from intomd.ir import ConversionResult, Document, Footnote, Warning, WarningKind
from intomd.profiles import Profile
from intomd.render.base import Attachment
from intomd.render.links import LinkCollector
from intomd.render.text import TextStats

__all__ = ["HeadingInfo", "RenderContext", "Unit", "UnitKind"]

UnitKind = Literal[
    "heading",
    "prose",
    "table",
    "figure",
    "list",
    "code",
    "footnotes",
    "marker",
    "transcript",
    "quote",
    "raw",
    "links",
    "equation",
    "head",
    "note",
]


@dataclass(slots=True)
class HeadingInfo:
    block_id: str
    level: int
    """Effective Markdown level (2..6) after shift and clamp."""
    original_level: int
    title: str
    original_title: str
    number: str | None
    anchor: str | None
    path: list[str]
    """Display labels from the top-level section down to this one (for rag breadcrumbs)."""
    time_start: float | None = None
    time_end: float | None = None
    overflow: str | None = None
    """Full text of a heading longer than 200 chars, emitted as the next paragraph."""

    @property
    def label(self) -> str:
        return f"{self.number} {self.title}" if self.number else self.title


@dataclass(slots=True)
class Unit:
    text: str
    kind: UnitKind
    block_ids: list[str] = field(default_factory=list)
    page: int | None = None
    page_label: str | None = None
    time_start: float | None = None
    time_end: float | None = None
    heading: HeadingInfo | None = None
    fn_refs: list[str] = field(default_factory=list)
    """Footnote block ids first referenced inside this unit."""
    table_head: str | None = None
    table_rows: list[str] | None = None
    """For table units: caption/header lines and row lines, so the chunker can split by rows."""
    list_items: list[str] | None = None
    sidecar_key: tuple[str, int] | None = None
    """(sidecar list name, index) whose offsets this unit fills in."""
    generated: bool = False
    """True for renderer-generated marker comments (excluded from the injection scan)."""


@dataclass(slots=True)
class RenderContext:
    profile: Profile
    result: ConversionResult
    base_url: str | None = None
    stats: TextStats = field(default_factory=TextStats)
    furniture_removed: int = 0
    heading_shift: int = 1
    """Levels source headings moved down: 1 when a source H1 remains below the title, else 0."""
    images_dropped_decorative: int = 0
    warnings: list[Warning] = field(default_factory=list)
    links: LinkCollector = field(default_factory=LinkCollector)
    footnotes: dict[str, Footnote] = field(default_factory=dict)
    fn_numbers: dict[str, int] = field(default_factory=dict)
    pending_refs: list[str] = field(default_factory=list)
    anchors: dict[str, str] = field(default_factory=dict)
    headings: dict[str, HeadingInfo] = field(default_factory=dict)
    current_heading: HeadingInfo | None = None
    table_count: int = 0
    figure_count: int = 0
    attachments: list[Attachment] = field(default_factory=list)
    sidecar_lists: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    annotations: dict[str, list[str]] = field(default_factory=dict)
    truncated: bool = False
    header_synthesized: int = 0
    speaker_names: dict[str, str] = field(default_factory=dict)
    show_speakers: bool = False
    fence_defanged: int = 0
    keep_furniture: set[str] = field(default_factory=set)

    @property
    def doc(self) -> Document:
        return self.result.document

    def warn(
        self, kind: WarningKind, message: str, *, block_id: str | None = None, **detail: str | int | float
    ) -> None:
        for w in self.warnings:
            if w.kind == kind and w.block_id == block_id and w.message == message:
                return
        self.warnings.append(Warning(kind=kind, message=message, block_id=block_id, detail=dict(detail)))

    def side(self, name: str, entry: dict[str, object]) -> int:
        bucket = self.sidecar_lists.setdefault(name, [])
        bucket.append(entry)
        return len(bucket) - 1

    def footnote_number(self, footnote_id: str) -> int | None:
        """Number a footnote on first reference (sequential through the document)."""
        if footnote_id not in self.footnotes:
            return None
        if footnote_id not in self.fn_numbers:
            self.fn_numbers[footnote_id] = len(self.fn_numbers) + 1
            self.pending_refs.append(footnote_id)
        return self.fn_numbers[footnote_id]

    def take_refs(self) -> list[str]:
        refs, self.pending_refs = self.pending_refs, []
        return refs
