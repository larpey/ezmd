"""Print the CHANGELOG.md section for one release (used by .github/workflows/release.yml for the notes).

    python tools/changelog_section.py 0.1.0-rc2 CHANGELOG.md > notes.md

The section is the text under the heading `## [<version>]` (optionally followed by ` - <date>`), matched
exactly: `0.1.0` never matches `## [0.1.0-rc2]`. Without that heading, the `## [Unreleased]` section is
used if it has content. Otherwise the script exits 1 with a message instead of publishing another
release's notes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

UNRELEASED = "Unreleased"


def _heading(name: str) -> re.Pattern[str]:
    return re.compile(r"^## \[" + re.escape(name) + r"\](?:\s+-\s+.*)?\s*$")


def _body(lines: list[str], name: str) -> str | None:
    pattern = _heading(name)
    for i, line in enumerate(lines):
        if pattern.match(line):
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            body = "\n".join(lines[i + 1 : end]).strip()
            return body + "\n" if body else None
    return None


def section(text: str, version: str) -> str:
    """The notes for `version`, or the Unreleased notes; LookupError when neither has content."""
    lines = text.splitlines()
    for name in (version, UNRELEASED):
        body = _body(lines, name)
        if body is not None:
            return body
    raise LookupError(f"CHANGELOG has no non-empty '## [{version}]' or '## [{UNRELEASED}]' section")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: changelog_section.py <version> <CHANGELOG.md>\n")
        return 2
    version, path = argv
    try:
        notes = section(Path(path).read_text(encoding="utf-8"), version)
    except (OSError, LookupError) as e:
        sys.stderr.write(f"changelog_section: {e}\n")
        return 1
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
