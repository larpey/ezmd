"""documents.docx: native DOCX converter (lxml over the sanitized OOXML package).

Part 2 section 2: styles, numbering, tables with gridSpan/vMerge, footnotes and endnotes, tracked changes
(w:ins, w:del, w:moveFrom, w:moveTo, w:rPrChange), comments with replies and resolved state, text boxes,
OMML equations, hidden text. python-docx does not expose revisions or comments, and Pandoc (GPL) would only
be an optional external binary, so the default path reads the XML directly (docs/decisions/P1-T01-office.md).
"""

from __future__ import annotations

from intomd.context import Limits
from intomd.inputs import InputRef
from intomd.ir import Document, Heading, Metadata, SourceType, Warning, WarningKind, spans_text
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.office._common import (
    DOCX_EXTS,
    DOCX_MIMES,
    FAMILY,
    MB,
    OfficeOptions,
    check_size,
    clean_warning,
    confidence,
)
from intomd_converters.office._ooxml_ns import (
    REL_COMMENTS,
    REL_COMMENTS_EXT,
    REL_ENDNOTES,
    REL_FOOTNOTES,
    REL_NUMBERING,
    REL_OFFICE_DOCUMENT,
    REL_STYLES,
    W,
    q,
)
from intomd_converters.office._package import OfficePackage
from intomd_converters.office.docx_parts import load_comments, load_core
from intomd_converters.office.docx_walker import DocxWalker

_PART_TYPES = {
    "styles": REL_STYLES,
    "numbering": REL_NUMBERING,
    "footnotes": REL_FOOTNOTES,
    "endnotes": REL_ENDNOTES,
    "comments": REL_COMMENTS,
    "comments_ext": REL_COMMENTS_EXT,
}


def main_part(pkg: OfficePackage, default: str) -> str:
    for rel in pkg.rels("").values():
        if rel.type.lower().endswith(REL_OFFICE_DOCUMENT) and not rel.external:
            return rel.target
    return default


class DocxConverter:
    id = "documents.docx"
    family = FAMILY
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = DOCX_MIMES
    limits = Limits(max_bytes=200 * MB, timeout_s=120)

    def can_handle(self, ref: InputRef) -> float:
        return confidence(ref, DOCX_MIMES, DOCX_EXTS)

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        check_size(ref, self.limits.max_bytes or 200 * MB, "Word")
        options.ctx.progress("parse", 0.0, "Reading the Word package")
        pkg = OfficePackage(ref.read(), what="DOCX")
        return convert_package(pkg, ref.display, options, mime=ref.detected.mime if ref.detected else None)


def convert_package(pkg: OfficePackage, source: str, options: ConvertOptions, *, mime: str | None = None) -> Document:
    doc_part = main_part(pkg, "word/document.xml")
    if not pkg.has("[Content_Types].xml") or not pkg.has(doc_part):
        raise ConversionError(
            f"{source}: missing [Content_Types].xml or {doc_part}", user_message="This is not a valid Word document."
        )
    opts = OfficeOptions.from_options(options)
    rels = pkg.rels(doc_part)
    parts: dict[str, str] = {}
    for name, suffix in _PART_TYPES.items():
        for rel in rels.values():
            if not rel.external and rel.type.lower().endswith(suffix):
                parts[name] = rel.target
    root = pkg.xml(doc_part)
    body = root.find(q(W, "body")) if root is not None else None
    if body is None:
        raise ConversionError(f"{source}: no w:body", user_message="This Word document has no body.")
    comments = load_comments(pkg, parts.get("comments"), parts.get("comments_ext")) if opts.comments else {}
    walker = DocxWalker(pkg, doc_part, source, opts, options, parts, comments)
    blocks = walker.walk(body)
    core = load_core(pkg)
    meta = Metadata(
        source=source,
        source_type=SourceType.DOCX,
        mime=mime,
        title=core.title,
        author=core.author,
        authors=[core.author] if core.author else [],
        published=core.created,
        modified=core.modified,
        description=core.description,
        keywords=core.keywords,
        pages=core.pages,
    )
    if core.revision:
        meta.extra["revision"] = core.revision
    if meta.title is None:
        first = next((b for b in blocks if isinstance(b, Heading)), None)
        if first is not None:
            meta.title = spans_text(first.spans).strip() or None
    doc = Document(metadata=meta, blocks=blocks)
    doc.warnings.extend(pkg.warnings())
    doc.warnings.extend(_warnings(walker, opts, meta))
    if not doc.blocks:
        doc.warnings.append(
            Warning(kind=WarningKind.EXTRACTION_EMPTY, message="The Word document contains no text.", severity="error")
        )
    options.ctx.progress("parse", 1.0, "Word document parsed")
    return doc.finalize()


def _warnings(walker: DocxWalker, opts: OfficeOptions, meta: Metadata) -> list[Warning]:
    out: list[Warning] = []
    c, s = walker.counters, walker.stats
    if c.hidden_runs:
        if opts.keep_hidden:
            meta.extra["hidden_text"] = " ".join(t.strip() for t in c.hidden_text if t.strip())[:20_000]
        out.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                message=f"Excluded {c.hidden_runs} hidden or white-on-white text runs from the body.",
                count=c.hidden_runs,
                detail={"hidden_runs": c.hidden_runs},
            )
        )
    cw = clean_warning(walker.clean)
    if cw is not None:
        out.append(cw)
    if s.textboxes:
        out.append(
            Warning(
                kind=WarningKind.TEXTBOX_CONTENT_RELOCATED,
                message=f"Moved the content of {s.textboxes} text boxes after their anchoring paragraphs.",
                count=s.textboxes,
            )
        )
    if s.inferred_headings:
        out.append(
            Warning(
                kind=WarningKind.HEADING_INFERRED_FROM_FORMATTING,
                message=f"Inferred {s.inferred_headings} headings from bold, enlarged text.",
                count=s.inferred_headings,
            )
        )
    if s.ole:
        out.append(
            Warning(
                kind=WarningKind.OLE_OBJECT_SKIPPED,
                message=f"Skipped {s.ole} embedded OLE objects.",
                count=s.ole,
            )
        )
    if c.math_partial:
        out.append(
            Warning(
                kind=WarningKind.EQUATION_PARTIAL,
                message=f"{c.math_partial} equations used constructs without a LaTeX mapping; plain text was kept.",
                count=c.math_partial,
            )
        )
    return out
