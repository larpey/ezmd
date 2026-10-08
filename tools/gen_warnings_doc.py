"""Generate docs/warnings.md from intomd.warnings.codes (a test asserts the committed file is current)."""

from __future__ import annotations

import sys
from pathlib import Path

from intomd.warnings.codes import CODES

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "warnings.md"
PIPE_ESCAPED = "\\|"


def render() -> str:
    lines = [
        "# Warning codes",
        "",
        "Every loss or degradation intomd knows about is reported as a structured warning with one of these codes.",
        "Generated from `packages/core/src/intomd/warnings/codes.py` by `tools/gen_warnings_doc.py`; do not edit.",
        "",
        "| Code | Severity | Family | Meaning | What you can do |",
        "|---|---|---|---|---|",
    ]
    for spec in CODES.values():
        desc = spec.description.replace("|", PIPE_ESCAPED)
        sug = spec.suggestion.replace("|", PIPE_ESCAPED)
        lines.append(f"| `{spec.code}` | {spec.severity} | {spec.family} | {desc} | {sug} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(CODES)} codes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
