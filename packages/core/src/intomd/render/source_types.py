"""intomd.render.source_types: map IR SourceType onto the frontmatter `source_type` enum (D-0017 item 5).

The frontmatter enum is docs/spec/part3.md section 13, amended with `text` and `markdown`:

    web, pdf, docx, pptx, xlsx, epub, image, audio, video, podcast, post, thread, chat_export, email,
    code, data, notebook, text, markdown, other

Full mapping (IR SourceType -> frontmatter source_type):

    pdf          -> pdf
    docx         -> docx
    pptx         -> pptx
    xlsx         -> xlsx
    odf          -> other        (one IR type covers text, sheet and slide files; no single nearest value)
    iwork        -> other        (same reason as odf)
    rtf          -> other
    epub         -> epub
    markup       -> markdown     (Markdown, MDX, reST, AsciiDoc, LaTeX: all rendered as Markdown text)
    notebook     -> notebook
    html         -> web
    web          -> web
    feed         -> web
    social       -> thread when the IR carries replies (Comment blocks), else post
    audio        -> audio
    video        -> video
    media_url    -> audio when the mime is audio/* or metadata.extra["media_kind"] == "audio", else video
    image        -> image
    code         -> code
    repo         -> code
    openapi      -> code         (API specs belong to the code family, Part 2)
    email        -> email
    chat         -> chat_export
    data         -> data
    finance_xml  -> data
    calendar     -> data
    notes        -> other        (exports mix Markdown, HTML and proprietary formats)
    archive      -> other
    text         -> text
    other        -> other

A converter may override the result with `metadata.extra["source_type"]` (for example `podcast`) when the
value is in the enum; out-of-enum overrides are ignored.
"""

from __future__ import annotations

from intomd.ir import Comment, Document, SourceType

__all__ = ["FRONTMATTER_SOURCE_TYPES", "frontmatter_source_type"]

FRONTMATTER_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "web",
        "pdf",
        "docx",
        "pptx",
        "xlsx",
        "epub",
        "image",
        "audio",
        "video",
        "podcast",
        "post",
        "thread",
        "chat_export",
        "email",
        "code",
        "data",
        "notebook",
        "text",
        "markdown",
        "other",
    }
)

_DIRECT: dict[SourceType, str] = {
    SourceType.PDF: "pdf",
    SourceType.DOCX: "docx",
    SourceType.PPTX: "pptx",
    SourceType.XLSX: "xlsx",
    SourceType.ODF: "other",
    SourceType.IWORK: "other",
    SourceType.RTF: "other",
    SourceType.EPUB: "epub",
    SourceType.MARKUP: "markdown",
    SourceType.NOTEBOOK: "notebook",
    SourceType.HTML: "web",
    SourceType.WEB: "web",
    SourceType.FEED: "web",
    SourceType.AUDIO: "audio",
    SourceType.VIDEO: "video",
    SourceType.IMAGE: "image",
    SourceType.CODE: "code",
    SourceType.REPO: "code",
    SourceType.OPENAPI: "code",
    SourceType.EMAIL: "email",
    SourceType.CHAT: "chat_export",
    SourceType.DATA: "data",
    SourceType.FINANCE_XML: "data",
    SourceType.CALENDAR: "data",
    SourceType.NOTES: "other",
    SourceType.ARCHIVE: "other",
    SourceType.TEXT: "text",
    SourceType.OTHER: "other",
}


def frontmatter_source_type(doc: Document) -> str:
    """The frontmatter `source_type` for a Document (see the module docstring for the table)."""
    meta = doc.metadata
    override = meta.extra.get("source_type")
    if isinstance(override, str) and override in FRONTMATTER_SOURCE_TYPES:
        return override
    st = meta.source_type
    if st == SourceType.SOCIAL:
        return "thread" if any(isinstance(b, Comment) for b in doc.blocks) else "post"
    if st == SourceType.MEDIA_URL:
        audio = (meta.mime or "").startswith("audio/") or meta.extra.get("media_kind") == "audio"
        return "audio" if audio else "video"
    return _DIRECT[st]
