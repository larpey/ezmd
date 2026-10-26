"""`escape_inline` stays linear on a huge span (a 4 MB single-paragraph text file timed out at 120 s)."""

from __future__ import annotations

import time

from ezmd.render import text as t


def test_a_multi_megabyte_span_escapes_in_bounded_time() -> None:
    row = " ".join(("-9999" if i % 7 == 0 else str(100 + i)) for i in range(800)) + " & more\n"
    grid = row * 600  # about 2.4 MB, one paragraph, with a character the pre-check flags
    assert len(grid) > t.PARSE_MAX_CHARS
    start = time.perf_counter()
    out = t.escape_inline(grid)
    assert time.perf_counter() - start < 5.0
    assert out == grid  # nothing in it forms markup


def test_short_spans_still_use_the_parser() -> None:
    assert t.escape_inline("plain words") == "plain words"
    assert t.escape_inline("a *bold* claim") == "a \\*bold\\* claim"
    assert t.escape_inline("snake_case_name stays") == "snake_case_name stays"
