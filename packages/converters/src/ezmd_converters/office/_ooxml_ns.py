"""OOXML namespace URIs and Clark-notation helpers shared by the DOCX and PPTX parsers."""

from __future__ import annotations

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
V = "urn:schemas-microsoft-com:vml"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
P188 = "http://schemas.microsoft.com/office/powerpoint/2018/8/main"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

REL_OFFICE_DOCUMENT = "/officedocument"
REL_STYLES = "/styles"
REL_NUMBERING = "/numbering"
REL_FOOTNOTES = "/footnotes"
REL_ENDNOTES = "/endnotes"
REL_COMMENTS = "/comments"
REL_COMMENTS_EXT = "/commentsextended"
REL_IMAGE = "/image"
REL_HYPERLINK = "/hyperlink"


def q(ns: str, local: str) -> str:
    """Clark notation `{ns}local` as lxml uses it."""
    return f"{{{ns}}}{local}"


def local(tag: object) -> str:
    """Local name of an lxml tag (comments and processing instructions return "")."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def ns_of(tag: object) -> str:
    if not isinstance(tag, str) or not tag.startswith("{"):
        return ""
    return tag[1:].split("}", 1)[0]
