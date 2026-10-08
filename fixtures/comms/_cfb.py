"""A minimal Compound File Binary (MS-CFB v3) writer and Outlook .msg builder for self-generated fixtures.

olefile reads but does not create compound files, so the MSG fixture and the MSG unit tests build theirs here.
The writer emits 512-byte sectors, a mini stream for streams under 4096 bytes, a FAT without DIFAT sectors
(enough for files up to ~7 MB), and a balanced binary sibling tree per storage. The .msg builder lays out the
property streams the spec names (docs/spec/part2.md 9b step 2): `__substg1.0_<tag>` streams,
`__properties_version1.0`, recipient and attachment storages, and embedded messages (`3701000D`).
Deterministic: no timestamps in directory entries.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

SECTOR = 512
MINI = 64
CUTOFF = 4096
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF
MAGIC = bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])

Tree = dict[str, "bytes | Tree"]


@dataclass
class _Entry:
    name: str
    kind: int  # 1 storage, 2 stream, 5 root
    data: bytes = b""
    children: list[int] = field(default_factory=list)
    left: int = NOSTREAM
    right: int = NOSTREAM
    child: int = NOSTREAM
    start: int = ENDOFCHAIN
    size: int = 0


def _key(name: str) -> tuple[int, str]:
    return (len(name), name.upper())


def _flatten(tree: Tree) -> list[_Entry]:
    entries = [_Entry("Root Entry", 5)]
    queue: list[tuple[int, Tree]] = [(0, tree)]
    while queue:
        parent, node = queue.pop(0)
        for name in sorted(node, key=_key):
            value = node[name]
            idx = len(entries)
            if isinstance(value, dict):
                entries.append(_Entry(name, 1))
                queue.append((idx, value))
            else:
                entries.append(_Entry(name, 2, data=value, size=len(value)))
            entries[parent].children.append(idx)
    for e in entries:
        e.child = _balance(entries, e.children)
    return entries


def _balance(entries: list[_Entry], ids: list[int]) -> int:
    if not ids:
        return NOSTREAM
    mid = len(ids) // 2
    root = ids[mid]
    entries[root].left = _balance(entries, ids[:mid])
    entries[root].right = _balance(entries, ids[mid + 1 :])
    return root


def _chain(fat: list[int], start: int, count: int) -> None:
    for i in range(count):
        fat[start + i] = start + i + 1 if i < count - 1 else ENDOFCHAIN


def write_cfb(tree: Tree) -> bytes:
    entries = _flatten(tree)
    mini = bytearray()
    minifat: list[int] = []
    big: list[_Entry] = []
    for e in entries:
        if e.kind != 2 or e.size == 0:
            continue
        if e.size < CUTOFF:
            n = -(-e.size // MINI)
            e.start = len(minifat)
            minifat.extend(range(e.start + 1, e.start + n))
            minifat.append(ENDOFCHAIN)
            mini.extend(e.data.ljust(n * MINI, b"\x00"))
        else:
            big.append(e)
    sectors: list[bytes] = []
    plan: list[tuple[int, int]] = []

    def alloc(data: bytes) -> int:
        start = len(sectors)
        n = max(1, -(-len(data) // SECTOR))
        padded = data.ljust(n * SECTOR, b"\x00")
        sectors.extend(padded[i * SECTOR : (i + 1) * SECTOR] for i in range(n))
        plan.append((start, n))
        return start

    for e in big:
        e.start = alloc(e.data)
    root = entries[0]
    if mini:
        root.start = alloc(bytes(mini))
        root.size = len(mini)
    minifat_start = ENDOFCHAIN
    minifat_count = 0
    if minifat:
        raw = b"".join(struct.pack("<I", x) for x in minifat)
        minifat_count = -(-len(raw) // SECTOR)
        minifat_start = alloc(raw.ljust(minifat_count * SECTOR, b"\xff"))
    dir_raw = b"".join(_dirent(e) for e in entries)
    dir_raw = dir_raw.ljust(-(-len(dir_raw) // SECTOR) * SECTOR, b"\x00")
    dir_start = alloc(dir_raw)
    n_fat = 1
    while (len(sectors) + n_fat) > n_fat * (SECTOR // 4):
        n_fat += 1
    if n_fat > 109:
        raise ValueError("file too large for a DIFAT-less compound file")
    fat_start = len(sectors)
    total = fat_start + n_fat
    fat = [FREESECT] * (n_fat * (SECTOR // 4))
    for start, n in plan:
        _chain(fat, start, n)
    for i in range(n_fat):
        fat[fat_start + i] = FATSECT
    fat_raw = b"".join(struct.pack("<I", x) for x in fat)
    sectors.extend(fat_raw[i * SECTOR : (i + 1) * SECTOR] for i in range(n_fat))
    assert len(sectors) == total
    difat = [fat_start + i for i in range(n_fat)] + [FREESECT] * (109 - n_fat)
    header = (
        MAGIC
        + bytes(16)
        + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6)
        + bytes(6)
        + struct.pack("<IIIIIIIII", 0, n_fat, dir_start, 0, CUTOFF, minifat_start, minifat_count, ENDOFCHAIN, 0)
        + b"".join(struct.pack("<I", x) for x in difat)
    )
    assert len(header) == SECTOR
    return header + b"".join(sectors)


def _dirent(e: _Entry) -> bytes:
    name = e.name.encode("utf-16-le")
    if len(name) > 62:
        raise ValueError(f"CFB name too long: {e.name}")
    return (
        name.ljust(64, b"\x00")
        + struct.pack("<HBB", len(name) + 2, e.kind, 1)
        + struct.pack("<III", e.left, e.right, e.child)
        + bytes(16)
        + bytes(4)
        + bytes(16)
        + struct.pack("<IQ", e.start if e.kind != 1 else 0, e.size if e.kind != 1 else 0)
    )


# ---------------------------------------------------------------------------
# Outlook .msg layout
# ---------------------------------------------------------------------------

PT_UNICODE = 0x001F
PT_BINARY = 0x0102
PT_LONG = 0x0003
PT_SYSTIME = 0x0040


def filetime(unix_seconds: int) -> int:
    return (unix_seconds + 11644473600) * 10_000_000


def _props_stream(fixed: dict[int, tuple[int, int]], header_len: int) -> bytes:
    out = bytearray(header_len)
    for prop_id, (ptype, value) in sorted(fixed.items()):
        tag = (prop_id << 16) | ptype
        out += struct.pack("<IIQ", tag, 0x6, value)
    return bytes(out)


@dataclass
class MsgAttachment:
    name: str
    data: bytes | None = None
    mime: str | None = None
    content_id: str | None = None
    embedded: MsgSpec | None = None


@dataclass
class MsgSpec:
    strings: dict[int, str] = field(default_factory=dict)
    """Property id -> Unicode string (written as PT_UNICODE `001F` streams)."""
    ansi: dict[int, bytes] = field(default_factory=dict)
    """Property id -> 8-bit string bytes (PT_STRING8 `001E` streams)."""
    binary: dict[int, bytes] = field(default_factory=dict)
    times: dict[int, int] = field(default_factory=dict)
    """Property id -> Unix seconds (PT_SYSTIME in the properties stream)."""
    recipients: list[tuple[str, str, int]] = field(default_factory=list)
    """(display name, SMTP address, type 1 To / 2 Cc / 3 Bcc)."""
    attachments: list[MsgAttachment] = field(default_factory=list)


def msg_tree(spec: MsgSpec, *, top: bool = True) -> Tree:
    tree: Tree = {}
    for pid, text in spec.strings.items():
        tree[f"__substg1.0_{pid:04X}{PT_UNICODE:04X}"] = text.encode("utf-16-le")
    for pid, raw in spec.ansi.items():
        tree[f"__substg1.0_{pid:04X}001E"] = raw
    for pid, raw in spec.binary.items():
        tree[f"__substg1.0_{pid:04X}{PT_BINARY:04X}"] = raw
    fixed = {pid: (PT_SYSTIME, filetime(t)) for pid, t in spec.times.items()}
    header = bytes(8) + struct.pack(
        "<IIII", len(spec.recipients), len(spec.attachments), len(spec.recipients), len(spec.attachments)
    )
    header_len = 32 if top else 24
    stream = bytearray(_props_stream(fixed, header_len))
    stream[: min(header_len, len(header))] = header[:header_len]
    tree["__properties_version1.0"] = bytes(stream)
    for i, (name, addr, rtype) in enumerate(spec.recipients):
        tree[f"__recip_version1.0_#{i:08X}"] = {
            "__substg1.0_3001001F": name.encode("utf-16-le"),
            "__substg1.0_39FE001F": addr.encode("utf-16-le"),
            "__properties_version1.0": _props_stream({0x0C15: (PT_LONG, rtype)}, 8),
        }
    for i, att in enumerate(spec.attachments):
        node: Tree = {"__substg1.0_3707001F": att.name.encode("utf-16-le")}
        method = 1
        if att.data is not None:
            node["__substg1.0_37010102"] = att.data
        if att.mime:
            node["__substg1.0_370E001F"] = att.mime.encode("utf-16-le")
        if att.content_id:
            node["__substg1.0_3712001F"] = att.content_id.encode("utf-16-le")
        if att.embedded is not None:
            node["__substg1.0_3701000D"] = msg_tree(att.embedded, top=False)
            method = 5
        node["__properties_version1.0"] = _props_stream({0x3705: (PT_LONG, method)}, 8)
        tree[f"__attach_version1.0_#{i:08X}"] = node
    if top:
        tree["__nameid_version1.0"] = {
            "__substg1.0_00020102": b"",
            "__substg1.0_00030102": b"",
            "__substg1.0_00040102": b"",
        }
    return tree


def write_msg(spec: MsgSpec) -> bytes:
    return write_cfb(msg_tree(spec))


# ---------------------------------------------------------------------------
# Compressed RTF (MS-OXRTFCP) writer: greedy LZFu over the preloaded dictionary
# ---------------------------------------------------------------------------


def compress_rtf(raw: bytes, prebuf: bytes) -> bytes:
    dictionary = bytearray(4096)
    dictionary[: len(prebuf)] = prebuf
    wp = len(prebuf)
    filled = len(prebuf)
    out = bytearray()
    i = 0
    done = False
    while not done:
        control = 0
        chunk = bytearray()
        for bit in range(8):
            if i >= len(raw):
                ref = (wp << 4) & 0xFFF0
                chunk += struct.pack(">H", ref)
                control |= 1 << bit
                done = True
                break
            best_len, best_off = 0, 0
            for off in range(min(filled, 4096)):
                if off == wp:
                    continue
                n = 0
                room = (wp - off) % 4096  # never read a slot the decoder rewrites during this match
                while n < 17 and n < room and i + n < len(raw) and dictionary[(off + n) % 4096] == raw[i + n]:
                    n += 1
                if n > best_len:
                    best_len, best_off = n, off
            if best_len >= 2:
                chunk += struct.pack(">H", (best_off << 4) | (best_len - 2))
                control |= 1 << bit
                for k in range(best_len):
                    dictionary[wp] = raw[i + k]
                    wp = (wp + 1) % 4096
                    filled = min(4096, filled + 1)
                i += best_len
            else:
                chunk.append(raw[i])
                dictionary[wp] = raw[i]
                wp = (wp + 1) % 4096
                filled = min(4096, filled + 1)
                i += 1
        out.append(control)
        out += chunk
    crc = (~zlib.crc32(bytes(out), 0xFFFFFFFF)) & 0xFFFFFFFF
    return struct.pack("<IIII", len(out) + 12, len(raw), 0x75465A4C, crc) + bytes(out)
