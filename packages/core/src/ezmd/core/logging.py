"""ezmd.core.logging: redaction filter for every ezmd log handler (docs/spec/part1.md section 8.4).

Redacts API keys (header values and the `ak_<env>_<22 base62>` pattern), Authorization/Bearer
values, Turnstile tokens, fetch-node claim tokens, and URL userinfo, in the message, the args, and
string-valued `extra` attributes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

REDACTED = "[REDACTED]"

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bak_[a-z0-9]+_[A-Za-z0-9]{22}\b"), REDACTED),
    (re.compile(r"\bct_[A-Za-z0-9_-]{8,}\b"), REDACTED),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"), r"\1 " + REDACTED),
    (
        re.compile(
            r"(?i)\b(x-api-key|authorization|turnstile_token|cf-turnstile-response|claim_token)"
            r"(\"?\s*[:=]\s*\"?)[^\s\",;&]+"
        ),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"\b0\.[A-Za-z0-9_-]{40,}"), REDACTED),  # Turnstile response tokens
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+(?::[^/\s@]*)?@"), r"\1" + REDACTED + "@"),
)

_STD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def redact(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def _redact_value(v: Any) -> Any:
    if isinstance(v, str):
        return redact(v)
    if isinstance(v, dict):
        return {k: _redact_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(_redact_value(x) for x in v)
    return v


class RedactionFilter(logging.Filter):
    """Attach to handlers (not loggers) so records from every library are covered."""

    def filter(self, record: logging.LogRecord) -> bool:
        # 1. Redact each string argument in place. `record.args` is kept (non-string values untouched)
        #    because some formatters, such as uvicorn's access formatter, unpack it positionally.
        # 2. If the fully formatted message still contains something redactable (a pattern spanning
        #    the template and an argument, e.g. "Bearer %s"), replace the record with the redacted
        #    formatted text. Redacting the template alone would eat format specifiers and break
        #    formatting ("not all arguments converted").
        if isinstance(record.args, dict):
            record.args = {k: _redact_value(v) for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact_value(a) for a in record.args)
        try:
            formatted = record.getMessage()
        except Exception:
            formatted = str(record.msg)
            record.args = None
        cleaned = redact(formatted)
        if cleaned != formatted:
            record.msg = cleaned
            record.args = None
        for key, value in list(record.__dict__.items()):
            if key not in _STD_ATTRS:
                setattr(record, key, _redact_value(value))
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def install(handler: logging.Handler | None = None) -> logging.Handler:
    """Add the redaction filter to `handler` (or a new stderr handler on the `ezmd` logger)."""
    if handler is None:
        handler = logging.StreamHandler()
        logging.getLogger("ezmd").addHandler(handler)
    if not any(isinstance(f, RedactionFilter) for f in handler.filters):
        handler.addFilter(RedactionFilter())
    return handler
