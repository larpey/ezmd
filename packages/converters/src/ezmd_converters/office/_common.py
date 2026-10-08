"""Shared helpers for the Office family: options, mime tables, confidence rules, block building."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef
from ezmd.ir import Block, InlineSpan, InlineStyle, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions

FAMILY = "documents"
MB = 1024 * 1024

DOCX_MIMES = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-word.document.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "application/vnd.ms-word.template.macroenabled.12",
)
DOCX_EXTS = (".docx", ".docm", ".dotx", ".dotm")
PPTX_MIMES = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint.presentation.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.presentationml.template",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
)
PPTX_EXTS = (".pptx", ".pptm", ".potx", ".ppsx")
XLSX_MIMES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
)
XLSX_EXTS = (".xlsx", ".xlsm", ".xltx", ".xltm")
ODF_MIMES = (
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.text-template",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.spreadsheet-template",
    "application/vnd.oasis.opendocument.presentation",
    "application/vnd.oasis.opendocument.presentation-template",
)
ODF_EXTS = (".odt", ".ott", ".ods", ".ots", ".odp", ".otp")
RTF_MIMES = ("application/rtf", "text/rtf")
RTF_EXTS = (".rtf",)
LEGACY_MIMES = (
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12",
    "application/vnd.wordperfect",
)
LEGACY_EXTS = (".doc", ".dot", ".xls", ".xlsb", ".ppt", ".pps", ".wpd")
IWORK_MIMES = ("application/vnd.apple.pages", "application/vnd.apple.numbers", "application/vnd.apple.keynote")
IWORK_EXTS = (".pages", ".numbers", ".key")
ZIP_LIKE = ("application/zip", "application/octet-stream", "application/x-zip", "application/x-ole-storage")


def confidence(ref: InputRef, mimes: tuple[str, ...], exts: tuple[str, ...]) -> float:
    """Part 2 convention 2: 1.0 for a detected mime match, 0.9 for an extension match on a generic container
    mime (zip, octet-stream), 0.0 otherwise. A text/* or image/* detection never yields to the extension."""
    mime = (ref.detected.mime if ref.detected else None) or ""
    if mime.lower() in mimes:
        return 1.0
    ext = Path(ref.display).suffix.lower()
    if ext in exts and (not mime or mime in ZIP_LIKE or mime.startswith("application/")):
        return 0.9
    return 0.0


def _extra_bool(options: ConvertOptions, key: str, default: bool) -> bool:
    v = options.extra.get(f"office.{key}")
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _extra_int(options: ConvertOptions, key: str, default: int) -> int:
    v = options.extra.get(f"office.{key}")
    if v is None or isinstance(v, bool):
        return default
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def _extra_str(options: ConvertOptions, key: str, default: str, allowed: tuple[str, ...]) -> str:
    v = options.extra.get(f"office.{key}")
    if isinstance(v, str) and v.strip().lower() in allowed:
        return v.strip().lower()
    return default


@dataclass(frozen=True, slots=True)
class OfficeOptions:
    """`options.office` from Part 2 2h, read from `ConvertOptions.extra["office.<name>"]` plus the shared
    ConvertOptions switches (tracked_changes, comments, formulas)."""

    tracked_changes: bool = True
    comments: bool = True
    include_headers_footers: bool = False
    include_hidden_slides: bool = True
    include_hidden_sheets: bool = True
    include_notes: bool = True
    infer_headings: bool = True
    keep_hidden: bool = False
    formulas: str = "sidecar"
    max_rows: int = 10_000
    max_cols: int = 256
    max_sheets: int = 50
    max_slides: int = 500
    libreoffice_timeout_s: int = 120
    libreoffice_max_bytes: int = 100 * MB

    @classmethod
    def from_options(cls, options: ConvertOptions) -> OfficeOptions:
        formulas = _extra_str(options, "formulas", "sidecar", ("sidecar", "inline", "table", "off"))
        if not options.formulas:
            formulas = "off"
        return cls(
            tracked_changes=options.tracked_changes and _extra_str(options, "track_changes", "all", ("all",)) == "all",
            comments=options.comments and _extra_bool(options, "include_comments", True),
            include_headers_footers=_extra_bool(options, "include_headers_footers", False),
            include_hidden_slides=_extra_bool(options, "include_hidden_slides", True),
            include_hidden_sheets=_extra_bool(options, "include_hidden_sheets", True),
            include_notes=_extra_bool(options, "include_notes", True),
            infer_headings=_extra_bool(options, "infer_headings", True),
            keep_hidden=_extra_bool(options, "keep_hidden", False),
            formulas=formulas,
            max_rows=_extra_int(options, "max_rows", 10_000),
            max_cols=_extra_int(options, "max_cols", 256),
            max_sheets=_extra_int(options, "max_sheets", 50),
            max_slides=_extra_int(options, "max_slides", 500),
            libreoffice_timeout_s=_extra_int(options, "libreoffice_timeout_s", 120),
            libreoffice_max_bytes=_extra_int(options, "libreoffice_max_bytes", 100 * MB),
        )


def check_size(ref: InputRef, max_bytes: int, what: str) -> None:
    """Refuse inputs over the converter's byte cap (Part 2 13.4: Office refuses over bytes)."""
    size = ref.size()
    if size > max_bytes:
        raise ConversionError(
            f"{what} input of {size} bytes exceeds the {max_bytes} byte cap",
            user_message=f"This {what} file is larger than the {max_bytes // MB} MB limit.",
            retryable_with_fallback=False,
        )


@dataclass(slots=True)
class SpanBuilder:
    """Accumulates inline spans, merging neighbours with identical styling and cleaning text."""

    stats: CleanStats
    spans: list[InlineSpan] = field(default_factory=list)

    def add(
        self,
        text: str,
        styles: tuple[InlineStyle, ...] = (),
        href: str | None = None,
        footnote_ref: str | None = None,
        math: str | None = None,
        *,
        change: str | None = None,
        change_author: str | None = None,
        change_id: str | None = None,
    ) -> None:
        text = clean_text(text, self.stats)
        if not text and footnote_ref is None:
            return
        st = sorted(set(styles), key=list(InlineStyle).index)
        last = self.spans[-1] if self.spans else None
        if (
            last is not None
            and footnote_ref is None
            and math is None
            and last.footnote_ref is None
            and last.math is None
            and last.styles == st
            and last.href == href
            and (last.change, last.change_author, last.change_id) == (change, change_author, change_id)
        ):
            self.spans[-1] = last.model_copy(update={"text": last.text + text})
            return
        self.spans.append(
            InlineSpan(
                text=text,
                styles=st,
                href=href,
                footnote_ref=footnote_ref,
                math=math,
                change=change,
                change_author=change_author if change else None,
                change_id=change_id if change else None,
            )
        )

    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    def stripped(self) -> list[InlineSpan]:
        """Spans with leading/trailing whitespace of the whole run removed."""
        spans = [s.model_copy() for s in self.spans]
        while spans and not spans[0].footnote_ref and not spans[0].text.strip():
            spans.pop(0)
        while spans and not spans[-1].footnote_ref and not spans[-1].text.strip():
            spans.pop()
        if spans and not spans[0].footnote_ref:
            spans[0] = spans[0].model_copy(update={"text": spans[0].text.lstrip()})
        if spans and not spans[-1].footnote_ref:
            spans[-1] = spans[-1].model_copy(update={"text": spans[-1].text.rstrip()})
        return spans


class BlockList:
    """Ordered blocks with ids assigned at insertion, so anchors (comments, tracked changes, slide children)
    can reference a block before `Document.finalize()` runs. Ids follow finalize()'s `b0001` pattern."""

    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self._n = 0

    def add(self, block: Block) -> str:
        if not block.id:
            self._n += 1
            block.id = f"b{self._n:04d}"
        self.blocks.append(block)
        return block.id

    def next_id(self) -> str:
        """Reserve the id the next anonymous block will get."""
        self._n += 1
        return f"b{self._n:04d}"


def clean_warning(stats: CleanStats) -> Warning | None:
    if not stats.total:
        return None
    return Warning(
        kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
        severity="info",
        message=f"Removed {stats.total} control or invisible characters.",
        count=stats.total,
        detail={"control": stats.control, "invisible": stats.invisible, "surrogates": stats.surrogates},
    )


_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$")


def parse_datetime(value: str | None) -> datetime | None:
    """Lenient ISO 8601 parsing for document properties; None when absent or malformed."""
    if not value:
        return None
    s = value.strip()
    if not _ISO.match(s):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


SAFE_SCHEMES = ("http://", "https://", "mailto:", "ftp://", "#")


def safe_href(target: str | None) -> str | None:
    """Keep only web, mail, and in-document links; drop file:, javascript:, UNC paths, and the like."""
    if not target:
        return None
    t = target.strip()
    return t if t.lower().startswith(SAFE_SCHEMES) else None
