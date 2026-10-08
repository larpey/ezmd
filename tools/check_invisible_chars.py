"""Fail (or with --fix, rewrite) when source files contain literal invisible or bidi characters.

Such characters in source are a "Trojan Source" hazard; write them as escapes (backslash-u) instead.
"""

from __future__ import annotations

import pathlib
import re
import sys

RANGES = [
    (0x00AD, 0x00AD),
    (0x200B, 0x200F),
    (0x2060, 0x2064),
    (0x202A, 0x202E),
    (0x2066, 0x2069),
    (0xFEFF, 0xFEFF),
    (0xFFFD, 0xFFFD),
    (0xE0000, 0xE007F),
]
BAD = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in RANGES) + "]")
SKIP = {".venv", "node_modules", "dist", ".git", "fixtures"}
BACKSLASH = chr(92)


def _escape(ch: str) -> str:
    cp = ord(ch)
    return f"{BACKSLASH}U{cp:08x}" if cp > 0xFFFF else f"{BACKSLASH}u{cp:04x}"


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    found = 0
    for p in pathlib.Path(".").rglob("*"):
        if p.suffix not in {".py", ".ts", ".tsx", ".js", ".mjs"} or SKIP & set(p.parts):
            continue
        s = p.read_text(encoding="utf-8", errors="surrogatepass")
        hits = BAD.findall(s)
        if not hits:
            continue
        found += len(hits)
        print(f"{p}: {len(hits)} invisible character(s)")
        if fix:
            p.write_text(BAD.sub(lambda m: _escape(m.group()), s), encoding="utf-8", newline="\n")
    return 1 if found and not fix else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
