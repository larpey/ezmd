"""Thread reconstruction for mailboxes (docs/spec/part2.md 9c step 5).

A simplified JWZ pass: each message's parent is the nearest `References` id (last first) or `In-Reply-To`
that is present in the mailbox; messages without a present parent are roots. Roots whose normalized subject
(`Re:`, `Fwd:`, `AW:`, `WG:`, `[list]` prefixes stripped) matches an earlier thread with a shared
participant within 30 days join that thread as replies to its root (the broken-chain fallback). Threads are
ordered by their first message's date; messages inside a thread are chronological, each with its reply depth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from intomd_converters.comms.model import ParsedMessage

SUBJECT_WINDOW = timedelta(days=30)
_PREFIX = re.compile(r"^\s*(?:(?:re|fwd?|aw|wg|sv|antw)\s*(?:\[\d+\])?\s*:\s*|\[[^\]]{1,40}\]\s*)+", re.IGNORECASE)
_ID = re.compile(r"<[^<>\s]+>")
_ADDR = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MIN = datetime.min.replace(tzinfo=UTC)


def normalize_subject(subject: str) -> str:
    return " ".join(_PREFIX.sub("", subject).split()).casefold()


def _ids(value: str) -> list[str]:
    return [m.group(0).lower() for m in _ID.finditer(value)]


def _participants(msg: ParsedMessage) -> set[str]:
    text = " ".join(msg.headers.get(h, "") for h in ("From", "To", "Cc"))
    return {a.lower() for a in _ADDR.findall(text)}


def _when(msg: ParsedMessage) -> datetime:
    d = msg.date
    if d is None:
        return _MIN
    return d if d.tzinfo is not None else d.replace(tzinfo=UTC)


@dataclass(slots=True)
class Thread:
    root: int
    subject: str
    members: list[tuple[int, int]] = field(default_factory=list)
    """(message index, reply depth) in chronological order."""


def build_threads(messages: list[ParsedMessage]) -> list[Thread]:
    by_id: dict[str, int] = {}
    for i, m in enumerate(messages):
        mid = _ids(m.message_id or "")
        if mid and mid[0] not in by_id:
            by_id[mid[0]] = i
    parent: dict[int, int | None] = {}
    for i, m in enumerate(messages):
        candidates = [*reversed(_ids(m.headers.get("References", ""))), *_ids(m.headers.get("In-Reply-To", ""))]
        found = next((by_id[c] for c in candidates if c in by_id and by_id[c] != i), None)
        parent[i] = found
    _break_cycles(parent)
    roots = sorted((i for i, p in parent.items() if p is None), key=lambda i: (_when(messages[i]), i))
    merged: list[int] = []
    for r in roots:
        key = normalize_subject(messages[r].subject)
        target = None
        if key:
            for t in merged:
                tm = messages[t]
                close = abs(_when(messages[r]) - _when(tm)) <= SUBJECT_WINDOW
                if normalize_subject(tm.subject) == key and close and _participants(tm) & _participants(messages[r]):
                    target = t
                    break
        if target is None:
            merged.append(r)
        else:
            parent[r] = target
    children: dict[int, list[int]] = {}
    for i, p in parent.items():
        if p is not None:
            children.setdefault(p, []).append(i)
    threads: list[Thread] = []
    for r in merged:
        thread = Thread(root=r, subject=messages[r].subject)
        stack = [(r, 0)]
        collected: list[tuple[int, int]] = []
        while stack:
            node, depth = stack.pop()
            collected.append((node, depth))
            stack.extend((c, depth + 1) for c in children.get(node, []))
        collected.sort(key=lambda nd: (_when(messages[nd[0]]), nd[0]))
        thread.members = collected
        threads.append(thread)
    threads.sort(key=lambda t: (_when(messages[t.members[0][0]]), t.members[0][0]))
    return threads


def _break_cycles(parent: dict[int, int | None]) -> None:
    """A message that reaches itself through parents becomes a root (forged or looping References)."""
    for start in list(parent):
        seen = {start}
        node = parent[start]
        while node is not None:
            if node in seen:
                parent[start] = None
                break
            seen.add(node)
            node = parent[node]
