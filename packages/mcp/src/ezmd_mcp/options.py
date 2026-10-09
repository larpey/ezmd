"""ezmd_mcp.options: which conversion options an MCP tool caller may set.

Tool arguments come from the model, and the model reads untrusted documents, so a tool call must not
widen what the operator allowed. Mirrors `ezmd_api.options`: an allowlist of output options
(TOOL_FIELDS), a set of limits the caller may only lower (LIMIT_FIELDS, capped by the operator's
`ezmd-mcp --max-*` flags), and everything else (`extra`, `converter`, `experimental`) refused.
`allow_private_networks` keeps its own server gate in `LocalBackend`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from ezmd_mcp.errors import ToolFailure

__all__ = ["LIMIT_FIELDS", "SERVER_FIELDS", "TOOL_FIELDS", "OperatorLimits", "tool_options"]

_DEFAULT_MAX_PAGES = 500
_DEFAULT_MAX_DURATION_S = 3 * 3600.0
_DEFAULT_MAX_SECONDS = 600.0
_DEFAULT_MAX_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class OperatorLimits:
    """Ceilings set by whoever started ezmd-mcp. Defaults equal `ezmd.library.Options` defaults."""

    max_bytes: int = _DEFAULT_MAX_BYTES
    max_seconds: float = _DEFAULT_MAX_SECONDS
    max_pages: int = _DEFAULT_MAX_PAGES
    max_duration_seconds: float = _DEFAULT_MAX_DURATION_S

    def as_dict(self) -> dict[str, int | float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


TOOL_FIELDS: tuple[str, ...] = (
    "ocr",
    "asr_model",
    "diarize",
    "languages",
    "extract_images",
    "tracked_changes",
    "comments",
    "formulas",
    "render",
    "allow_private_networks",
)
"""Options a tool call may set freely (output shape, not resource use)."""

LIMIT_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(OperatorLimits))
"""Options a tool call may set only at or below the operator's limit."""

SERVER_FIELDS: dict[str, str] = {
    "extra": "family engine options (archive caps, timeouts) are operator settings",
    "converter": "forcing a converter bypasses detection; not a tool-call choice",
    "experimental": "experimental converters are an operator policy",
}
"""Options a tool call may not set, with the reason shown in the error."""


def tool_options(options: dict[str, Any], limits: OperatorLimits) -> dict[str, Any]:
    """Check tool-call options and return the `Options` kwargs with the operator limits applied."""
    for key in options:
        if key in SERVER_FIELDS:
            raise ToolFailure("invalid_request", f"options.{key} is not settable by tool calls ({SERVER_FIELDS[key]}).")
        if key not in TOOL_FIELDS and key not in LIMIT_FIELDS:
            allowed = ", ".join((*TOOL_FIELDS, *LIMIT_FIELDS))
            raise ToolFailure("invalid_request", f"Unknown option {str(key)[:64]!r}; allowed: {allowed}.")
    out = {k: v for k, v in options.items() if k in TOOL_FIELDS}
    for key in LIMIT_FIELDS:
        ceiling = getattr(limits, key)
        if key not in options:
            out[key] = ceiling
            continue
        value = options[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ToolFailure("invalid_request", f"options.{key} must be a number at most {ceiling}.")
        if value > ceiling:
            raise ToolFailure(
                "invalid_request",
                f"options.{key} may not exceed this server's limit of {ceiling} (set by the operator).",
            )
        out[key] = value
    return out
