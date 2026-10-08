"""ezmd: convert anything to LLM-ready Markdown.

    >>> import ezmd
    >>> result = ezmd.convert("report.pdf", profile="compact")
    >>> print(result.markdown)

Names are resolved lazily so `import ezmd` stays fast (no engines, no renderer at import time).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0rc1"

__all__ = [
    "Options",
    "Progress",
    "Result",
    "__version__",
    "capabilities",
    "convert",
    "convert_async",
    "convert_many",
    "register_converter",
    "unload_models",
]

if TYPE_CHECKING:
    from ezmd.library import (
        Options,
        Progress,
        Result,
        capabilities,
        convert,
        convert_async,
        convert_many,
        register_converter,
        unload_models,
    )


def __getattr__(name: str) -> Any:
    if name in __all__ and name != "__version__":
        from ezmd import library

        return getattr(library, name)
    raise AttributeError(f"module 'ezmd' has no attribute {name!r}")
