"""ezmd.testing.score: golden-fixture scorer (docs/spec/part1.md section 2.4).

Compares an actual rendered Markdown document against the expected golden, both in the `full`
profile, and returns sub-scores in [0, 1]:

- heading_score (0.25): F1 over (level, normalized text) heading pairs, averaged with a hierarchy
  term (fraction of expected parent->child heading relations preserved).
- table_score (0.25): each expected table matched to the best actual table by caption and shape;
  cell accuracy after whitespace and number normalization; minus 0.1 per unexpected extra table.
- text_score (0.30): rapidfuzz ratio over the concatenated, NFKC-normalized paragraph text (list item
  paragraphs included, so a changed list item is not invisible to the score).
- structure_score (0.20): per block-type count agreement averaged over types present in expected.

Frontmatter is ignored here (it holds timestamps); the fields that matter are compared exactly by
`ezmd.testing.invariants`, together with the structure a similarity score cannot see. Anchors (`{#sec-1}`)
and derived heading numbers are normalized away so that numbering changes do not dominate the heading score.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.token import Token
from rapidfuzz import fuzz

WEIGHTS = {"heading": 0.25, "table": 0.25, "text": 0.30, "structure": 0.20}
STRUCTURE_TYPES = (
    "list",
    "code",
    "image",
    "footnote",
    "equation",
    "transcript_segment",
    "comment",
    "tracked_change",
    "link",
)

_ANCHOR = re.compile(r"\s*\{#[^}]*\}\s*$")
_NUMBER = re.compile(r"^\d+(\.\d+)*\.?\s+")
_WS = re.compile(r"\s+")
_NUMERIC = re.compile(r"^[-+(]?[$€£]?\d[\d,]*(\.\d+)?%?\)?$")
_TIMESTAMP = re.compile(r"\[\d{2}:\d{2}:\d{2}\]")
_FOOTNOTE_DEF = re.compile(r"^\[\^[^\]]+\]:", re.M)


def _parser() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])


def strip_frontmatter(md: str) -> str:
    if md.startswith("---\n"):
        end = md.find("\n---\n", 4)
        if end != -1:
            return md[end + 5 :]
    return md


def norm(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def _norm_cell(text: str) -> str:
    t = norm(text).replace("\\|", "|")
    if _NUMERIC.match(t):
        return t.replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    return t.lower()


@dataclass(slots=True)
class ParsedTable:
    caption: str
    rows: list[list[str]]

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.rows), max((len(r) for r in self.rows), default=0)


@dataclass(slots=True)
class Parsed:
    headings: list[tuple[int, str]] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)


def _heading_text(raw: str) -> str:
    t = _ANCHOR.sub("", raw)
    t = _NUMBER.sub("", t)
    return norm(t).lower()


def parse(md: str) -> Parsed:
    body = strip_frontmatter(md)
    tokens = _parser().parse(body)
    out = Parsed()
    last_paragraph = ""
    i = 0
    list_depth = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open":
            out.headings.append((int(t.tag[1]), _heading_text(tokens[i + 1].content)))
        elif t.type == "paragraph_open":
            content = tokens[i + 1].content
            last_paragraph = content
            if not _is_caption(content):
                out.paragraphs.append(content)
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            if list_depth == 0:
                out.counts["list"] += 1
            list_depth += 1
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            list_depth -= 1
        elif t.type in ("fence", "code_block"):
            out.counts["code"] += 1
        elif t.type == "table_open":
            out.tables.append(_parse_table(tokens, i, last_paragraph))
        elif t.type == "html_block" and "<table" in t.content.lower():
            out.tables.append(_parse_html_table(t.content, last_paragraph))
        elif t.type == "inline":
            for c in t.children or []:
                if c.type == "image":
                    out.counts["image"] += 1
                elif c.type == "link_open":
                    out.counts["link"] += 1
        i += 1
    out.counts["footnote"] = len(_FOOTNOTE_DEF.findall(body))
    out.counts["equation"] = body.count("$$") // 2
    out.counts["transcript_segment"] = len(_TIMESTAMP.findall(body))
    out.counts["comment"] = body.count("{>>")
    out.counts["tracked_change"] = body.count("{++") + body.count("{--")
    return out


def _is_caption(text: str) -> bool:
    return bool(re.match(r"^\*\*Table \d+", text)) or text.startswith("Columns: ")


def _parse_table(tokens: list[Token], i: int, caption: str) -> ParsedTable:
    rows: list[list[str]] = []
    j = i + 1
    while j < len(tokens) and tokens[j].type != "table_close":
        if tokens[j].type == "tr_open":
            rows.append([])
        elif tokens[j].type == "inline" and rows:
            rows[-1].append(tokens[j].content)
        j += 1
    return ParsedTable(caption=norm(caption) if _is_caption(caption) else "", rows=rows)


def _parse_html_table(html: str, caption: str) -> ParsedTable:
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I)
        rows.append([re.sub(r"<[^>]+>", "", c) for c in cells])
    return ParsedTable(caption=norm(caption) if _is_caption(caption) else "", rows=rows)


def _f1(expected: list[tuple[int, str]], actual: list[tuple[int, str]]) -> float:
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0
    e, a = Counter(expected), Counter(actual)
    tp = sum((e & a).values())
    if tp == 0:
        return 0.0
    precision, recall = tp / sum(a.values()), tp / sum(e.values())
    return 2 * precision * recall / (precision + recall)


def _relations(headings: list[tuple[int, str]]) -> set[tuple[str, str]]:
    rels: set[tuple[str, str]] = set()
    stack: list[tuple[int, str]] = []
    for level, text in headings:
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            rels.add((stack[-1][1], text))
        stack.append((level, text))
    return rels


def heading_score(expected: Parsed, actual: Parsed) -> float:
    f1 = _f1(expected.headings, actual.headings)
    exp_rel = _relations(expected.headings)
    if not exp_rel:
        return f1
    hier = len(exp_rel & _relations(actual.headings)) / len(exp_rel)
    return (f1 + hier) / 2


def _cell_accuracy(e: ParsedTable, a: ParsedTable) -> float:
    total = sum(len(r) for r in e.rows)
    if total == 0:
        return 1.0 if not a.rows else 0.0
    hits = 0
    for r, row in enumerate(e.rows):
        for c, cell in enumerate(row):
            if r < len(a.rows) and c < len(a.rows[r]) and _norm_cell(a.rows[r][c]) == _norm_cell(cell):
                hits += 1
    return hits / total


def table_score(expected: Parsed, actual: Parsed) -> float:
    if not expected.tables:
        return max(0.0, 1.0 - 0.1 * len(actual.tables))
    remaining = list(actual.tables)
    scores: list[float] = []
    for et in expected.tables:
        best, best_rank, best_i = 0.0, -1.0, -1
        for k, at in enumerate(remaining):
            # Caption and shape agreement only break ties between candidates; the score is cell accuracy.
            s = _cell_accuracy(et, at)
            rank = (
                s + (0.01 if et.caption and et.caption == at.caption else 0.0) + (0.01 if et.shape == at.shape else 0.0)
            )
            if rank > best_rank:
                best, best_rank, best_i = s, rank, k
        scores.append(best)
        if best_i >= 0:
            remaining.pop(best_i)
    extra = max(0, len(actual.tables) - len(expected.tables))
    return max(0.0, sum(scores) / len(scores) - 0.1 * extra)


def text_score(expected: Parsed, actual: Parsed) -> float:
    e = norm(" ".join(expected.paragraphs))
    a = norm(" ".join(actual.paragraphs))
    if not e and not a:
        return 1.0
    return float(fuzz.ratio(e, a)) / 100.0


def structure_score(expected: Parsed, actual: Parsed) -> float:
    present = [t for t in STRUCTURE_TYPES if expected.counts[t] > 0]
    if not present:
        extra = sum(actual.counts[t] for t in STRUCTURE_TYPES)
        return 1.0 if extra == 0 else max(0.0, 1.0 - 0.1 * extra)
    parts = []
    for t in present:
        exp, act = expected.counts[t], actual.counts[t]
        parts.append(1 - min(1.0, abs(exp - act) / max(exp, 1)))
    return sum(parts) / len(parts)


@dataclass(frozen=True, slots=True)
class Score:
    heading: float
    table: float
    text: float
    structure: float

    @property
    def overall(self) -> float:
        return (
            WEIGHTS["heading"] * self.heading
            + WEIGHTS["table"] * self.table
            + WEIGHTS["text"] * self.text
            + WEIGHTS["structure"] * self.structure
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "heading": round(self.heading, 4),
            "table": round(self.table, 4),
            "text": round(self.text, 4),
            "structure": round(self.structure, 4),
            "overall": round(self.overall, 4),
        }


def score(expected_md: str, actual_md: str) -> Score:
    e, a = parse(expected_md), parse(actual_md)
    return Score(
        heading=heading_score(e, a),
        table=table_score(e, a),
        text=text_score(e, a),
        structure=structure_score(e, a),
    )
