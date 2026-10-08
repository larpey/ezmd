"""Plain-text email bodies to IR blocks (docs/spec/part2.md 9c steps 2 and 3).

format=flowed is unwrapped (RFC 3676), hard-wrapped lines join into paragraphs, `>` runs become Quote blocks
with their depth, an `On ... wrote:` / Outlook header line marks the quotes after it as reply history, and the
`-- ` delimiter or a `Sent from my ...` line starts a signature. Quote and signature roles live in
`attrs["role"]` (`reply_header`, `reply_history`, `signature`); `body_quotes` applies the strip mode.
"""

from __future__ import annotations

import re

from ezmd.ir import Block, InlineSpan, ListBlock, ListItem, Paragraph, Provenance, Quote
from ezmd_converters.text.lines import LINE_BREAKS_ATTR, LINE_BREAKS_HARD, join_lines

ROLE = "role"
REPLY_HEADER = "reply_header"
REPLY_HISTORY = "reply_history"
SIGNATURE = "signature"

REPLY_HEADER_RE = re.compile(
    r"^\s*(?:On\s.+\swrote|Le\s.+\sa\s+écrit|Am\s.+\sschrieb.*|El\s.+\sescribió|Op\s.+\sschreef)\s*:?\s*$",
    re.IGNORECASE | re.DOTALL,
)
ORIGINAL_RE = re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE)
OUTLOOK_BLOCK_RE = re.compile(r"^\s*From:\s.+\b(?:Sent|Date):\s.+\bSubject:", re.IGNORECASE | re.DOTALL)
SENT_FROM_RE = re.compile(r"^\s*Sent from my \w[\w ]{0,40}$", re.IGNORECASE)
_QUOTE_PREFIX = re.compile(r"^((?:>\s?)+)")
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d{1,3}[.)])\s+")


def unflow(text: str, delsp: bool) -> list[str]:
    """RFC 3676: a line ending in a space continues on the next line (same quote depth)."""
    out: list[str] = []
    pending: str | None = None
    pending_depth = -1
    for line in text.split("\n"):
        m = _QUOTE_PREFIX.match(line)
        depth = m.group(1).count(">") if m else 0
        body = line[m.end() :] if m else line
        if body.startswith(" "):
            body = body[1:]  # space-stuffing
        if pending is not None and depth == pending_depth:
            body = pending + body
        elif pending is not None:
            out.append(_requote(pending, pending_depth))
        pending = None
        if body.endswith(" ") and body != "-- ":
            pending = body[:-1] if delsp else body
            pending_depth = depth
            continue
        out.append(_requote(body, depth))
    if pending is not None:
        out.append(_requote(pending, pending_depth))
    return out


def _requote(body: str, depth: int) -> str:
    return ("> " * depth + body) if depth else body


def is_reply_header(text: str) -> bool:
    return bool(REPLY_HEADER_RE.match(text)) or bool(ORIGINAL_RE.match(text)) or bool(OUTLOOK_BLOCK_RE.match(text))


def text_blocks(text: str, prov: Provenance, *, flowed: bool = False, delsp: bool = False) -> list[Block]:
    lines = unflow(text, delsp) if flowed else text.split("\n")
    return _Builder(prov, flowed).run(lines)


def logical_lines(lines: list[str], flowed: bool) -> list[str]:
    """Hard-wrapped lines joined by the shared plain-text rule (`ezmd_converters.text.lines`)."""
    return [x.text for x in join_lines(lines, flowed=flowed)]


class _Builder:
    def __init__(self, prov: Provenance, flowed: bool = False) -> None:
        self.prov = prov
        self.flowed = flowed
        self.blocks: list[Block] = []
        self.para: list[str] = []
        self.quote: list[str] = []
        self.quote_depth = 0
        self.history = False
        """After a reply header: quotes (and, after an Outlook header, everything) are reply history."""
        self.outlook = False
        self.sig = False

    def run(self, lines: list[str]) -> list[Block]:
        i = 0
        while i < len(lines):
            line = lines[i].rstrip("\r")
            m = _QUOTE_PREFIX.match(line)
            if m:
                self._flush_para()
                depth = m.group(1).count(">")
                if self.quote and depth != self.quote_depth:
                    self._flush_quote()
                self.quote_depth = depth
                self.quote.append(line[m.end() :].strip())
                i += 1
                continue
            self._flush_quote()
            stripped = line.strip()
            joined = stripped
            if stripped.lower().startswith(("on ", "le ", "am ", "el ", "op ")) and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if not REPLY_HEADER_RE.match(stripped) and REPLY_HEADER_RE.match(f"{stripped} {nxt}"):
                    joined = f"{stripped} {nxt}"
                    i += 1
            if not self.outlook and (REPLY_HEADER_RE.match(joined) or ORIGINAL_RE.match(joined)):
                self._flush_para()
                self.sig = False
                self.history = True
                self.outlook = bool(ORIGINAL_RE.match(joined))
                self.blocks.append(self._para([joined], REPLY_HEADER))
                i += 1
                continue
            if line in ("-- ", "--") and not self.outlook:
                self._flush_para()
                self.sig = True
                i += 1
                continue
            if not stripped:
                self._flush_para()
            else:
                if SENT_FROM_RE.match(stripped) and not self.para and not self.outlook:
                    self.blocks.append(self._para([stripped], SIGNATURE))
                else:
                    self.para.append(stripped)
            i += 1
        self._flush_para()
        self._flush_quote()
        return self.blocks

    def _role(self) -> str | None:
        if self.outlook:
            return REPLY_HISTORY
        if self.sig:
            return SIGNATURE
        return None

    def _para(self, lines: list[str], role: str | None) -> Block:
        attrs = {ROLE: role} if role else {}
        return Paragraph(spans=[InlineSpan(text=" ".join(lines))], provenance=self.prov, attrs=attrs)

    def _quote_spans(self, groups: list[list[str]]) -> list[InlineSpan]:
        spans: list[InlineSpan] = []
        for group in groups:
            for line in logical_lines(group, self.flowed):
                if spans:
                    spans.append(InlineSpan(text="\n\n"))
                spans.append(InlineSpan(text=line))
        return spans

    def _flush_para(self) -> None:
        if not self.para:
            return
        raw, self.para = self.para, []
        role = self._role()
        if role == REPLY_HISTORY:
            spans = self._quote_spans([raw])
            self.blocks.append(Quote(spans=spans, provenance=self.prov, attrs={ROLE: REPLY_HISTORY}))
            return
        segment: list[str] = []
        segment_is_list = False
        for line in join_lines(raw, flowed=self.flowed):
            is_list = line.kind == "list" and role is None
            if segment and is_list != segment_is_list:
                self._emit(segment, segment_is_list, role)
                segment = []
            segment.append(line.text)
            segment_is_list = is_list
        if segment:
            self._emit(segment, segment_is_list, role)

    def _emit(self, lines: list[str], is_list: bool, role: str | None) -> None:
        if is_list:
            self.blocks.append(self._list(lines))
            return
        attrs = {ROLE: role} if role else {}
        if len(lines) > 1:
            attrs[LINE_BREAKS_ATTR] = LINE_BREAKS_HARD
        self.blocks.append(Paragraph(spans=[InlineSpan(text="\n".join(lines))], provenance=self.prov, attrs=attrs))

    def _list(self, lines: list[str]) -> ListBlock:
        items = [ListItem(spans=[InlineSpan(text=_BULLET_PREFIX.sub("", x))]) for x in lines]
        return ListBlock(items=items, ordered=bool(re.match(r"^\s*\d", lines[0])), provenance=self.prov)

    def _flush_quote(self) -> None:
        if not self.quote:
            return
        lines, self.quote = self.quote, []
        para: list[str] = []
        groups: list[list[str]] = []
        for line in [*lines, ""]:
            if line:
                para.append(line)
            elif para:
                groups.append(para)
                para = []
        spans = self._quote_spans(groups)
        if not spans:
            return
        attrs = {ROLE: REPLY_HISTORY} if self.history else {}
        self.blocks.append(Quote(spans=spans, depth=max(1, self.quote_depth), provenance=self.prov, attrs=attrs))
