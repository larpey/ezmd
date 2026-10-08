"""intomd.ir: the intermediate representation every converter produces and every renderer consumes.

Blocks are flat and ordered. Hierarchy is expressed via `parent_id` (sections, figures, slides)
and via explicit nesting inside ListBlock. Every block carries Provenance.

Implemented from docs/spec/part1.md section 4. Deviations are logged in DECISIONS.md (D-0004).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intomd.warnings.codes import CODES, WarningKind, normalize_code

__all__ = [
    "MAX_CHILD_DEPTH",
    "MAX_NEST_DEPTH",
    "BBox",
    "Block",
    "BlockBase",
    "CodeBlock",
    "ColumnType",
    "Comment",
    "ConversionResult",
    "Document",
    "ElementCounts",
    "Equation",
    "Figure",
    "Footnote",
    "Heading",
    "Image",
    "InlineSpan",
    "InlineStyle",
    "InputKind",
    "InputRefInfo",
    "LanguageSource",
    "Link",
    "ListBlock",
    "ListItem",
    "Metadata",
    "Metrics",
    "PageBreak",
    "Paragraph",
    "Provenance",
    "Quote",
    "Raw",
    "Slide",
    "SourceType",
    "Table",
    "TableCell",
    "TrackedChange",
    "TranscriptSegment",
    "Warning",
    "WarningKind",
    "spans_text",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, validate_assignment=True)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class BBox(_Model):
    """Axis-aligned bounding box in page coordinates, origin top-left, units in points (PDF)
    or pixels (images). `page_width`/`page_height` allow normalization downstream."""

    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float | None = None
    page_height: float | None = None

    @model_validator(mode="after")
    def _ordered(self) -> BBox:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bbox coordinates must satisfy x0<=x1 and y0<=y1")
        return self


class Provenance(_Model):
    """Where a block came from. Every field is optional except `source`.

    source: canonical path or URL of the input this block was extracted from. For attachments
        and nested archives this is `<outer>!<inner path>`.
    source_page: 1-based page number (PDF, DOCX page estimate, PPTX slide index, XLSX sheet index).
    source_label: name of the containing sheet, slide, or chapter. Only for those names; a printed
        page label goes in `page_label` (D-0017).
    page_label: the page label printed on the page when it differs from the physical number ("iv", "A-3").
    path: location inside a container input: archive member path, repository file path, JSON pointer,
        or mailbox folder. None for single-file inputs.
    source_id: stable id of the source item the block came from (message id, post id, notebook cell id).
    char_start / char_end: 0-based character offsets into the decoded source text, end exclusive.
    bbox: layout box when the engine provides one.
    time_start / time_end: seconds into media for transcript-derived blocks.
    line_start / line_end: 1-based line numbers in text-like sources (code, plain text, line-structured transcripts).
    engine: converter id and engine that produced this block (for shadow-run comparisons).
    confidence: engine confidence in [0, 1] when available (OCR, ASR). None means unknown.
    """

    source: str
    source_page: int | None = None
    source_label: str | None = None
    page_label: str | None = None
    path: str | None = None
    source_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: BBox | None = None
    time_start: float | None = None
    time_end: float | None = None
    line_start: int | None = None
    line_end: int | None = None
    engine: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _char_range(self) -> Provenance:
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        return self


# ---------------------------------------------------------------------------
# Inline content
# ---------------------------------------------------------------------------


class InlineStyle(StrEnum):
    BOLD = "bold"
    ITALIC = "italic"
    CODE = "code"
    STRIKE = "strike"
    UNDERLINE = "underline"
    SUPERSCRIPT = "superscript"
    SUBSCRIPT = "subscript"


class InlineSpan(_Model):
    """A run of text with uniform styling. `href` makes it a link; `footnote_ref` points at a
    Footnote block id; `math` holds LaTeX for inline equations (text is the fallback rendering)."""

    text: str
    styles: list[InlineStyle] = Field(default_factory=list)
    href: str | None = None
    footnote_ref: str | None = None
    math: str | None = None


def spans_text(spans: list[InlineSpan]) -> str:
    """Plain-text concatenation of spans. Used by scoring and by renderers that drop styling."""
    return "".join(s.text for s in spans)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class BlockBase(_Model):
    """Fields shared by every block. `id` is assigned by Document.finalize(); converters may leave it empty."""

    id: str = ""
    parent_id: str | None = None
    provenance: Provenance
    attrs: dict[str, str] = Field(default_factory=dict)
    """Free-form string attributes for converter-specific hints the renderer may use
    (for example `{"docling_label": "caption"}`). Never required for rendering."""


class Heading(BlockBase):
    type: Literal["heading"] = "heading"
    level: int = Field(ge=1, le=6)
    spans: list[InlineSpan]
    number: str | None = None
    """Section number if the source had one ("3.2"). Renderers may assign numbers when absent."""


ParagraphRole = Literal[
    "body", "caption", "header", "footer", "page_number", "abstract", "title", "subtitle", "author", "date"
]


class Paragraph(BlockBase):
    type: Literal["paragraph"] = "paragraph"
    spans: list[InlineSpan]
    role: ParagraphRole = "body"
    """Furniture roles (header, footer, page_number) let renderers drop repeated chrome."""


class TableCell(_Model):
    spans: list[InlineSpan]
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    is_header: bool = False
    formula: str | None = None
    """Spreadsheet formula text when the source had one (XLSX). The spans hold the cached value."""
    raw_value: str | None = None
    """Unformatted value (for example the float behind a currency-formatted cell)."""
    bbox: BBox | None = None


ColumnType = Literal["text", "int", "float", "currency", "date", "percent", "bool"]
"""Per-column value type a converter knows from the source (XLSX number formats, typed data)."""


class Table(BlockBase):
    type: Literal["table"] = "table"
    cells: list[TableCell]
    n_rows: int = Field(ge=0)
    n_cols: int = Field(ge=0)
    caption: list[InlineSpan] | None = None
    has_merged_cells: bool = False
    header_rows: int = 0
    """Number of leading rows that are headers. 0 means unknown or none."""
    continued_from: str | None = None
    """Block id of the previous fragment when a table spanned pages and the converter joined them."""
    column_types: list[ColumnType] | None = None
    """One type per column when known. None means unknown: the renderer infers numeric columns."""

    @model_validator(mode="after")
    def _shape(self) -> Table:
        if self.column_types is not None and len(self.column_types) != self.n_cols:
            raise ValueError(f"column_types has {len(self.column_types)} entries for {self.n_cols} columns")
        for c in self.cells:
            if c.row + c.row_span > self.n_rows or c.col + c.col_span > self.n_cols:
                raise ValueError(f"cell at ({c.row},{c.col}) exceeds table shape {self.n_rows}x{self.n_cols}")
        merged = any(c.row_span > 1 or c.col_span > 1 for c in self.cells)
        if merged and not self.has_merged_cells:
            # object.__setattr__ avoids re-running validation recursively under validate_assignment.
            object.__setattr__(self, "has_merged_cells", True)
        return self

    def grid(self) -> list[list[TableCell | None]]:
        """Materialize a row-major grid. Merged cells occupy their anchor position only."""
        g: list[list[TableCell | None]] = [[None] * self.n_cols for _ in range(self.n_rows)]
        for c in self.cells:
            g[c.row][c.col] = c
        return g


class ListItem(_Model):
    spans: list[InlineSpan]
    children: list[ListItem] = Field(default_factory=list)
    children_ordered: bool = False
    """Whether `children` form an ordered (numbered) sub-list (D-0014)."""
    children_start: int = 1
    """First number of an ordered sub-list."""
    checked: bool | None = None
    """Task-list state. None means not a task item."""
    provenance: Provenance | None = None


class ListBlock(BlockBase):
    type: Literal["list"] = "list"
    ordered: bool = False
    start: int = 1
    items: list[ListItem]


class CodeBlock(BlockBase):
    type: Literal["code"] = "code"
    code: str
    language: str | None = None
    filename: str | None = None
    """For repo packing: path of the file this code came from."""


class Image(BlockBase):
    type: Literal["image"] = "image"
    ref: str
    """Path or URL where the renderer can reference the image. Blob store key for extracted images."""
    alt: str | None = None
    caption: list[InlineSpan] | None = None
    generated_caption: str | None = None
    """VLM or OCR-derived description; renderers label it as generated."""
    ocr_text: str | None = None
    width: int | None = None
    height: int | None = None
    mime: str | None = None
    chart_data: Table | None = None
    """When a chart was converted to data, the extracted table."""


class Figure(BlockBase):
    """A grouping block: its children (image, caption paragraph, table) have parent_id == this id."""

    type: Literal["figure"] = "figure"
    label: str | None = None
    """'Figure 3', 'Table 2', 'Listing 1'."""


class Footnote(BlockBase):
    type: Literal["footnote"] = "footnote"
    marker: str
    """The visible marker ('1', 'a', '*')."""
    spans: list[InlineSpan]
    section_id: str | None = None
    """Heading block id of the section this footnote belongs to, so renderers can place it at section end."""


class Equation(BlockBase):
    type: Literal["equation"] = "equation"
    latex: str | None = None
    text: str | None = None
    """Fallback plain text when LaTeX could not be recovered."""
    label: str | None = None


class PageBreak(BlockBase):
    type: Literal["page_break"] = "page_break"
    page_number: int
    """The page that begins after this break (1-based)."""


class TranscriptSegment(BlockBase):
    """One ASR or caption segment. Converters emit these at engine granularity; the renderer merges
    into turns and paragraphs according to Part 3 rules."""

    type: Literal["transcript_segment"] = "transcript_segment"
    start: float
    end: float
    text: str
    speaker: str | None = None
    """Diarization label ('SPEAKER_00') or resolved name."""
    language: str | None = None
    words: list[tuple[str, float, float]] | None = None
    """Optional word-level timings (word, start, end). Kept for the sidecar only."""
    kind: Literal["speech", "music", "noise", "silence", "on_screen_text", "slide_change"] = "speech"


class Slide(BlockBase):
    """Grouping block for presentations. Children carry parent_id == this id. Notes are a Paragraph child
    with role='body' and attrs={'slide_part': 'notes'}."""

    type: Literal["slide"] = "slide"
    index: int
    title: str | None = None
    layout: str | None = None


class Comment(BlockBase):
    """A review comment (DOCX, PPTX, PDF annotation, Google Docs) anchored to a block or text range."""

    type: Literal["comment"] = "comment"
    author: str | None = None
    created: datetime | None = None
    spans: list[InlineSpan]
    anchor_block_id: str | None = None
    anchor_text: str | None = None
    reply_to: str | None = None
    """Comment block id this replies to."""
    resolved: bool | None = None


class TrackedChange(BlockBase):
    """A DOCX/ODT/Google Docs revision. The renderer decides how to show it per profile."""

    type: Literal["tracked_change"] = "tracked_change"
    change: Literal["insert", "delete", "format", "move"]
    author: str | None = None
    created: datetime | None = None
    spans: list[InlineSpan]
    anchor_block_id: str | None = None


class Link(BlockBase):
    """A standalone link worth listing (web page outbound links, references, 'Links' sections).
    Inline links live in InlineSpan.href; this block is for link lists and reference sections."""

    type: Literal["link"] = "link"
    href: str
    text: str | None = None
    rel: str | None = None


class Quote(BlockBase):
    type: Literal["quote"] = "quote"
    spans: list[InlineSpan]
    attribution: str | None = None
    depth: int = Field(default=1, ge=1)
    """Nesting depth for threaded content (email quotes, nested comments)."""


class Raw(BlockBase):
    """Content the converter could not map to another block. Renderers emit it in a fenced block
    labeled with `format` so nothing is lost. Use sparingly; prefer a Paragraph with a warning."""

    type: Literal["raw"] = "raw"
    format: str
    """'html', 'xml', 'latex', 'rtf', 'unknown', ..."""
    content: str


Block = Annotated[
    Heading
    | Paragraph
    | Table
    | ListBlock
    | CodeBlock
    | Image
    | Figure
    | Footnote
    | Equation
    | PageBreak
    | TranscriptSegment
    | Slide
    | Comment
    | TrackedChange
    | Link
    | Quote
    | Raw,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Document-level metadata, warnings, metrics
# ---------------------------------------------------------------------------


class SourceType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    ODF = "odf"
    IWORK = "iwork"
    RTF = "rtf"
    EPUB = "epub"
    MARKUP = "markup"
    NOTEBOOK = "notebook"
    HTML = "html"
    WEB = "web"
    FEED = "feed"
    SOCIAL = "social"
    AUDIO = "audio"
    VIDEO = "video"
    MEDIA_URL = "media_url"
    IMAGE = "image"
    CODE = "code"
    REPO = "repo"
    OPENAPI = "openapi"
    EMAIL = "email"
    CHAT = "chat"
    DATA = "data"
    FINANCE_XML = "finance_xml"
    NOTES = "notes"
    CALENDAR = "calendar"
    ARCHIVE = "archive"
    TEXT = "text"
    OTHER = "other"


LanguageSource = Literal["declared", "detected", "hint"]


class Metadata(_Model):
    """Document-level metadata. Mirrors the frontmatter schema (Part 3) minus render-time fields."""

    title: str | None = None
    source: str
    source_type: SourceType
    mime: str | None = None
    author: str | None = None
    authors: list[str] = Field(default_factory=list)
    published: datetime | None = None
    modified: datetime | None = None
    fetched: datetime | None = None
    language: str | None = None
    """BCP-47. The majority language when `languages` lists several."""
    languages: list[str] = Field(default_factory=list)
    """BCP-47 codes when the document is multilingual (Part 2 13.3), majority first."""
    language_source: LanguageSource | None = None
    """Where `language` came from: a structural declaration, detection, or the user's hint."""
    encoding: str | None = None
    """Text encoding the source was decoded with (text-like inputs only; Part 2 13.2)."""
    encoding_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    """Confidence of the encoding detection; 1.0 for a BOM or a strict UTF-8 decode."""
    license: str | None = None
    pages: int | None = None
    duration_seconds: float | None = None
    speakers: list[str] = Field(default_factory=list)
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    canonical_url: str | None = None
    site_name: str | None = None
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    """Converter-specific scalar metadata (EXIF, email headers, repo stats). Rendered into frontmatter
    under `extra:` in the full profile only."""


class Warning(_Model):
    """A structured warning. `kind` is a code from `intomd.warnings.codes`; when `severity` is omitted
    the registry's default severity for that code is used."""

    kind: WarningKind
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    """Human-readable, one sentence, no engine stack traces."""
    block_id: str | None = None
    page: int | None = None
    count: int | None = None
    detail: dict[str, str | int | float] = Field(default_factory=dict)

    @field_validator("kind", mode="before")
    @classmethod
    def _canonical_kind(cls, value: Any) -> Any:
        """Retired spellings (warnings.codes.ALIASES) are accepted and stored as the canonical code."""
        if isinstance(value, str):
            try:
                return normalize_code(value)
            except ValueError:
                return value
        return value

    @model_validator(mode="before")
    @classmethod
    def _default_severity(cls, data: Any) -> Any:
        if isinstance(data, dict) and "severity" not in data and "kind" in data:
            try:
                spec = CODES[normalize_code(data["kind"])]
            except (KeyError, ValueError, TypeError):
                return data
            return {**data, "severity": spec.severity}
        return data


class ElementCounts(_Model):
    headings: int = 0
    paragraphs: int = 0
    tables: int = 0
    table_cells: int = 0
    lists: int = 0
    list_items: int = 0
    code_blocks: int = 0
    images: int = 0
    figures: int = 0
    footnotes: int = 0
    equations: int = 0
    page_breaks: int = 0
    transcript_segments: int = 0
    slides: int = 0
    comments: int = 0
    tracked_changes: int = 0
    links: int = 0
    quotes: int = 0
    raw: int = 0
    words: int = 0


class Metrics(_Model):
    duration_seconds: float = 0.0
    """Wall time of the conversion, excluding fetch."""
    fetch_seconds: float | None = None
    engine: str | None = None
    """Primary engine id, e.g. 'docling@2.14.0'."""
    engines_tried: list[str] = Field(default_factory=list)
    input_bytes: int | None = None
    estimated_tokens: int = 0
    """cl100k_base estimate of the plain text; renderers recompute for the rendered output."""
    counts: ElementCounts = Field(default_factory=ElementCounts)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


_COUNT_FIELD: dict[str, str] = {
    "heading": "headings",
    "paragraph": "paragraphs",
    "table": "tables",
    "list": "lists",
    "code": "code_blocks",
    "image": "images",
    "figure": "figures",
    "footnote": "footnotes",
    "equation": "equations",
    "page_break": "page_breaks",
    "transcript_segment": "transcript_segments",
    "slide": "slides",
    "comment": "comments",
    "tracked_change": "tracked_changes",
    "link": "links",
    "quote": "quotes",
    "raw": "raw",
}


MAX_NEST_DEPTH = 32
"""Deepest list level (1-based) that keeps its own structure. finalize() flattens every descendant of a
level-32 item into that item's children, in text order, and warns `nesting_flattened` (D-0017)."""

MAX_CHILD_DEPTH = 8
"""Deepest allowed nesting of `Document.children` (archives cap at 3); finalize() raises beyond it."""


class Document(_Model):
    """The unit of conversion. One input produces one Document. Attachments and archive members
    are separate Documents linked via `children`.

    schema_version "1.1" (D-0017) is additive over "1"; readers accept both.
    """

    schema_version: Literal["1", "1.1"] = "1.1"
    metadata: Metadata
    blocks: list[Block] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    children: list[Document] = Field(default_factory=list)
    converter_id: str = ""
    content_hash: str = ""
    """sha256 of the finalized plain text; set by finalize()."""
    truncated: bool = False
    """True when the converter stopped early (a cap or the deadline). ConversionResult.truncated ORs this
    with every warning whose code spec has `truncates=True`."""
    _finalized: bool = False

    @property
    def finalized(self) -> bool:
        return self._finalized

    def plain_text(self) -> str:
        """Concatenated plain text of all text-bearing blocks, in order. Used for hashing, token
        estimates, scoring, and injection scanning."""
        parts: list[str] = []
        for b in self.blocks:
            match b:
                case Heading() | Paragraph() | Quote() | Footnote() | TrackedChange() | Comment():
                    parts.append(spans_text(b.spans))
                case Table():
                    parts.append("\n".join(spans_text(c.spans) for c in b.cells))
                case ListBlock():
                    parts.extend(_list_text(b.items))
                case CodeBlock():
                    parts.append(b.code)
                case TranscriptSegment():
                    parts.append(b.text)
                case Image():
                    parts.append(b.generated_caption or b.alt or "")
                case Equation():
                    parts.append(b.latex or b.text or "")
                case Raw():
                    parts.append(b.content)
                case _:
                    pass
        return "\n".join(p for p in parts if p)

    def finalize(self) -> Document:
        """Assign ids in document order, validate parent references, cap list nesting, compute the hash.
        Idempotent. Converters must call this before returning. Raises ValueError when `children`
        nest deeper than MAX_CHILD_DEPTH."""
        if _child_depth(self) > MAX_CHILD_DEPTH:
            raise ValueError(f"Document.children nest deeper than {MAX_CHILD_DEPTH} levels")
        self._cap_list_nesting()
        for i, b in enumerate(self.blocks, start=1):
            if not b.id:
                b.id = f"b{i:04d}"
        ids = {b.id for b in self.blocks}
        if len(ids) != len(self.blocks):
            raise ValueError("duplicate block ids")
        for b in self.blocks:
            if b.parent_id is not None and b.parent_id not in ids:
                raise ValueError(f"block {b.id} references unknown parent {b.parent_id}")
        text = self.plain_text()
        self.content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        for child in self.children:
            child.finalize()
        self._finalized = True
        return self

    def _cap_list_nesting(self) -> None:
        flattened = 0
        for b in self.blocks:
            if isinstance(b, ListBlock):
                flattened += _flatten_deep_items(b.items)
        if flattened and not any(w.kind == WarningKind.NESTING_FLATTENED for w in self.warnings):
            self.warnings.append(
                Warning(
                    kind=WarningKind.NESTING_FLATTENED,
                    message=f"List nesting deeper than {MAX_NEST_DEPTH} levels was flattened.",
                    count=flattened,
                    detail={"max_depth": MAX_NEST_DEPTH},
                )
            )

    def counts(self) -> ElementCounts:
        values: dict[str, int] = {}
        for b in self.blocks:
            name = _COUNT_FIELD[b.type]
            values[name] = values.get(name, 0) + 1
            match b:
                case Table():
                    values["table_cells"] = values.get("table_cells", 0) + len(b.cells)
                case ListBlock():
                    values["list_items"] = values.get("list_items", 0) + _count_items(b.items)
                case _:
                    pass
        values["words"] = len(self.plain_text().split())
        return ElementCounts(**values)

    def sections(self) -> list[tuple[Heading, list[Block]]]:
        """Group blocks under their preceding heading. Blocks before the first heading are grouped
        under a synthetic heading with id `b0000` and empty spans (the spec's "level-0" heading;
        `level` is 1 because Heading.level is constrained to 1..6). The synthetic group is always
        first, even when empty, so callers can rely on `sections()[0]` being the preamble."""
        out: list[tuple[Heading, list[Block]]] = []
        current = Heading(level=1, spans=[], provenance=Provenance(source=self.metadata.source), id="b0000")
        bucket: list[Block] = []
        for b in self.blocks:
            if isinstance(b, Heading):
                out.append((current, bucket))
                current, bucket = b, []
            else:
                bucket.append(b)
        out.append((current, bucket))
        return out


def _child_depth(doc: Document) -> int:
    """Levels of `children` below `doc` (0 when it has none), computed without recursion."""
    deepest = 0
    stack: list[tuple[Document, int]] = [(doc, 0)]
    while stack:
        node, depth = stack.pop()
        deepest = max(deepest, depth)
        if depth > MAX_CHILD_DEPTH:
            break
        stack.extend((c, depth + 1) for c in node.children)
    return deepest


def _flatten_deep_items(items: list[ListItem]) -> int:
    """Flatten descendants of every level-MAX_NEST_DEPTH item into its children. Returns how many items
    moved up. Iterative, so arbitrarily deep input cannot exhaust the stack."""
    moved = 0
    stack: list[tuple[ListItem, int]] = [(it, 1) for it in items]
    while stack:
        item, level = stack.pop()
        if level < MAX_NEST_DEPTH:
            stack.extend((c, level + 1) for c in item.children)
            continue
        if not any(c.children for c in item.children):
            continue
        flat: list[ListItem] = []
        walk: list[tuple[ListItem, int]] = [(c, 1) for c in reversed(item.children)]
        while walk:
            node, rel = walk.pop()
            if rel > 1:
                moved += 1
            flat.append(node.model_copy(update={"children": []}))
            walk.extend((c, rel + 1) for c in reversed(node.children))
        item.children = flat
    return moved


def _list_text(items: list[ListItem]) -> list[str]:
    out: list[str] = []
    for it in items:
        out.append(spans_text(it.spans))
        out.extend(_list_text(it.children))
    return out


def _count_items(items: list[ListItem]) -> int:
    return sum(1 + _count_items(it.children) for it in items)


# ---------------------------------------------------------------------------
# ConversionResult
# ---------------------------------------------------------------------------


InputKind = Literal[
    "path", "bytes", "url", "residential_fetch", "transcript_segments", "captions_json3", "media_upload"
]
"""Input kinds. The last three come from the Part 4 reconciliation note (browser-side Whisper and
extension uploads)."""


class InputRefInfo(_Model):
    """Serializable summary of the InputRef that was converted (the InputRef itself may hold handles)."""

    kind: InputKind
    display: str
    """Filename or URL for display and frontmatter."""
    mime: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None


class ConversionResult(_Model):
    """What the pipeline returns to the job system and the CLI. Wraps the Document with run metrics."""

    document: Document
    warnings: list[Warning] = Field(default_factory=list)
    """Pipeline-level warnings (detection ambiguity, fallback engine used, limits hit). Document-level
    warnings live on document.warnings; renderers merge both."""
    metrics: Metrics = Field(default_factory=Metrics)
    truncated: bool = False
    """True when any cap (pages, rows, duration, bytes, time) cut the input short: `document.truncated`
    OR any warning whose code spec has `truncates=True` (computed by the registry; D-0017)."""
    converter_id: str
    input_ref: InputRefInfo

    @property
    def all_warnings(self) -> list[Warning]:
        return [*self.warnings, *self.document.warnings]


Document.model_rebuild()
ListItem.model_rebuild()
ConversionResult.model_rebuild()
