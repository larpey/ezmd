"""Token budgeting for repository packs (docs/spec/part2.md 8c step 6).

Applied in order until the pack fits: (a) drop lockfiles, generated and minified files; (b) drop test
directories; (c) switch files over 300 lines to signatures-only; (d) truncate every remaining file to its first
N lines (N >= 40, the largest N that fits); (e) drop files from the deepest directories. Each step that changed
anything is recorded; the tree is never touched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from intomd_converters.code.signatures import signatures

__all__ = ["PackFile", "apply_budget"]

COMPRESS_OVER_LINES = 300
MIN_TRUNCATE_LINES = 40


@dataclass(slots=True)
class PackFile:
    path: str
    text: str
    language: str | None
    lines: int
    tokens: int
    depth: int
    is_test: bool
    disposable: bool
    """Lockfile, generated, or minified (budget step a)."""
    size: int = 0
    """Source size in bytes, before decoding, redaction, truncation, or compression."""
    note: str | None = None
    compressed: bool = False
    dropped: str | None = None


def _disposable(f: PackFile) -> bool:
    return f.disposable


def _is_test(f: PackFile) -> bool:
    return f.is_test


def _total(files: list[PackFile], overhead: int) -> int:
    return overhead + sum(f.tokens for f in files if f.dropped is None)


def apply_budget(files: list[PackFile], budget: int, overhead: int, count: Callable[[str], int]) -> list[str]:
    """Mutates the PackFile states in place (they are private to one conversion). Returns the action log."""
    actions: list[str] = []
    live = [f for f in files if f.dropped is None]
    if _total(files, overhead) <= budget:
        return actions
    steps: list[tuple[str, Callable[[PackFile], bool]]] = [
        ("dropped {n} lockfile, generated, or minified file(s)", _disposable),
        ("dropped {n} test file(s)", _is_test),
    ]
    for label, pred in steps:
        hits = [f for f in live if f.dropped is None and pred(f)]
        for f in hits:
            f.dropped = "token budget"
        if hits:
            actions.append(label.format(n=len(hits)))
        if _total(files, overhead) <= budget:
            return actions
    big = [f for f in files if f.dropped is None and not f.compressed and f.lines > COMPRESS_OVER_LINES]
    for f in big:
        f.text = signatures(f.text, f.language)
        f.tokens = count(f.text)
        f.compressed = True
    if big:
        actions.append(f"compressed {len(big)} file(s) over {COMPRESS_OVER_LINES} lines to signatures")
    if _total(files, overhead) <= budget:
        return actions
    n = _truncate_lines(files, budget - overhead)
    cut = 0
    for f in files:
        lines = f.text.split("\n")
        if f.dropped is None and len(lines) > n:
            f.text = "\n".join(lines[:n])
            f.note = f"... (truncated, {len(lines) - n:,} more lines)"
            f.tokens = count(f.text) + count(f.note)
            cut += 1
    if cut:
        actions.append(f"truncated {cut} file(s) to their first {n} lines")
    if _total(files, overhead) <= budget:
        return actions
    deepest = sorted((f for f in files if f.dropped is None), key=lambda f: (-f.depth, f.path))
    dropped = 0
    running = _total(files, overhead)
    for f in deepest:
        if running <= budget:
            break
        f.dropped = "token budget"
        running -= f.tokens
        dropped += 1
    if dropped:
        actions.append(f"dropped {dropped} file(s) from the deepest directories")
    return actions


def _truncate_lines(files: list[PackFile], room: int) -> int:
    """Largest N >= MIN_TRUNCATE_LINES whose proportional token estimate fits in `room`."""
    live = [(f.tokens, max(1, f.text.count("\n") + 1)) for f in files if f.dropped is None]
    if not live:
        return MIN_TRUNCATE_LINES
    lo, hi = MIN_TRUNCATE_LINES, max(n for _t, n in live)

    def est(n: int) -> float:
        return sum(t * min(1.0, n / lines) for t, lines in live)

    if est(lo) > room:
        return lo
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if est(mid) <= room:
            lo = mid
        else:
            hi = mid - 1
    return lo
