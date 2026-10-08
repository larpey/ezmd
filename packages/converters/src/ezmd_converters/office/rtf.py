"""documents.rtf: plain-text RTF fallback on striprtf (BSD-3-Clause), Part 2 2b item 2.

The structured path for RTF is LibreOffice to DOCX (`documents.libreoffice`, first in the chain when
`soffice` is installed). This converter keeps the text, the paragraph breaks, and the info-group title and
author; formatting, tables, and pictures are not recovered. When LibreOffice is absent it says so with
`libreoffice_missing`.
"""

from __future__ import annotations

import re

from ezmd.context import Limits
from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef
from ezmd.ir import Document, Heading, InlineSpan, Metadata, Paragraph, Provenance, SourceType, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.office._common import FAMILY, MB, RTF_EXTS, RTF_MIMES, check_size, clean_warning, confidence
from ezmd_converters.office.libreoffice import find_soffice

_BS = chr(92)
_INFO = {
    "title": re.compile(re.escape("{" + _BS + "title") + r"\s+([^{}]*)\}"),
    "author": re.compile(re.escape("{" + _BS + "author") + r"\s+([^{}]*)\}"),
}
_CODEPAGE = re.compile(re.escape(_BS) + r"ansicpg(\d+)")
_OBJECT = re.compile(re.escape("{" + _BS + "object"))
_PICT = re.compile(re.escape("{" + _BS + "pict"))


class RtfConverter:
    id = "documents.rtf"
    family = FAMILY
    priority = 5
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = RTF_MIMES
    limits = Limits(max_bytes=50 * MB, timeout_s=120)

    def can_handle(self, ref: InputRef) -> float:
        score = confidence(ref, RTF_MIMES, RTF_EXTS)
        if score == 0.0 and ref.head(6).startswith(b"{" + _BS.encode() + b"rtf"):
            return 0.7
        return score

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        from striprtf.striprtf import rtf_to_text

        check_size(ref, self.limits.max_bytes or 50 * MB, "RTF")
        raw = ref.read()
        if not raw.lstrip().startswith(b"{" + _BS.encode() + b"rtf"):
            raise ConversionError(
                f"{ref.display} does not start with an RTF header", user_message="This is not an RTF file."
            )
        text = raw.decode("latin-1")
        cp = _CODEPAGE.search(text[:4096])
        encoding = f"cp{cp.group(1)}" if cp else "cp1252"
        try:
            "".encode(encoding)
        except LookupError:
            encoding = "cp1252"
        options.ctx.check_deadline()
        try:
            plain = str(rtf_to_text(text, encoding=encoding, errors="replace"))  # type: ignore[no-untyped-call]
        except Exception as e:  # striprtf raises on malformed control words
            raise ConversionError(f"striprtf failed: {e}", user_message="The RTF file could not be read.") from e
        stats = CleanStats()
        meta = Metadata(
            source=ref.display, source_type=SourceType.RTF, mime=ref.detected.mime if ref.detected else None
        )
        for key, rx in _INFO.items():
            m = rx.search(text)
            if m and m.group(1).strip():
                value = clean_text(m.group(1).strip(), stats)
                if key == "title":
                    meta.title = value
                else:
                    meta.author = value
                    meta.authors = [value]
        meta.encoding = encoding
        doc = Document(metadata=meta)
        for i, line in enumerate(clean_text(plain, stats).split("\n")):
            body = " ".join(line.split())
            if body:
                doc.blocks.append(
                    Paragraph(
                        spans=[InlineSpan(text=body)], provenance=Provenance(source=ref.display, path=f"para[{i}]")
                    )
                )
        first = doc.blocks[0] if doc.blocks else None
        if meta.title and isinstance(first, Paragraph) and first.spans[0].text.strip() == meta.title:
            doc.blocks[0] = Heading(level=1, spans=first.spans, provenance=first.provenance)
        if find_soffice() is None:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.LIBREOFFICE_MISSING,
                    message="LibreOffice is not installed; the RTF was converted as plain text without formatting.",
                )
            )
        objects = len(_OBJECT.findall(text))
        if objects:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.OLE_OBJECT_SKIPPED, message=f"Skipped {objects} embedded objects.", count=objects
                )
            )
        picts = len(_PICT.findall(text))
        if picts:
            doc.warnings.append(
                Warning(kind=WarningKind.IMAGE_SKIPPED, message=f"Skipped {picts} embedded pictures.", count=picts)
            )
        cw = clean_warning(stats)
        if cw is not None:
            doc.warnings.append(cw)
        if not doc.blocks:
            doc.warnings.append(
                Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="The RTF file contains no text.")
            )
        return doc.finalize()
