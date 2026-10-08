"""HTML email bodies through the web family's HTML-to-IR module in file mode (docs/spec/part2.md 9c step 2).

The body runs through `ezmd_converters.web.pipeline.build_document` with the `full_body` engine (no
article extraction: an email has no boilerplate to remove, and readability heuristics drop quotes and
signatures). `cid:` references are rewritten to the inline image asset paths first. Gmail
(`gmail_quote`, `gmail_signature`) and Apple Mail (`blockquote type=cite`) markers are fingerprinted on the
parsed DOM and matched against the resulting Quote/Paragraph blocks to assign reply-history and signature
roles. When the web family is unavailable the visible text goes through the plain-text path.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import Any

import lxml.html  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from ezmd.context import ConvertContext
from ezmd.inputs import Detected, InputRef
from ezmd.ir import Block, Paragraph, Provenance, Quote, Warning, WarningKind, spans_text
from ezmd.registry import ConvertOptions
from ezmd_converters.comms.body_text import REPLY_HEADER, REPLY_HISTORY, ROLE, SIGNATURE, is_reply_header, text_blocks

log = logging.getLogger(__name__)

_CID = re.compile(r"""(?i)\bcid:([^"'\s>)]+)""")
_KEEP_WARNINGS = frozenset({WarningKind.INJECTION_SUSPECTED, WarningKind.REMOVED_HIDDEN_ELEMENTS})
_FP_CHARS = 48
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)
QUOTE_XPATH = (
    "//blockquote[contains(concat(' ', normalize-space(@class), ' '), ' gmail_quote ')]"
    " | //blockquote[@type='cite']"
    " | //div[contains(concat(' ', normalize-space(@class), ' '), ' gmail_quote ')]//blockquote"
)
SIGNATURE_XPATH = (
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' gmail_signature ')]"
    " | //*[@id='Signature'] | //*[contains(@class, 'moz-signature')]"
)


def fingerprint(text: str) -> str:
    return _NON_ALNUM.sub("", text).lower()[:_FP_CHARS]


def rewrite_cids(html: str, cid_refs: dict[str, str]) -> tuple[str, int]:
    """Replace `cid:<id>` with the asset path of the inline image; count references that resolve nowhere."""
    missing = 0

    def sub(m: re.Match[str]) -> str:
        nonlocal missing
        key = m.group(1).strip("<>").lower()
        ref = cid_refs.get(key)
        if ref is None:
            missing += 1
            return m.group(0)
        return ref

    return _CID.sub(sub, html), missing


def _markers(html: str) -> tuple[set[str], set[str]]:
    try:
        root = lxml.html.document_fromstring(html.encode("utf-8"), parser=lxml.html.HTMLParser(no_network=True))
    except Exception:
        return set(), set()
    quotes = {fingerprint(el.text_content() or "") for el in root.xpath(QUOTE_XPATH)}
    sigs = {fingerprint(el.text_content() or "") for el in root.xpath(SIGNATURE_XPATH)}
    return {q for q in quotes if q}, {s for s in sigs if s}


def html_blocks(
    html: str, prov: Provenance, options: ConvertOptions, cid_refs: dict[str, str], id_prefix: str = "m0-"
) -> tuple[list[Block], list[Warning]]:
    html, missing = rewrite_cids(html, cid_refs)
    warnings: list[Warning] = []
    if missing:
        warnings.append(
            Warning(
                kind=WarningKind.MISSING_RESOURCE,
                message=f"{missing} inline image reference(s) (cid:) point at parts the message does not contain.",
                count=missing,
            )
        )
    quote_fps, sig_fps = _markers(html)
    blocks, notes = _convert(html, options, prov)
    blocks = reid(blocks, id_prefix)
    warnings.extend(notes)
    marked: list[Block] = []
    for b in blocks:
        role: str | None = None
        text = spans_text(b.spans) if isinstance(b, Paragraph | Quote) else ""
        fp = fingerprint(text) if text else ""
        if isinstance(b, Quote) and fp and any(q.startswith(fp[:24]) or fp.startswith(q[:24]) for q in quote_fps):
            role = REPLY_HISTORY
        elif isinstance(b, Paragraph) and fp and any(s.startswith(fp[:24]) for s in sig_fps):
            role = SIGNATURE
        elif isinstance(b, Paragraph) and is_reply_header(" ".join(text.split())):
            role = REPLY_HEADER
        new_prov = prov.model_copy(update={"path": prov.path, "engine": b.provenance.engine})
        update: dict[str, object] = {"provenance": new_prov}
        if role:
            update["attrs"] = {**b.attrs, ROLE: role}
        marked.append(b.model_copy(update=update))
    return _history_after_headers(marked), warnings


_ID_KEYS = frozenset({"id", "parent_id", "footnote_ref", "anchor_block_id", "reply_to", "continued_from", "section_id"})
_BLOCK: TypeAdapter[Block] = TypeAdapter(Block)


def _prefixed(value: Any, prefix: str) -> Any:
    if isinstance(value, dict):
        return {
            k: (
                prefix + v
                if k in _ID_KEYS and isinstance(v, str) and v
                else (v if k == "attrs" else _prefixed(v, prefix))
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_prefixed(v, prefix) for v in value]
    return value


def reid(blocks: list[Block], prefix: str) -> list[Block]:
    """Blocks from the web pipeline already carry ids of their own document; prefix every id reference so
    they stay unique (and internally consistent) inside the email Document."""
    return [_BLOCK.validate_python(_prefixed(b.model_dump(mode="python"), prefix)) for b in blocks]


def _history_after_headers(blocks: list[Block]) -> list[Block]:
    """Quotes right after a reply-header paragraph are reply history even without Gmail/Apple markers; an
    Outlook `-----Original Message-----` / `From: Sent:` header makes everything after it history."""
    out: list[Block] = []
    after_header = False
    outlook = False
    for b in blocks:
        role = b.attrs.get(ROLE)
        if role == REPLY_HEADER:
            after_header = True
            text = " ".join(spans_text(b.spans).split()) if isinstance(b, Paragraph) else ""
            outlook = outlook or not text.lower().startswith(("on ", "le ", "am ", "el ", "op "))
            out.append(b)
            continue
        if outlook and role is None:
            out.append(b.model_copy(update={"attrs": {**b.attrs, ROLE: REPLY_HISTORY}}))
            continue
        if after_header and isinstance(b, Quote) and role is None:
            out.append(b.model_copy(update={"attrs": {**b.attrs, ROLE: REPLY_HISTORY}}))
            continue
        if not isinstance(b, Quote):
            after_header = False
        out.append(b)
    return out


def _convert(html: str, options: ConvertOptions, prov: Provenance) -> tuple[list[Block], list[Warning]]:
    try:
        from ezmd_converters.web.pipeline import build_document
    except ImportError:  # the web family is optional at import time; fall back to visible text
        log.info("web family unavailable; HTML email body converted as text")
        return text_blocks(_visible_text(html), prov), []
    ref = InputRef.from_bytes(html.encode("utf-8"), filename="body.html", declared_mime="text/html")
    ref.fetched_headers = {"content-type": "text/html; charset=utf-8"}
    ref.detected = Detected(mime="text/html", extension=".html", confidence=1.0)
    sub = dataclasses.replace(options, ctx=ConvertContext(), image_dir=None)
    try:
        doc = build_document(ref, sub, "full_body", "web.html_raw")
    finally:
        ref.cleanup()
    empty = any(w.kind in (WarningKind.EXTRACTION_EMPTY, WarningKind.EMPTY_BODY_JS_REQUIRED) for w in doc.warnings)
    blocks = [] if empty else list(doc.blocks)
    notes = [w for w in doc.warnings if w.kind in _KEEP_WARNINGS]
    return blocks, notes


def _visible_text(html: str) -> str:
    try:
        root = lxml.html.document_fromstring(html.encode("utf-8"), parser=lxml.html.HTMLParser(no_network=True))
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    for el in root.xpath("//script | //style | //head"):
        el.drop_tree()
    return root.text_content() or ""
