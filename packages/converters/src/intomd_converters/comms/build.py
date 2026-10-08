"""ParsedMessage to IR (docs/spec/part2.md 9c steps 1 to 4 and 6), shared by EML, MBOX, and MSG.

One message renders as: a heading (the subject, or `From · Date` inside a mailbox), the headers Table,
the body blocks (headings shifted below the message heading), an `Attachments` heading and Table when the
message has attachments, and, with `comms.all_headers`, an `All headers` Table. Converted attachments are
returned as child Documents. Provenance: `source_id` = Message-ID, `path` = `headers` / `body` /
`attachments`, and the message heading carries `attrs["timestamp"]` (ISO 8601) because Provenance has no
timestamp field yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from intomd.ir import (
    Block,
    Document,
    Heading,
    InlineSpan,
    Paragraph,
    Provenance,
    Quote,
    SidecarScalar,
    Table,
    TableCell,
    Warning,
    WarningKind,
    spans_text,
)
from intomd.registry import ConvertOptions
from intomd_converters.comms.attachments import AttachmentRunner, attachments_table, inline_images
from intomd_converters.comms.body_html import html_blocks
from intomd_converters.comms.body_text import REPLY_HEADER, REPLY_HISTORY, ROLE, text_blocks
from intomd_converters.comms.model import HEADER_FIELDS, ParsedMessage
from intomd_converters.comms.options import CommsOptions

MAX_SIDECAR_HEADERS = 500
ALTERNATIVE_RATIO = 0.5


@dataclass(slots=True)
class MessageBuild:
    blocks: list[Block] = field(default_factory=list)
    children: list[Document] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    headers_sidecar: list[dict[str, SidecarScalar]] = field(default_factory=list)
    body_source: str = "none"
    body_alternatives: bool = False
    attachment_count: int = 0
    quotes_removed: int = 0


@dataclass(frozen=True, slots=True)
class MessageSpec:
    """Where a message sits: `source` labels its blocks, `level` is its heading level, `title` overrides the
    subject heading (mailboxes use `From · Date`), `index` numbers it inside a mailbox."""

    source: str
    level: int = 1
    title: str | None = None
    index: int | None = None
    depth: int = 0


def _prov(spec: MessageSpec, msg: ParsedMessage, path: str) -> Provenance:
    prefix = f"messages/{spec.index}/" if spec.index is not None else ""
    return Provenance(source=spec.source, path=prefix + path, source_id=msg.message_id)


def headers_table(msg: ParsedMessage, prov: Provenance) -> Table:
    rows = [(name, msg.headers[name]) for name in HEADER_FIELDS if msg.headers.get(name)]
    if msg.labels:
        rows.append(("Labels", ", ".join(msg.labels)))
    return _kv_table(("Header", "Value"), rows, prov, "headers", "Message headers")


def _kv_table(header: tuple[str, str], rows: list[tuple[str, str]], prov: Provenance, role: str, caption: str) -> Table:
    cells = [TableCell(spans=[InlineSpan(text=h)], row=0, col=c, is_header=True) for c, h in enumerate(header)]
    for r, (k, v) in enumerate(rows, start=1):
        cells.append(TableCell(spans=[InlineSpan(text=k)], row=r, col=0))
        cells.append(TableCell(spans=[InlineSpan(text=v)], row=r, col=1))
    return Table(
        cells=cells,
        n_rows=len(rows) + 1,
        n_cols=2,
        header_rows=1,
        provenance=prov,
        attrs={"role": role},
        caption=[InlineSpan(text=caption)],
    )


def shift_headings(blocks: list[Block], min_level: int) -> list[Block]:
    levels = [b.level for b in blocks if isinstance(b, Heading)]
    if not levels or min(levels) >= min_level:
        return blocks
    delta = min_level - min(levels)
    return [b.model_copy(update={"level": min(6, b.level + delta)}) if isinstance(b, Heading) else b for b in blocks]


def _text_len(blocks: list[Block]) -> int:
    total = 0
    for b in blocks:
        if isinstance(b, Paragraph | Quote | Heading):
            total += len(spans_text(b.spans))
    return total


def apply_quote_mode(blocks: list[Block], mode: str) -> tuple[list[Block], int]:
    """`keep` drops the history roles, `strip` removes history and its header line, `mark` leaves them."""
    if mode == "mark":
        return blocks, 0
    if mode == "keep":
        out: list[Block] = []
        for b in blocks:
            if b.attrs.get(ROLE) in (REPLY_HISTORY, REPLY_HEADER):
                out.append(b.model_copy(update={"attrs": {k: v for k, v in b.attrs.items() if k != ROLE}}))
            else:
                out.append(b)
        return out, 0
    removed = sum(1 for b in blocks if b.attrs.get(ROLE) == REPLY_HISTORY)
    if not removed:
        return blocks, 0
    return [b for b in blocks if b.attrs.get(ROLE) not in (REPLY_HISTORY, REPLY_HEADER)], removed


def _body(msg: ParsedMessage, spec: MessageSpec, options: ConvertOptions, opts: CommsOptions, out: MessageBuild,
          cid_refs: dict[str, str]) -> list[Block]:  # fmt: skip
    prov = _prov(spec, msg, "body")
    choice = opts.body
    use_html = bool(msg.html) and (choice in ("auto", "html") or not msg.text)
    if choice == "text" and msg.text:
        use_html = False
    text_part: list[Block] = []
    if msg.text:
        text_part = text_blocks(msg.text, prov, flowed=msg.text_flowed, delsp=msg.text_delsp)
    if use_html and msg.html:
        blocks, notes = html_blocks(msg.html, prov, options, cid_refs, f"m{spec.index or 0}-")
        out.warnings.extend(notes)
        if not blocks and text_part:
            blocks, out.body_source = text_part, "text"
        else:
            out.body_source = "html"
        if msg.text and _text_len(text_part) < ALTERNATIVE_RATIO * _text_len(blocks):
            out.body_alternatives = True
    else:
        blocks = text_part
        out.body_source = "text" if msg.text else "none"
    blocks = shift_headings(blocks, spec.level + 1)
    blocks, removed = apply_quote_mode(blocks, opts.strip_quotes)
    out.quotes_removed = removed
    return blocks


def build_message(msg: ParsedMessage, spec: MessageSpec, options: ConvertOptions, opts: CommsOptions) -> MessageBuild:
    out = MessageBuild(warnings=list(msg.warnings))
    head_prov = _prov(spec, msg, "headers")
    title = spec.title or msg.subject or "(no subject)"
    attrs: dict[str, str] = {}
    if msg.date is not None:
        attrs["timestamp"] = msg.date.isoformat()
    if spec.index is not None:
        attrs["depth"] = str(spec.depth)
    out.blocks.append(Heading(level=spec.level, spans=[InlineSpan(text=title)], provenance=head_prov, attrs=attrs))
    out.blocks.append(headers_table(msg, head_prov))
    cid_refs = inline_images(msg, options)
    out.blocks.extend(_body(msg, spec, options, opts, out, cid_refs))
    if out.quotes_removed:
        out.warnings.append(
            Warning(
                kind=WarningKind.QUOTED_HISTORY_REMOVED,
                message=f"{out.quotes_removed} quoted reply block(s) were removed.",
                count=out.quotes_removed,
            )
        )
    if msg.attachments:
        att_prov = _prov(spec, msg, "attachments")
        runner = AttachmentRunner(spec.source, options, opts)
        result = runner.run(msg, cid_refs)
        out.attachment_count = len(result.rows)
        out.blocks.append(
            Heading(level=min(6, spec.level + 1), spans=[InlineSpan(text="Attachments")], provenance=att_prov)
        )
        out.blocks.append(attachments_table(result.rows, att_prov))
        out.children.extend(result.children)
        out.warnings.extend(result.warnings)
    if opts.all_headers and msg.raw_headers:
        rows = [(k, v[: opts.max_header_chars]) for k, v in msg.raw_headers[:MAX_SIDECAR_HEADERS]]
        out.blocks.append(
            Heading(level=min(6, spec.level + 1), spans=[InlineSpan(text="All headers")], provenance=head_prov)
        )
        out.blocks.append(_kv_table(("Header", "Value"), rows, head_prov, "all_headers", "All headers"))
    for name, value in msg.raw_headers[:MAX_SIDECAR_HEADERS]:
        entry: dict[str, SidecarScalar] = {"name": name, "value": value[: opts.max_header_chars]}
        if spec.index is not None:
            entry["message"] = spec.index
        out.headers_sidecar.append(entry)
    return out


def table_rows(table: Table) -> list[tuple[str, str]]:
    """(first column, second column) text of a two-column key/value Table, header row excluded."""
    grid = table.grid()
    out: list[tuple[str, str]] = []
    for row in grid[table.header_rows :]:
        key = spans_text(row[0].spans) if row[0] is not None else ""
        value = spans_text(row[1].spans) if len(row) > 1 and row[1] is not None else ""
        out.append((key, value))
    return out
