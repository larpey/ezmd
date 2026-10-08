from __future__ import annotations

import io
import logging
from pathlib import Path

from ezmd.core.licensing import notify_once
from ezmd.core.logging import RedactionFilter, install, redact
from ezmd.core.textclean import CleanStats, clean_text

KEY = "ak_live_" + "A1b2C3d4E5f6G7h8I9j0Kl"


def test_redact_patterns() -> None:
    s = redact(f"X-API-Key: {KEY} Authorization: Bearer abc.def.ghi https://u:secret@host/x claim_token=ct_abcdefgh123")
    assert KEY not in s and "abc.def.ghi" not in s and "secret@" not in s and "ct_abcdefgh123" not in s
    assert "[REDACTED]" in s and "host/x" in s
    assert "[REDACTED]" in redact("turnstile_token=0." + "a" * 50)
    assert redact("plain text stays") == "plain text stays"


def test_filter_on_handler_redacts_args_and_extra() -> None:
    stream = io.StringIO()
    h = logging.StreamHandler(stream)
    h.setFormatter(logging.Formatter("%(message)s %(url)s"))
    install(h)
    install(h)
    assert sum(isinstance(f, RedactionFilter) for f in h.filters) == 1
    lg = logging.getLogger("ezmd.test.redact")
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    lg.info("key %s", KEY, extra={"url": "https://a:b@x.org/"})
    out = stream.getvalue()
    assert KEY not in out and "a:b@" not in out


def test_notify_once(tmp_path: Path) -> None:
    buf = io.StringIO()
    assert notify_once("pymupdf", stream=buf, stamp_dir=tmp_path)
    assert "AGPL-3.0" in buf.getvalue()
    assert not notify_once("pymupdf", stream=buf, stamp_dir=tmp_path)
    assert notify_once("unknown-extra", stream=io.StringIO(), stamp_dir=tmp_path)


def test_clean_text_counts() -> None:
    st = CleanStats()
    out = clean_text("a\x00b\u200bc\u202ed\ufeffe\U000e0041f\r\ng\x07", st)
    assert out == "abcdef\ng"
    assert st.control == 2 and st.invisible == 4 and st.total == 6
    assert clean_text("x\ud800y") == "x\ufffdy"


def test_filter_keeps_positional_args_for_formatters() -> None:
    rec = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s" %d', ("1.2.3.4", "GET", f"/x?k={KEY}", 200), None
    )
    RedactionFilter().filter(rec)
    assert isinstance(rec.args, tuple) and rec.args[3] == 200
    msg = rec.getMessage()
    assert KEY not in msg and "200" in msg
