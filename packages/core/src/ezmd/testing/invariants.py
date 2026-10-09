"""ezmd.testing.invariants: exact structural checks between a golden and an actual rendering.

The similarity score (`ezmd.testing.score`) tolerates small differences by design, and that tolerance let real
regressions through: a dropped rowspan, a changed table total, a removed equation or blockquote, a flattened
list, a removed link, a leaked hidden paragraph, or a downgraded `injection_risk` all scored above 0.95. These
invariants compare exact profiles of the expected and actual Markdown; every mismatch is a hard fixture failure,
whatever the score:

- `math`: the multiset of display (`$$...$$`) and inline (`$...$`) math expressions, outside code.
- `blocks`: counts of headings, paragraphs (anywhere, including inside lists and quotes), tables, code blocks,
  blockquotes and list items.
- `lists`: the (depth, ordered) sequence of list items, so nesting cannot be flattened or deepened.
- `table_spans`: per table, the (rowspan, colspan) of every cell in document order.
- `links` and `images`: the multiset of link targets and image sources.
- `numbers`: the multiset of numeric tokens in the body (anchors, link targets and HTML tag attributes removed),
  checked when `exact_numbers` is on (the default; see `ezmd.testing.fixtures`).
- `frontmatter`: `warnings` (as a set of codes), `injection_risk` and `truncated`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from markdown_it.token import Token

from ezmd.testing.score import _parser, norm, strip_frontmatter

FRONTMATTER_KEYS = ("warnings", "injection_risk", "truncated")

_FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[ ]*$", re.M | re.S)
_CODE_SPAN = re.compile(r"`[^`]*`")
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.S)
_INLINE_MATH = re.compile(r"(?<![\x5c$])\$(?!\$)([^$]+?)(?<![\x5c$])\$(?!\$)")
_ANCHOR = re.compile(r"\{#[^}]*\}")
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_TAG = re.compile(r"<[^>]+>")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_HTML_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
_HTML_CELL = re.compile(r"<t[hd]\b([^>]*)>", re.I)
_ROWSPAN = re.compile(r"rowspan\s*=\s*[\"']?(\d+)", re.I)
_COLSPAN = re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.I)
_HREF = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"']*)[\"']", re.I)
_SRC = re.compile(r"<img\b[^>]*?src\s*=\s*[\"']([^\"']*)[\"']", re.I)
_FM_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ ]?(.*)$")


@dataclass(slots=True)
class Profile:
    """Exact structural facts about one rendered Markdown document."""

    math: Counter[str] = field(default_factory=Counter)
    blocks: Counter[str] = field(default_factory=Counter)
    lists: list[tuple[int, bool]] = field(default_factory=list)
    table_spans: list[tuple[tuple[int, int], ...]] = field(default_factory=list)
    links: Counter[str] = field(default_factory=Counter)
    images: Counter[str] = field(default_factory=Counter)
    numbers: Counter[str] = field(default_factory=Counter)
    frontmatter: dict[str, object] = field(default_factory=dict)


def frontmatter_fields(md: str) -> dict[str, object]:
    """The FRONTMATTER_KEYS present in the leading `---` block (one `key: value` per line, as rendered)."""
    if not md.startswith("---"):
        return {}
    end = md.find(chr(10) + "---", 3)
    if end == -1:
        return {}
    out: dict[str, object] = {}
    for line in md[3:end].splitlines():
        m = _FM_LINE.match(line)
        if not m or m.group(1) not in FRONTMATTER_KEYS:
            continue
        key, value = m.group(1), m.group(2).strip()
        if key == "warnings":
            inner = value.strip("[]")
            out[key] = frozenset(w.strip().strip("\"'") for w in inner.split(",") if w.strip())
        else:
            out[key] = value.strip("\"'")
    return out


def _without_code(body: str) -> str:
    return _CODE_SPAN.sub(" ", _FENCE.sub(" ", body))


def _math(body: str) -> Counter[str]:
    text = _without_code(body)
    found: Counter[str] = Counter(norm(m) for m in _DISPLAY_MATH.findall(text))
    text = _DISPLAY_MATH.sub(" ", text)
    for line in text.splitlines():
        found.update(norm(m) for m in _INLINE_MATH.findall(line))
    return found


def _numbers(body: str) -> Counter[str]:
    text = _TAG.sub(" ", _LINK_TARGET.sub("]", _ANCHOR.sub(" ", body)))
    return Counter(_NUM.findall(text))


def _html_spans(html: str) -> list[tuple[tuple[int, int], ...]]:
    tables = []
    for table in _HTML_TABLE.findall(html):
        spans = []
        for attrs in _HTML_CELL.findall(table):
            r, c = _ROWSPAN.search(attrs), _COLSPAN.search(attrs)
            spans.append((int(r.group(1)) if r else 1, int(c.group(1)) if c else 1))
        tables.append(tuple(spans))
    return tables


def _md_table(tokens: list[Token], i: int) -> tuple[tuple[int, int], ...]:
    cells = []
    j = i + 1
    while j < len(tokens) and tokens[j].type != "table_close":
        if tokens[j].type in ("th_open", "td_open"):
            cells.append((1, 1))
        j += 1
    return tuple(cells)


def _html_refs(p: Profile, html: str) -> None:
    p.links.update(_HREF.findall(html))
    p.images.update(_SRC.findall(html))


def _inline(p: Profile, t: Token) -> None:
    for c in t.children or []:
        if c.type == "link_open":
            p.links[str(c.attrGet("href") or "")] += 1
        elif c.type == "image":
            p.images[str(c.attrGet("src") or "")] += 1
        elif c.type == "html_inline":
            _html_refs(p, c.content)


def profile(md: str) -> Profile:
    body = strip_frontmatter(md)
    p = Profile(math=_math(body), numbers=_numbers(body), frontmatter=frontmatter_fields(md))
    tokens = _parser().parse(body)
    stack: list[bool] = []
    for i, t in enumerate(tokens):
        if t.type == "heading_open":
            p.blocks["headings"] += 1
        elif t.type == "paragraph_open":
            p.blocks["paragraphs"] += 1
        elif t.type in ("fence", "code_block"):
            p.blocks["code"] += 1
        elif t.type == "blockquote_open":
            p.blocks["blockquotes"] += 1
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            stack.append(t.type == "ordered_list_open")
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            stack.pop()
        elif t.type == "list_item_open":
            p.blocks["list_items"] += 1
            p.lists.append((len(stack), stack[-1] if stack else False))
        elif t.type == "table_open":
            p.blocks["tables"] += 1
            p.table_spans.append(_md_table(tokens, i))
        elif t.type == "html_block":
            spans = _html_spans(t.content)
            p.blocks["tables"] += len(spans)
            p.table_spans.extend(spans)
            _html_refs(p, t.content)
        elif t.type == "inline":
            _inline(p, t)
    return p


def _counter_diff(name: str, expected: Counter[str], actual: Counter[str]) -> str | None:
    if expected == actual:
        return None
    missing = sorted((expected - actual).elements())
    extra = sorted((actual - expected).elements())
    return f"{name} differ: missing {missing[:8]}, unexpected {extra[:8]}"


def check(expected_md: str, actual_md: str, *, exact_numbers: bool = True) -> list[str]:
    """Every invariant the actual rendering breaks, as human-readable failure messages (empty when exact)."""
    e, a = profile(expected_md), profile(actual_md)
    failures: list[str] = []
    for key in FRONTMATTER_KEYS:
        if e.frontmatter.get(key) != a.frontmatter.get(key):
            failures.append(f"frontmatter {key}: expected {e.frontmatter.get(key)!r}, got {a.frontmatter.get(key)!r}")
    if e.blocks != a.blocks:
        failures.append(
            f"block counts differ: expected {dict(sorted(e.blocks.items()))}, got {dict(sorted(a.blocks.items()))}"
        )
    if e.lists != a.lists:
        failures.append(f"list nesting profile differs: expected {e.lists}, got {a.lists}")
    if e.table_spans != a.table_spans:
        failures.append(f"table cell spans differ: expected {e.table_spans}, got {a.table_spans}")
    for name, exp, act in (
        ("math expressions", e.math, a.math),
        ("link targets", e.links, a.links),
        ("image sources", e.images, a.images),
    ):
        msg = _counter_diff(name, exp, act)
        if msg:
            failures.append(msg)
    if exact_numbers:
        msg = _counter_diff("numeric tokens", e.numbers, a.numbers)
        if msg:
            failures.append(msg)
    return failures


def contains(haystack: str, needle: str, *, fold: bool) -> bool:
    """`needle` in `haystack`, raw or after NFKC and whitespace normalization (and casefolding when `fold`)."""
    if needle in haystack:
        return True
    n, h = norm(needle), norm(haystack)
    if fold:
        n, h = n.casefold(), h.casefold()
    return bool(n) and n in h


def check_text(actual_md: str, *, must_contain: list[str], must_not_contain: list[str]) -> list[str]:
    """meta.toml `must_contain` (case-sensitive) and `must_not_contain` (case-insensitive) over the whole
    rendered Markdown, frontmatter included."""
    failures = [f"must_contain {s!r} is missing" for s in must_contain if not contains(actual_md, s, fold=False)]
    failures += [f"must_not_contain {s!r} is present" for s in must_not_contain if contains(actual_md, s, fold=True)]
    return failures
