"""intomd_api.logs: process logging with the intomd redaction filter on every handler
(docs/spec/part1.md section 8.4). Logs never contain document content or raw client IPs."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from intomd.core.logging import install
from intomd_api.settings import Settings

_STD = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STD and not key.startswith("_"):
                payload[key] = value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _StderrHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Resolves sys.stderr at emit time so a swapped or closed stream (test capture) is never used."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


_configured = False


def configure_logging(settings: Settings) -> None:
    """Install one stderr handler on the root logger (idempotent) and add the redaction filter to
    every root handler, so third-party library records are redacted too."""
    global _configured
    root = logging.getLogger()
    if not _configured:
        handler = _StderrHandler(sys.stderr)
        text_fmt = logging.Formatter("%(levelname)s %(name)s %(message)s")
        handler.setFormatter(JsonFormatter() if settings.log_format == "json" else text_fmt)
        root.addHandler(handler)
        _configured = True
    root.setLevel(settings.log_level.upper())
    for h in root.handlers:
        install(h)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            install(h)
