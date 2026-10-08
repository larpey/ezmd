"""Ebooks family (converter family "documents", docs/spec/part2.md section 4): EPUB 2/3 and Jupyter notebooks.

Markdown and plain text live in the `text` family. MOBI/AZW/CHM (Calibre), FB2, LaTeX, reStructuredText,
AsciiDoc, Org, Textile, and MediaWiki are planned (docs/converters/ebooks.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    "application/epub+zip": ["documents.epub", "archives.archive"],
    "application/x-ipynb+json": ["documents.ipynb"],
}


def converters() -> list[Converter | Unavailable]:
    from intomd_converters.ebooks.epub import EpubConverter
    from intomd_converters.ebooks.notebook import NotebookConverter

    return [EpubConverter(), NotebookConverter()]
