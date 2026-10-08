"""Hostile inputs (docs/spec/part1.md 8.2): huge headers, deep MIME nesting, part floods, deadlines."""

from __future__ import annotations

import time

import pytest

from ezmd.inputs import InputRef
from ezmd.ir import WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.comms.eml import EmlConverter
from ezmd_converters.comms.options import CommsOptions
from ezmd_converters.comms.parse_eml import parse_message_bytes

HEAD = b"From: a@x.org\r\nTo: b@x.org\r\nSubject: Hostile\r\nDate: Wed, 02 Oct 2024 12:00:00 +0000\r\n"


def test_huge_header_is_cut_and_reported(convert) -> None:
    to = ", ".join(f"user{i}@example.org" for i in range(20000)).encode()
    raw = HEAD.replace(b"To: b@x.org", b"To: " + to) + b"\r\nBody.\r\n"
    t0 = time.monotonic()
    result = convert(raw)
    assert time.monotonic() - t0 < 10
    w = next(w for w in result.document.warnings if w.kind == WarningKind.TRUNCATED)
    assert w.detail["reason"] == "header_too_long"
    assert result.truncated


def _nested_multipart(depth: int) -> bytes:
    parts = []
    for i in range(depth):
        parts.append(f'Content-Type: multipart/mixed; boundary="b{i}"\r\n\r\n--b{i}\r\n'.encode())
    tail = b"Content-Type: text/plain\r\n\r\ninnermost\r\n"
    closing = b"".join(f"\r\n--b{i}--\r\n".encode() for i in reversed(range(depth)))
    return HEAD + b"MIME-Version: 1.0\r\n" + b"".join(parts) + tail + closing


def test_deep_mime_nesting_is_bounded() -> None:
    pm = parse_message_bytes(_nested_multipart(60), CommsOptions())
    assert pm.truncated
    assert any(w.detail.get("reason") == "mime_depth" for w in pm.warnings)


def test_very_deep_nesting_does_not_crash(convert) -> None:
    try:
        result = convert(_nested_multipart(3000))
    except ConversionError:
        return  # a clean refusal is acceptable
    assert result.document.blocks


def test_part_flood_is_capped() -> None:
    body = b"".join(
        b"--z\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename=a.txt\r\n\r\nx\r\n"
        for _ in range(50)
    )
    raw = HEAD + b'MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="z"\r\n\r\n' + body + b"--z--\r\n"
    pm = parse_message_bytes(raw, CommsOptions(max_parts=10))
    assert len(pm.attachments) < 10 and pm.truncated


def test_attachment_bomb_depth_stops_at_limit(convert, mk) -> None:
    inner = mk("L8", "bottom\n", mid="<l8@x>")
    for level in range(7, 0, -1):
        outer = mk(f"L{level}", f"level {level}\n", mid=f"<l{level}@x>")
        outer.add_attachment(inner)
        inner = outer
    doc = convert(inner.as_bytes()).document
    depth = 0
    node = doc
    while node.children:
        node = node.children[0]
        depth += 1
    assert depth == 3  # options.max_attachment_depth default
    assert any(w.kind == WarningKind.ATTACHMENT_SKIPPED for w in node.warnings)


def test_deadline_is_enforced(mk) -> None:
    m = mk("Slow", "x\n")
    for i in range(3):
        m.add_attachment(f"file {i}\n".encode(), maintype="text", subtype="plain", filename=f"{i}.txt")
    ref = InputRef.from_bytes(m.as_bytes(), filename="m.eml")
    opts = ConvertOptions(max_seconds=0.0)
    with pytest.raises(ConversionError) as e:
        EmlConverter().convert(ref, opts)
    assert e.value.code == "timeout"


def test_oversized_input_is_refused(mk) -> None:
    from ezmd.context import Limits

    ref = InputRef.from_bytes(mk("Big", "x" * 5000 + "\n").as_bytes(), filename="m.eml")
    opts = ConvertOptions()
    opts.ctx.limits = Limits(max_bytes=1000)
    with pytest.raises(ConversionError):
        EmlConverter().convert(ref, opts)


def test_garbage_is_not_claimed() -> None:
    ref = InputRef.from_bytes(b"\x00\x01binary junk", filename="x.bin")
    from ezmd.detect import detect

    ref.detected = detect(ref)
    assert EmlConverter().can_handle(ref) == 0.0
