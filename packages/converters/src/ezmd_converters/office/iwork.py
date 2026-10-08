"""iWork (.pages, .numbers, .key): the structured path is Docling's iWork backend (`ezmd[iwork]`), registered
as `documents.iwork` and Unavailable until it is integrated (ROADMAP P1-T01 assigns iWork to Docling). The
embedded-preview fallback (`iwork_preview_fallback`, Part 2 2b item 6) needs the PDF family and is a follow-up."""

from __future__ import annotations

from ezmd.registry import Unavailable
from ezmd_converters.office._common import FAMILY, IWORK_MIMES


def unavailable() -> Unavailable:
    return Unavailable(
        id="documents.iwork",
        family=FAMILY,
        reason="The Docling iWork backend is not integrated yet; export to DOCX, XLSX, or PPTX and convert that.",
        requires_extras=("iwork",),
        mimes=IWORK_MIMES,
    )
