"""Code family (docs/spec/part2.md section 8): single source files and repository packing.

Phase 1 converters in this package: `code.source_file` (one file, one fenced block, optional signatures-only
and outline) and `code.repo_pack` (zip or tar.gz of a repository, or a GitHub repository URL fetched as a
codeload tarball). Both redact secrets before text enters the IR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from intomd_converters.code.languages import CODE_MIMES

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {mime: ["code.source_file", "text.plain"] for mime in CODE_MIMES}


def converters() -> list[Converter | Unavailable]:
    from intomd_converters.code.repo_pack import RepoPackConverter
    from intomd_converters.code.source_file import SourceFileConverter

    return [SourceFileConverter(), RepoPackConverter()]
