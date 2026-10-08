"""Office family (`documents.*`): DOCX, PPTX, XLSX, ODF, RTF, legacy formats via LibreOffice, iWork.

docs/spec/part2.md section 2 and docs/converters/office.md. Every zip package is validated and sanitized by
`_package.OfficePackage` (archive limits, macro and ActiveX removal, external relationship filtering, DTD
refusal) before any parser sees it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from intomd_converters.office._common import (
    DOCX_MIMES,
    IWORK_MIMES,
    LEGACY_MIMES,
    ODF_MIMES,
    PPTX_MIMES,
    RTF_MIMES,
    XLSX_MIMES,
)

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    **{m: ["documents.docx"] for m in DOCX_MIMES},
    **{m: ["documents.pptx"] for m in PPTX_MIMES},
    **{m: ["documents.xlsx"] for m in XLSX_MIMES},
    **{m: ["documents.odf", "documents.libreoffice"] for m in ODF_MIMES},
    **{m: ["documents.libreoffice", "documents.rtf"] for m in RTF_MIMES},
    **{m: ["documents.libreoffice"] for m in LEGACY_MIMES},
    **{m: ["documents.iwork"] for m in IWORK_MIMES},
}


def converters() -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable

    out: list[Converter | Unavailable] = []
    from intomd_converters.office.docx import DocxConverter
    from intomd_converters.office.iwork import unavailable
    from intomd_converters.office.libreoffice import LibreOfficeConverter, find_soffice
    from intomd_converters.office.odf import OdfConverter
    from intomd_converters.office.pptx import PptxConverter
    from intomd_converters.office.rtf import RtfConverter

    out.extend([DocxConverter(), PptxConverter(), OdfConverter()])
    if find_soffice() is None:
        out.append(
            Unavailable(
                id="documents.libreoffice",
                family="documents",
                reason="libreoffice_missing: soffice was not found; install LibreOffice or set LIBREOFFICE_PATH "
                "to convert .doc, .xls, .ppt, .xlsb, .wpd (RTF and ODF fall back to native parsers).",
                mimes=LibreOfficeConverter.mimes,
            )
        )
    else:
        out.append(LibreOfficeConverter())
    out.append(unavailable())
    try:
        import openpyxl  # type: ignore[import-untyped]  # noqa: F401

        from intomd_converters.office.xlsx import XlsxConverter
    except ImportError as e:
        out.append(
            Unavailable(
                id="documents.xlsx",
                family="documents",
                reason=f"openpyxl is not installed: {e}",
                mimes=XLSX_MIMES,
            )
        )
    else:
        out.append(XlsxConverter())
    try:
        import striprtf  # noqa: F401
    except ImportError as e:
        out.append(Unavailable(id="documents.rtf", family="documents", reason=f"striprtf is not installed: {e}"))
    else:
        out.append(RtfConverter())
    return out
