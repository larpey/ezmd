"""Filing HTML to raw IR blocks through the web family's HTML-to-IR module (part2 12c step 3).

EDGAR filings are machine-generated (Workiva, Donnelley, Toppan Merrill, EDGARizer): styling is inline CSS
(`font-weight:700` on a `<span>` instead of `<b>`), every table cell wraps its text in a `<div>`, and inline
XBRL tags (`ix:nonNumeric`, `ix:nonFraction`) sit inside the text. Before the shared converter runs we
read the `dei:` cover facts, drop the hidden `ix:header`, turn CSS bold and italic into tags, and unwrap
block wrappers inside table cells so data tables are not mistaken for layout tables.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from intomd.ir import Block
from intomd_converters.web.build import Builder
from intomd_converters.web.dom import HtmlElement, body_of, collapse, decode_html, is_element, parse_html, tag_of
from intomd_converters.web.html_blocks import convert_children
from intomd_converters.web.hygiene import HygieneReport, pre_clean

ENGINE = "specialized.edgar"
_BOLD = re.compile(r"font-weight\s*:\s*(bold|bolder|[6-9]00)\b", re.I)
_ITALIC = re.compile(r"font-style\s*:\s*(italic|oblique)\b", re.I)
_FACT_TAGS = ("ix:nonnumeric", "ix:nonfraction")
_HIDDEN_IX = ("ix:header",)
_CELL_BLOCKS = frozenset({"div", "p", "font", "center"})
_INLINE_STYLED = frozenset({"span", "font", "a", "ix:nonnumeric", "ix:nonfraction", "ix:continuation"})
_SEC_HEADER = re.compile(r"<SEC-HEADER>.*?</SEC-HEADER>", re.S | re.I)
_DOC_TEXT = re.compile(r"<DOCUMENT>.*?<TYPE>([^\n<]+).*?<TEXT>(.*?)</TEXT>", re.S | re.I)
MAX_FACT_CHARS = 300
_WINGDINGS = re.compile(r"font-family\s*:[^;]*wingdings", re.I)
UNCHECKED = chr(0x2610)
CHECKED = chr(0x2612)
_WING_MAP = {"o": UNCHECKED, "q": UNCHECKED, chr(0xA8): UNCHECKED, "x": CHECKED, chr(0xFE): CHECKED, chr(0xFD): CHECKED}


@dataclass(slots=True)
class ParsedFiling:
    blocks: list[Block]
    facts: dict[str, str] = field(default_factory=dict)
    """`dei:` local name -> rendered text, first occurrence wins."""
    hygiene: HygieneReport = field(default_factory=HygieneReport)
    encoding: str = "utf-8"
    text_chars: int = 0


def submission_document(raw: bytes) -> tuple[str, bytes] | None:
    """The first document of a complete submission text file (`<SEC-DOCUMENT>` with `<DOCUMENT>` parts):
    (type, body). None when `raw` is not a submission file."""
    head = raw[:4096].upper()
    if b"<SEC-DOCUMENT>" not in head and b"<SEC-HEADER>" not in head and b"<DOCUMENT>" not in head:
        return None
    text = _SEC_HEADER.sub("", raw.decode("utf-8", "replace"), count=1)
    m = _DOC_TEXT.search(text)
    if m is None:
        return None
    return m.group(1).strip(), m.group(2).strip().encode("utf-8")


def read_facts(root: HtmlElement) -> dict[str, str]:
    facts: dict[str, str] = {}
    for el in root.iter(*_FACT_TAGS):
        name = (el.get("name") or "").strip()
        if not name.lower().startswith("dei:"):
            continue
        local = name.split(":", 1)[1]
        value = collapse(el.text_content() or "")[:MAX_FACT_CHARS]
        if value and local not in facts:
            facts[local] = value
    return facts


def _wrap_children(el: HtmlElement, tag: str) -> None:
    """Move all content of `el` into a new `<tag>` child."""
    wrapper = el.makeelement(tag, {})
    wrapper.text, el.text = el.text, None
    for child in list(el):
        wrapper.append(child)
    el.append(wrapper)


def _styles_to_tags(body: HtmlElement) -> None:
    for el in list(body.iter()):
        if not is_element(el):
            continue
        style = el.get("style") or ""
        if not style:
            continue
        tag = tag_of(el)
        for pattern, new in ((_BOLD, "b"), (_ITALIC, "i")):
            if not pattern.search(style):
                continue
            if tag in ("span", "font"):
                el.tag = new
                tag = new
            elif tag not in ("b", "strong", "i", "em", "table", "tr", "td", "th") and not tag.startswith("ix:"):
                if (el.text or "").strip() or len(el):
                    _wrap_children(el, new)


def _checkboxes(body: HtmlElement) -> None:
    """Wingdings check boxes (`o` unchecked, `x`/`þ` checked) become the Unicode ballot boxes, also when the
    glyph sits inside an inline XBRL tag (`ix:nonNumeric name="dei:EntityEmergingGrowthCompany"`)."""
    for el in list(body.iter()):
        if not (is_element(el) and _WINGDINGS.search(el.get("style") or "")):
            continue
        for node in el.iter():
            if not is_element(node):
                continue
            if (node.text or "").strip() in _WING_MAP:
                node.text = _WING_MAP[(node.text or "").strip()]
            if node is not el and (node.tail or "").strip() in _WING_MAP:
                node.tail = _WING_MAP[(node.tail or "").strip()]


def _unwrap_cells(body: HtmlElement) -> None:
    """Block wrappers inside `<td>`/`<th>` become inline spans, separated by a line break."""
    for cell in list(body.iter("td", "th")):
        wrappers = [d for d in cell.iter() if d is not cell and is_element(d) and tag_of(d) in _CELL_BLOCKS]
        for n, d in enumerate(wrappers):
            d.tag = "span"
            if n < len(wrappers) - 1 and collapse(d.text_content() or ""):
                d.tail = " " + (d.tail or "")


def _drop_hidden_ix(root: HtmlElement) -> None:
    for tag in _HIDDEN_IX:
        for el in list(root.iter(tag)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)


def parse_filing(raw: bytes, *, source: str, base: str | None, headers: dict[str, str] | None = None) -> ParsedFiling:
    text, encoding, _conf = decode_html(raw, headers)
    root = parse_html(text)
    facts = read_facts(root)
    _drop_hidden_ix(root)
    hygiene = pre_clean(root)
    body = body_of(root)
    _checkboxes(body)
    _styles_to_tags(body)
    _unwrap_cells(body)
    b = Builder(source=source, base=base, engine=ENGINE)
    convert_children(body, b)
    return ParsedFiling(
        blocks=b.blocks,
        facts=facts,
        hygiene=hygiene,
        encoding=encoding,
        text_chars=len(collapse(body.text_content() or "")),
    )
