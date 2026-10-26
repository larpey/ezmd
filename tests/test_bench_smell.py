"""The structural smell scorer: fires on the shapes everyday documents broke, stays quiet on clean output."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench.scoring import smell  # noqa: E402

CLEAN = """# A report

## 1 Introduction

This is a paragraph of ordinary prose with enough words to count as text. It continues for a while so the
scorer sees a normal document, with a list and a table below.

- first point
- second point, which is longer and wraps onto another line in the source

| col a | col b | col c |
|---|---|---|
| 1 | 2 | 3 |
| 4 | 5 | 6 |
| 7 | 8 | 9 |
| 10 | 11 | 12 |
"""


def test_clean_output_has_no_smell() -> None:
    assert smell.smells(CLEAN, "pdf", {"truncated": False, "warnings": []}, CLEAN.encode()) == []


def test_empty_and_control_characters() -> None:
    assert "empty" in smell.smells("", "pdf")
    assert "empty" in smell.smells("---\n\n   \n", "pdf")
    assert smell.smells(CLEAN + "\x0cmore\n", "pdf") == ["control_chars"]


def test_the_course_deck_shapes() -> None:
    lone = CLEAN + "\nSome question text?\n\n●\n\nNext question?\n"
    assert smell.smells(lone, "pdf") == ["lone_bullet"]
    code = CLEAN + "\n```\n/*\n *\n * comment\n */\n-\n```\n"
    assert smell.smells(code, "c") == []  # a lone `*` or `-` is ordinary in source code
    bullet_heading = CLEAN + "\n### 4.1 ● What information does the record need?\n"
    assert smell.smells(bullet_heading, "pdf") == ["heading_bullet"]
    long = "Describe the sequence of events when a running process is interrupted by a timer and the scheduler"
    tail = " picks another one to run next and what the hardware saves for it"
    repeated = CLEAN + f"\n### {long}{tail}...\n\n{long} picks another one.\n"
    assert smell.smells(repeated, "pdf") == ["heading_repeated"]


def test_truncation_counts_only_for_the_full_profile() -> None:
    side = {"truncated": True, "warnings": []}
    assert smell.smells(CLEAN, "pdf", side) == ["truncated_full"]
    assert smell.smells(CLEAN, "pdf", side, profile="compact") == []


def test_reported_smells() -> None:
    assert smell.smells(CLEAN + "\n" + "x � y � z �\n", "pdf") == ["replacement_chars"]
    assert smell.smells(CLEAN + "\nItâ€™s a cafÃ© problem\n", "pdf") == ["mojibake"]
    line = "Page footer that repeats on every page\n\n"
    assert smell.smells(CLEAN + "\n" + line * 10, "pdf") == ["repeated_lines"]
    assert smell.smells(CLEAN + "\n" + "二" * 300 + "\n", "pdf") == ["char_run"]
    table = "| a | b | c | d |\n|---|---|---|---|\n" + "|  |  | x |  |\n" * 5
    assert smell.smells(CLEAN + "\n" + table, "pdf") == ["empty_table"]
    side = {"truncated": False, "warnings": [{"kind": "prompt_injection_suspected"}]}
    assert smell.smells(CLEAN, "pdf", side) == ["injection"]
    assert smell.smells(CLEAN, "pdf", {"truncated": False, "warnings": [], "injection_risk": "high"}) == ["injection"]
    assert smell.smells(CLEAN, "pdf", {"truncated": False, "warnings": [], "injection_risk": "low"}) == []
    assert smell.smells(CLEAN, "pdf", {"warnings": [], "render_warnings": ["injection_suspected"]}) == ["injection"]


def test_shrunk_applies_to_text_like_inputs_only() -> None:
    src = ("word " * 2000).encode()
    short = "# Title\n\nJust a few words survived the conversion of this file.\n"
    assert smell.smells(short, "txt", None, src) == ["shrunk"]
    assert smell.smells(short, "govdocs-txt", None, src) == ["shrunk"]
    assert smell.smells(short, "pdf", None, src) == []
    html = ("<p>word</p>" * 2000).encode()
    assert smell.smells(short, "html", None, html) == ["shrunk"]
    assert smell.smells(short, "html", None, ("<p>word</p>" * 60).encode()) == []
