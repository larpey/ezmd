"""intomd.builtin: registers the converters shipped in `intomd-converters`.

Built-in converters live in the separate `intomd_converters` package (docs/spec/part1.md section 1.3
layout). They are registered here with source "builtin" rather than through entry points so that
`intomd` always resolves them first and a broken third-party plugin cannot shadow them (D-0003).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import ConverterRegistry

log = logging.getLogger(__name__)


def register_builtins(reg: ConverterRegistry) -> None:
    try:
        from intomd_converters import builtin_converters
    except ImportError as e:
        log.warning("intomd-converters is not installed; no built-in converters: %s", e)
        return
    for conv in builtin_converters():
        reg.register(conv, source="builtin")  # Unavailable entries are recorded with their reason
