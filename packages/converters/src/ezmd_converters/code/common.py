"""Helpers shared by the code converters: option parsing, token counts, and warnings."""

from __future__ import annotations

from ezmd.ir import Warning, WarningKind
from ezmd.registry import ConvertOptions, ExtraValue
from ezmd.render.tokens import TiktokenCounter
from ezmd_converters.code.secrets import Redactions

__all__ = ["count_tokens", "opt_bool", "opt_int", "opt_str", "secret_warning"]

_COUNTER = TiktokenCounter("cl100k_base")


def count_tokens(text: str) -> int:
    """cl100k_base token count (8b step 1), with ezmd.render.tokens' estimate fallback offline."""
    return _COUNTER.count(text)


def _extra(options: ConvertOptions, key: str) -> ExtraValue | None:
    return options.extra.get(key, options.extra.get(f"code.{key}"))


def opt_bool(options: ConvertOptions, key: str, default: bool) -> bool:
    value = _extra(options, key)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def opt_int(options: ConvertOptions, key: str, default: int | None) -> int | None:
    value = _extra(options, key)
    if value is None or isinstance(value, bool):
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def opt_str(options: ConvertOptions, key: str) -> str | None:
    value = _extra(options, key)
    return value if isinstance(value, str) and value.strip() else None


def secret_warning(found: Redactions) -> Warning | None:
    """One `secret_redacted` warning with counts by rule and file:line locations (never the values)."""
    if not found.total:
        return None
    detail: dict[str, str | int | float] = {f"rule.{rule}": n for rule, n in sorted(found.by_rule.items())}
    locs = [f"{p}:{line}" if p else str(line) for p, line, _rule in sorted(found.locations)[:200]]
    detail["locations"] = ", ".join(locs)
    rules = ", ".join(f"{rule} ({n})" for rule, n in sorted(found.by_rule.items()))
    return Warning(
        kind=WarningKind.SECRET_REDACTED,
        message=f"Redacted {found.total} value(s) that look like secrets: {rules}.",
        count=found.total,
        detail=detail,
    )
