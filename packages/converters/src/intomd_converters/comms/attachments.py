"""Attachment handling (docs/spec/part2.md 9b step 8 and 9c step 4).

Every attachment is listed in an attachments Table (name, type, size, status). Convertible attachments,
including forwarded `message/rfc822` parts, go through the registry with `options.ctx.convert_child`, which
shares the deadline and enforces `max_attachment_depth`; each converted attachment becomes a child Document
with `source = "<message source>!attachments/<name>"` and block provenance `path = "attachments/<n>"`.
Inline `cid:` images are written to `image_dir/images/` (when image extraction is on) and rendered in place.
Oversized, policy-skipped, depth-limited, unsupported, and failed attachments each yield a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from intomd.inputs import FetchRequired, InputRef, InputTooLarge
from intomd.ir import Document, InlineSpan, Metadata, Provenance, SourceType, Table, TableCell, Warning, WarningKind
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.comms.model import Attachment, ParsedMessage
from intomd_converters.comms.options import CommsOptions

UNSUPPORTED_MARKERS = ("no converter for", "no available converter", "not supported")


@dataclass(slots=True)
class Row:
    name: str
    mime: str
    size: int
    status: str


@dataclass(slots=True)
class AttachmentOutcome:
    rows: list[Row] = field(default_factory=list)
    children: list[Document] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    cid_refs: dict[str, str] = field(default_factory=dict)
    converted: int = 0


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _unique(name: str, seen: set[str]) -> str:
    if name not in seen:
        seen.add(name)
        return name
    stem, dot, ext = name.rpartition(".")
    base, suffix = (stem, f".{ext}") if dot and stem else (name, "")
    n = 2
    while f"{base} ({n}){suffix}" in seen:
        n += 1
    out = f"{base} ({n}){suffix}"
    seen.add(out)
    return out


def inline_images(msg: ParsedMessage, options: ConvertOptions) -> dict[str, str]:
    """cid -> asset path for inline images, writing the bytes when image extraction is configured."""
    refs: dict[str, str] = {}
    target_dir = Path(options.image_dir) / "images" if options.image_dir and options.extract_images else None
    seen: set[str] = set()
    for att in msg.attachments:
        if not att.inline_image or not att.content_id:
            continue
        name = _unique(att.name, seen)
        refs[att.content_id.lower()] = f"images/{name}"
        if target_dir is not None and att.data:
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / name).write_bytes(att.data)
    return refs


def _warn(kind: WarningKind, message: str, name: str, reason: str) -> Warning:
    return Warning(kind=kind, message=message, detail={"name": name, "reason": reason})


class AttachmentRunner:
    """Converts one message's attachments; `source` is the message's source label."""

    def __init__(self, source: str, options: ConvertOptions, opts: CommsOptions) -> None:
        self.source = source
        self.options = options
        self.opts = opts

    def run(self, msg: ParsedMessage, cid_refs: dict[str, str]) -> AttachmentOutcome:
        out = AttachmentOutcome(cid_refs=cid_refs)
        seen: set[str] = set()
        converted_slots = 0
        for att in msg.attachments:
            self.options.ctx.check_deadline()
            if att.inline_image:
                out.rows.append(Row(att.name, att.mime, att.size, "inline image"))
                continue
            name = _unique(att.name, seen)
            status = self._precheck(att, name, out, converted_slots)
            if status is not None:
                out.rows.append(Row(name, att.mime, att.size, status))
                continue
            converted_slots += 1
            index = len(out.rows) + 1
            if att.data is None and att.kind == "message":
                status = self._embedded(att, name, index, out)
            else:
                status = self._convert(att, name, index, out)
            out.rows.append(Row(name, att.mime, att.size, status))
        return out

    def _precheck(self, att: Attachment, name: str, out: AttachmentOutcome, slots: int) -> str | None:
        if att.kind == "signature":
            return "signature (not converted)"
        if att.kind == "tnef":
            out.warnings.append(
                _warn(
                    WarningKind.TNEF_UNPARSED,
                    f"{name} is an Outlook TNEF (winmail.dat) container, which is not decoded.",
                    name,
                    "tnef",
                )
            )
            return "not converted (TNEF)"
        if att.kind == "smime":
            out.warnings.append(
                _warn(
                    WarningKind.SMIME_NOT_DECRYPTED, f"{name} is S/MIME encrypted and was not decrypted.", name, "smime"
                )
            )
            return "not decrypted (S/MIME)"
        if self.opts.attachments == "skip" or self.opts.attachments == "list":
            out.warnings.append(
                _warn(
                    WarningKind.ATTACHMENT_SKIPPED,
                    f"{name} was listed but not converted (attachments={self.opts.attachments}).",
                    name,
                    "policy",
                )
            )
            return "listed (not converted)"
        if att.size > self.opts.max_attachment_bytes:
            out.warnings.append(
                _warn(
                    WarningKind.ATTACHMENT_SKIPPED,
                    f"{name} ({human_size(att.size)}) exceeds the {human_size(self.opts.max_attachment_bytes)} "
                    "attachment limit and was not converted.",
                    name,
                    "too_large",
                )
            )
            return "skipped (too large)"
        if slots >= self.opts.max_attachments:
            out.warnings.append(
                _warn(
                    WarningKind.ATTACHMENT_SKIPPED,
                    f"{name} was not converted: the message has more than {self.opts.max_attachments} attachments.",
                    name,
                    "attachment_cap",
                )
            )
            return "skipped (attachment cap)"
        if att.data is None and att.kind == "message":
            if att.message is None:
                out.warnings.append(
                    _warn(
                        WarningKind.ATTACHMENT_SKIPPED,
                        f"{name} was not converted: embedded messages nest deeper than "
                        f"{self.opts.max_attachment_depth} levels.",
                        name,
                        "depth",
                    )
                )
                return "skipped (depth limit)"
            return None
        if not att.data:
            out.warnings.append(
                _warn(WarningKind.ATTACHMENT_FAILED, f"{name} is empty or could not be decoded.", name, "empty")
            )
            return "failed (empty)"
        return None

    def _embedded(self, att: Attachment, name: str, index: int, out: AttachmentOutcome) -> str:
        """An embedded Outlook message, already parsed: rendered in-process as a child Document."""
        from intomd_converters.comms.build import MessageSpec, build_message

        assert att.message is not None
        label = f"{self.source}!attachments/{name}"
        built = build_message(att.message, MessageSpec(source=label), self.options, self.opts)
        meta = Metadata(title=att.message.subject or name, source=label, source_type=SourceType.EMAIL, mime=att.mime)
        path = f"attachments/{index}"
        blocks = [
            b.model_copy(update={"provenance": b.provenance.model_copy(update={"path": path})}) for b in built.blocks
        ]
        child = Document(metadata=meta, blocks=blocks, warnings=built.warnings, children=built.children)
        child.converter_id = "comms.msg"
        out.children.append(child.finalize())
        out.converted += 1
        return "converted (comms.msg)"

    def _convert(self, att: Attachment, name: str, index: int, out: AttachmentOutcome) -> str:
        label = f"{self.source}!attachments/{name}"
        assert att.data is not None
        try:
            ref = InputRef.from_bytes(att.data, filename=name, declared_mime=att.mime, max_bytes=max(len(att.data), 1))
        except InputTooLarge:
            return "skipped (too large)"
        try:
            result = self.options.ctx.convert_child(ref, label=label)
        except (ConversionError, FetchRequired) as e:
            text = f"{e} {getattr(e, 'user_message', '')}".lower()
            if any(m in text for m in UNSUPPORTED_MARKERS):
                out.warnings.append(
                    _warn(
                        WarningKind.ATTACHMENT_UNCONVERTED,
                        f"{name} ({att.mime}) has no available converter and is listed by name only.",
                        name,
                        "unsupported",
                    )
                )
                return "not converted (unsupported type)"
            out.warnings.append(
                _warn(
                    WarningKind.ATTACHMENT_FAILED,
                    f"{name} failed to convert and is listed by name only.",
                    name,
                    "failed",
                )
            )
            return "failed"
        finally:
            ref.cleanup()
        child = result.document
        if not child.blocks:
            skipped = [w for w in child.warnings if w.kind == WarningKind.ATTACHMENT_SKIPPED]
            if skipped:
                out.warnings.extend(
                    w.model_copy(update={"detail": {**w.detail, "name": name, "reason": "depth"}}) for w in skipped
                )
                return "skipped (depth limit)"
            out.warnings.append(
                _warn(WarningKind.ATTACHMENT_UNCONVERTED, f"{name} produced no content.", name, "empty_result")
            )
            return "not converted (no content)"
        child.warnings = [*result.warnings, *child.warnings]
        child.converter_id = result.converter_id
        path = f"attachments/{index}"
        for b in child.blocks:
            inner = b.provenance.path
            b.provenance = b.provenance.model_copy(
                update={"source": label, "path": path if inner is None else f"{path}!{inner}"}
            )
        child.metadata.source = label
        child.finalize()
        out.children.append(child)
        out.converted += 1
        return f"converted ({result.converter_id})" if result.converter_id else "converted"


def attachments_table(rows: list[Row], prov: Provenance) -> Table:
    header = ("Name", "Type", "Size", "Status")
    cells = [TableCell(spans=[InlineSpan(text=h)], row=0, col=c, is_header=True) for c, h in enumerate(header)]
    for r, row in enumerate(rows, start=1):
        size = human_size(row.size) if row.size or row.mime != "application/vnd.ms-outlook" else "unknown"
        values = (row.name, row.mime, size, row.status)
        cells.extend(TableCell(spans=[InlineSpan(text=v)], row=r, col=c) for c, v in enumerate(values))
    return Table(
        cells=cells, n_rows=len(rows) + 1, n_cols=4, header_rows=1, provenance=prov, attrs={"role": "attachments"}
    )
