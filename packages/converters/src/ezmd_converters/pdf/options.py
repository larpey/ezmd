"""PDF family options (docs/spec/part2.md 1h), read from `ConvertOptions.extra` keys `pdf.<name>`.

The CLI exposes them as `--pdf.<name>=value`; the API passes them through `extra`. Unknown values fall back
to the default with a ValueError naming the option, so a typo fails fast instead of being ignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from ezmd.registry import ConvertOptions

OcrMode = Literal["auto", "force", "off"]
FormsMode = Literal["table", "inline", "off"]
ImagesMode = Literal["extract", "skip", "caption"]
StructMode = Literal["prefer", "ignore", "only"]

DEFAULT_MAX_PAGES = 2000
DEFAULT_BATCH_PAGES = 25
MAX_PASSWORD_TRIES = 50
"""docs/spec/part2.md 1c step 3: never try more than 50 passwords."""
ENGINES = ("docling", "pdfium", "pypdf")
"""`pypdf` is accepted as an alias of the text-layer engine (the spec's name for it; DECISIONS P1-T01-pdf)."""


@dataclass(frozen=True, slots=True)
class PdfOptions:
    engine: str = "docling"
    ocr: OcrMode = "auto"
    max_pages: int = DEFAULT_MAX_PAGES
    batch_pages: int = DEFAULT_BATCH_PAGES
    password: str | None = None
    password_file: str | None = None
    forms: FormsMode = "table"
    images: ImagesMode = "extract"
    keep_running_headers: bool = False
    dehyphenate: bool = True
    structure_tree: StructMode = "prefer"
    page_markers: bool = True

    def passwords(self) -> list[str]:
        """Candidate passwords in spec order: empty, `password`, then `password_file` lines; at most 50."""
        out = [""]
        if self.password:
            out.append(self.password)
        if self.password_file:
            try:
                with open(self.password_file, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if len(out) >= MAX_PASSWORD_TRIES:
                            break
                        pw = line.rstrip("\r\n")
                        if pw:
                            out.append(pw)
            except OSError:
                pass
        return out[:MAX_PASSWORD_TRIES]


def _choice(raw: object, name: str, allowed: tuple[str, ...], default: str) -> str:
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value not in allowed:
        raise ValueError(f"pdf.{name} must be one of {', '.join(allowed)}; got {raw!r}")
    return value


def _int(raw: object, name: str, default: int, lo: int, hi: int) -> int:
    if raw is None:
        return default
    try:
        value = int(str(raw))
    except ValueError as e:
        raise ValueError(f"pdf.{name} must be an integer; got {raw!r}") from e
    return max(lo, min(hi, value))


def _bool(raw: object, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def pdf_options(options: ConvertOptions) -> PdfOptions:
    """Build PdfOptions from `options.extra` (`pdf.*` keys), the shared options, and `EZMD_PDF_ENGINE`."""
    ex = options.extra
    cap = DEFAULT_MAX_PAGES if options.max_pages is None else max(1, options.max_pages)
    engine_raw = ex.get("pdf.engine") or os.environ.get("EZMD_PDF_ENGINE")
    engine = _choice(engine_raw, "engine", ENGINES, "docling")
    ocr_default = "auto" if options.ocr else "off"
    password = ex.get("pdf.password")
    password_file = ex.get("pdf.password_file")
    return PdfOptions(
        engine="pdfium" if engine == "pypdf" else engine,
        ocr=_choice(ex.get("pdf.ocr"), "ocr", ("auto", "force", "off"), ocr_default),  # type: ignore[arg-type]
        max_pages=_int(ex.get("pdf.max_pages"), "max_pages", cap, 1, cap),
        batch_pages=_int(ex.get("pdf.batch_pages"), "batch_pages", DEFAULT_BATCH_PAGES, 1, 500),
        password=None if password is None else str(password),
        password_file=None if password_file is None else str(password_file),
        forms=_choice(ex.get("pdf.forms"), "forms", ("table", "inline", "off"), "table"),  # type: ignore[arg-type]
        images=_choice(ex.get("pdf.images"), "images", ("extract", "skip", "caption"), "extract"),  # type: ignore[arg-type]
        keep_running_headers=_bool(ex.get("pdf.keep_running_headers"), False),
        dehyphenate=_bool(ex.get("pdf.dehyphenate"), True),
        structure_tree=_choice(ex.get("pdf.structure_tree"), "structure_tree", ("prefer", "ignore", "only"), "prefer"),  # type: ignore[arg-type]
        page_markers=_bool(ex.get("pdf.page_markers"), True),
    )
