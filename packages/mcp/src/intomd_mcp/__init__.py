"""intomd MCP server (docs/spec/part4.md section 4.4).

A thin client over the intomd library (local mode) or an intomd REST instance (remote mode). It contains
no conversion logic: it validates tool arguments, enforces the allowed file roots, pages the renderer's
output with its opaque cursor, and reports warnings verbatim.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("intomd-mcp")
except PackageNotFoundError:  # running from a source tree without metadata
    __version__ = "0.0.0"

USER_AGENT = f"intomd-mcp/{__version__}"

__all__ = ["USER_AGENT", "__version__"]
