"""Generate the structured text fixtures (self-authored text, CC0). Run: uv run python fixtures/text/_generate.py

Writes `plaintext-structured/input.txt` and `markdown-obsidian/input.md` only; the older text fixtures
(plain-utf8, plain-latin1, plain-utf8-bom, markdown-kitchen-sink) were written by hand and are not touched.
Goldens come from `uv run ezmd-golden fixtures/text/<name> --write`. Output is LF-only and deterministic.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
NL = chr(10)

PLAINTEXT_STRUCTURED = [
    "Harbour Maintenance Manual",
    "==========================",
    "",
    "This manual describes the routine upkeep of the small-boat harbour. It was",
    "written to be read on paper, so its paragraphs are hard-wrapped at about",
    "eighty columns and its sections are marked the way a typewriter would.",
    "",
    "Daily Checks",
    "------------",
    "",
    "Walk the pontoons every morning before the first boat leaves.",
    "",
    "1. Check the mooring lines for chafe.",
    "2. Test the shore power posts.",
    "   2.1 Reset any tripped breaker once.",
    "   2.2 Report a second trip to the harbour master.",
    "3. Clear litter from the slipway.",
    "",
    "SAFETY EQUIPMENT CHECKS",
    "",
    "Every pontoon carries a life ring, a throw line and a ladder. Replace a",
    "missing item the same day and note it in the log.",
    "",
    "Item         Location        Checked",
    "Life ring    Pontoon A head  daily",
    "Throw line   Pontoon B head  daily",
    "Ladder       Each finger     weekly",
    "",
    "WINTER LAY-UP:",
    "",
    "Before the first frost, drain the fresh water lines with the following",
    "commands on the pump house controller:",
    "",
    "    valve close main",
    "    pump drain --all",
    "    valve open bleed",
    "",
    "Leave the bleed valve open until spring.",
    "",
    "END NOTE",
    "",
    "Two capital words alone are not a heading.",
]

MARKDOWN_OBSIDIAN = [
    "---",
    "title: Tide Station Notes",
    "tags: [harbour, tides]",
    "aliases:",
    "  - tide notes",
    "created: 2024-05-02",
    "---",
    "",
    "# Tide Station Notes",
    "",
    "Readings are copied from [[Tide Log 2024]] and the [[Station Map|map of the stations]].",
    "",
    "![[station-photo.png]]",
    "",
    "> [!warning] Calibration due",
    "> The north gauge drifts by 2 cm a month. See [[Calibration#Procedure]].",
    "",
    "> [!note]- Folded note",
    "> Folded callouts start collapsed in Obsidian.",
    "",
    "## Tasks",
    "",
    "- [x] Replace the gauge battery",
    "- [ ] Re-level the staff board",
    "    - [ ] Borrow the dumpy level",
    "",
    "## Readings",
    "",
    "| Station | High (m) | Low (m) |",
    "|:--|--:|--:|",
    "| North | 4.2 | 0.6 |",
    "| South | 3.9 | 0.8 |",
    "",
    "The south gauge sits in a sheltered inlet.[^shelter]",
    "",
    "```python",
    "def range_m(high, low):",
    "    return round(high - low, 2)",
    "```",
    "",
    "<details>",
    "<summary>Raw export</summary>",
    "",
    "north,4.2,0.6",
    "",
    "</details>",
    "",
    "Tagged #tides and #harbour/maintenance.",
    "",
    "[^shelter]: The inlet halves the wave height compared with the open shore.",
]


def write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(NL.join(lines) + NL, encoding="utf-8", newline=NL)


if __name__ == "__main__":
    write(HERE / "plaintext-structured" / "input.txt", PLAINTEXT_STRUCTURED)
    write(HERE / "markdown-obsidian" / "input.md", MARKDOWN_OBSIDIAN)
