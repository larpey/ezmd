"""comms.mbox: a Unix mailbox to one combined Document (docs/spec/part2.md 9c steps 5 and 8).

`mailbox.mbox` splits the file on `From ` lines (lazily, after building its table of contents). A split
whose first line is not a header is an unescaped `From ` inside a body and is merged back into the previous
message (9e step 11). mboxrd `>From ` escapes are undone. At most `comms.max_messages` (default 5,000) and
`Limits.max_bytes` are read; beyond that the Document is truncated with a `truncated` warning. Messages are
grouped into threads (`comms.threads`): an H1 per thread and an H2 per message (`From · Date`), with each
message's attachments converted as child Documents under `<mbox>!messages/<n>/attachments/<name>`.
"""

from __future__ import annotations

import mailbox
import re
from dataclasses import dataclass, field

from ezmd.context import Limits
from ezmd.inputs import InputRef
from ezmd.ir import (
    Block,
    Document,
    Heading,
    InlineSpan,
    Metadata,
    Provenance,
    SidecarScalar,
    SourceType,
    Warning,
    WarningKind,
)
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.comms.build import MessageSpec, build_message
from ezmd_converters.comms.eml import SIDECAR_KEY, is_mbox, looks_like_message
from ezmd_converters.comms.model import ParsedMessage
from ezmd_converters.comms.options import CommsOptions, read_options
from ezmd_converters.comms.parse_eml import EmailParseError, parse_message_bytes
from ezmd_converters.comms.threads import build_threads

MBOX_MIMES = ("application/mbox", "application/x-mbox", "message/rfc822", "text/plain", "application/octet-stream")
MBOX_EXTS = (".mbox", ".mbx")
DEFAULT_MAX_BYTES = 5 * 1024 * 1024 * 1024
_ESCAPED_FROM = re.compile(rb"(?m)^>(>*From )")
PARTIAL_EVERY = 50


@dataclass(slots=True)
class _Read:
    raws: list[bytes] = field(default_factory=list)
    capped: bool = False
    bytes_capped: bool = False
    merged: int = 0


def _read_mailbox(path: str, opts: CommsOptions, max_bytes: int, options: ConvertOptions) -> _Read:
    out = _Read()
    box = mailbox.mbox(path, create=False)
    total = 0
    try:
        for key in box.iterkeys():
            options.ctx.check_deadline()
            raw = box.get_bytes(key)
            if out.raws and not looks_like_message(raw[:4096]):
                out.raws[-1] = out.raws[-1] + b"\n" + box.get_bytes(key, from_=True)
                out.merged += 1
                continue
            if len(out.raws) >= opts.max_messages:
                out.capped = True
                break
            total += len(raw)
            if total > max_bytes:
                out.bytes_capped = True
                break
            out.raws.append(raw)
    finally:
        box.close()
    return out


def _sender_date(msg: ParsedMessage) -> str:
    sender = msg.sender or "(unknown sender)"
    return f"{sender} · {msg.headers['Date']}" if msg.headers.get("Date") else sender


class MboxConverter:
    id = "comms.mbox"
    family = "comms"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("application/mbox", "application/x-mbox")
    limits = Limits(max_bytes=DEFAULT_MAX_BYTES, max_entries=5000, max_depth=3, timeout_s=300.0)

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if not ref.has_body or mime not in MBOX_MIMES:
            return 0.0
        head = ref.head(4096)
        if is_mbox(head):
            return 1.0
        if ref.display.lower().endswith(MBOX_EXTS) and head.startswith(b"From "):
            return 0.9
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = read_options(options)
        limit = options.ctx.limits.max_entries
        if limit:
            opts = _with_max(opts, limit)
        max_bytes = options.ctx.limits.max_bytes or DEFAULT_MAX_BYTES
        source = ref.display
        options.ctx.progress("index", 0.05, "indexing mailbox")
        read = _read_mailbox(str(ref.path()), opts, max_bytes, options)
        doc = Document(
            metadata=Metadata(title=source, source=source, source_type=SourceType.EMAIL, mime="application/mbox")
        )
        messages: list[ParsedMessage] = []
        positions: list[int] = []
        for n, raw in enumerate(read.raws, start=1):
            options.ctx.check_deadline()
            try:
                messages.append(parse_message_bytes(_ESCAPED_FROM.sub(rb"\1", raw), opts))
                positions.append(n)
            except EmailParseError as e:
                doc.warnings.append(
                    Warning(
                        kind=WarningKind.OTHER,
                        message=f"Message {n} could not be parsed and was skipped.",
                        detail={"message": n, "reason": str(e)[:200]},
                    )
                )
        if not messages:
            raise ConversionError(f"{source} contains no readable messages", user_message="The mailbox is empty.")
        self._render(doc, messages, positions, source, options, opts)
        self._limits_warnings(doc, read, opts, max_bytes)
        doc.metadata.extra.update({"messages": len(messages), "merged_splits": read.merged})
        options.ctx.progress("done", 1.0, "converted")
        return doc.finalize()

    def _render(self, doc: Document, messages: list[ParsedMessage], positions: list[int], source: str,
                options: ConvertOptions, opts: CommsOptions) -> None:  # fmt: skip
        threads = build_threads(messages)
        doc.metadata.extra["threads"] = len(threads)
        sidecar: list[dict[str, SidecarScalar]] = []
        done = 0
        for thread in threads:
            subject = messages[thread.root].subject or "(no subject)"
            root = messages[thread.root]
            doc.blocks.append(
                Heading(
                    level=1,
                    spans=[InlineSpan(text=subject)],
                    provenance=Provenance(
                        source=source, path=f"messages/{positions[thread.root]}", source_id=root.message_id
                    ),
                    attrs={"thread_messages": str(len(thread.members))},
                )
            )
            for index, depth in thread.members:
                options.ctx.check_deadline()
                msg = messages[index]
                spec = MessageSpec(source=source, level=2, title=_sender_date(msg), index=positions[index], depth=depth)
                built = build_message(msg, spec, options, opts)
                doc.blocks.extend(built.blocks)
                doc.children.extend(built.children)
                doc.warnings.extend(built.warnings)
                doc.truncated = doc.truncated or msg.truncated
                sidecar.extend(built.headers_sidecar)
                done += 1
                options.ctx.progress("messages", done / len(messages), f"message {done} of {len(messages)}")
                if done % PARTIAL_EVERY == 0:
                    options.ctx.publish_partial(_snapshot(doc))
        if sidecar:
            doc.sidecar_extra[SIDECAR_KEY] = sidecar

    @staticmethod
    def _limits_warnings(doc: Document, read: _Read, opts: CommsOptions, max_bytes: int) -> None:
        if read.capped:
            doc.truncated = True
            doc.warnings.append(
                Warning(
                    kind=WarningKind.TRUNCATED,
                    message=f"The mailbox has more than {opts.max_messages} messages; only the first were converted.",
                    count=opts.max_messages,
                    detail={"reason": "max_messages", "max_messages": opts.max_messages},
                )
            )
        if read.bytes_capped:
            doc.truncated = True
            doc.warnings.append(
                Warning(
                    kind=WarningKind.SIZE_CAP,
                    message=f"The mailbox exceeds {max_bytes} bytes; later messages were not read.",
                    detail={"reason": "max_bytes", "max_bytes": max_bytes},
                )
            )


def _with_max(opts: CommsOptions, limit: int) -> CommsOptions:
    from dataclasses import replace

    return replace(opts, max_messages=min(opts.max_messages, limit))


def _snapshot(doc: Document) -> Document:
    blocks: list[Block] = [b.model_copy() for b in doc.blocks]
    return Document(metadata=doc.metadata.model_copy(), blocks=blocks, warnings=list(doc.warnings), truncated=True)
