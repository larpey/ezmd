"""arXiv papers: fidelity, declared versus silent loss, outline, tokens and local-model QA.

Whole born-digital papers, scored against witnesses the PDF itself carries, so no human ground truth is needed:

- the text layer (pypdfium2, every page): the words any text-layer converter had available. `text recall` is
  the share of its word occurrences (3+ alphanumerics, NFKC-folded) found in the tool's output. Running headers
  and footers are in the text layer, so a converter that drops them on purpose loses a little recall here;
  ezmd declares that drop with a warning, which is the point of the next metric.
- `silent loss`: a document lost more than LOSS_THRESHOLD of its words and the tool said nothing. ezmd's
  warnings (written by the adapter as `<output>.warnings.json`) and its `truncated` flag count as saying
  something when they are of a kind that means content was dropped or cut (LOSS_KINDS). Deliberate removals
  ezmd announces on nearly every paper (running headers, hidden elements) are not in that set: a warning that
  always fires cannot tell a reader this document is the one that lost something, so ezmd gets no credit for
  it here, which makes the standard stricter for ezmd, not looser. No competitor has a warning channel, so for
  them every such loss is silent. A failed conversion is loud, not silent.
- the bookmarks (`get_toc`): `outline recall` is the share of bookmarks found as a heading in the output,
  numbering ignored, over documents with at least OUTLINE_MIN bookmarks.
- `tokens per page`: o200k_base tokens of the output (ezmd's frontmatter removed, as in every scorer; base64
  images a tool embeds count as one placeholder each) per PDF page. Lower is better.
- `answer accuracy` and `correct answers per 10k tokens`: from tools/bench/qa.py when it has run (questions a
  local model wrote from the text layer, answered from each tool's output, graded by the same model).

The primary metric is answer accuracy when QA ran, else text recall.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from tools.bench.corpora import arxiv_root
from tools.bench.schema import DocResult
from tools.bench.scoring.common import attempted, by_tool, summarize
from tools.bench.scoring.text import is_ezmd, read_output

LOSS_THRESHOLD = 0.05
"""A document with more than this share of its text-layer words missing from the output has lost content."""
OUTLINE_MIN = 3
"""Papers with fewer bookmarks than this are not scored for outline recall."""
LOSS_KINDS = frozenset(
    {
        "engine_failed",
        "converter_failed",
        "extraction_empty",
        "size_cap",
        "page_cap_reached",
        "page_timeout",
        "row_cap_reached",
        "timeout_partial",
        "timeout_hard",
        "unsupported_feature",
        "pages_without_text",
        "file_repaired",
        "unmapped_glyphs",
        "ocr_unavailable",
        "equation_unrecognized",
        "equation_partial",
        "image_skipped",
        "markup_partial",
        "xfa_partial",
    }
)
"""ezmd warning codes that tell the reader this document had content dropped, cut or not understood."""

WORD = re.compile(r"[a-z0-9]{3,}")
_PDFIUM_MARKS = re.compile("[" + chr(0xFFFE) + chr(0x02) + chr(0xAD) + "]" + r"\s*")
"""pdfium's line-end hyphenation markers and soft hyphens."""
_LINE_HYPHEN = re.compile(r"-\s*\n\s*")
_NUMBERING = re.compile(r"^(?:(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z](?:\.\d+)*|Appendix\s+[A-Z])\.?[\s:]+)", re.I)
_MD = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])


def norm(text: str) -> str:
    text = _PDFIUM_MARKS.sub("", text)
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _LINE_HYPHEN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> Counter[str]:
    return Counter(WORD.findall(norm(text)))


def recall(source: Counter[str], output: Counter[str]) -> float:
    """Share of the source's word occurrences present in the output (each occurrence matched at most once)."""
    total = sum(source.values())
    if not total:
        return 1.0
    return sum(min(n, output.get(w, 0)) for w, n in source.items()) / total


def headings_of(md: str) -> list[str]:
    out: list[str] = []
    tokens = _MD.parse(md)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and i + 1 < len(tokens) and tokens[i + 1].type == "inline":
            text = "".join(c.content for c in tokens[i + 1].children or [] if c.type in ("text", "code_inline"))
            if text.strip():
                out.append(text.strip())
    return out


def heading_key(text: str) -> str:
    return norm(_NUMBERING.sub("", text.strip()))


def outline_recall(bookmarks: list[str], headings: list[str]) -> float | None:
    """Share of bookmarks that appear as a heading (same text after numbering is removed, or a bookmark of
    eight or more characters contained in a heading); None when the PDF has too few bookmarks to judge."""
    keys = [heading_key(b) for b in bookmarks if heading_key(b)]
    if len(keys) < OUTLINE_MIN:
        return None
    heads = [heading_key(h) for h in headings]
    found = sum(1 for k in keys if any(k == h or (len(k) >= 8 and k in h) for h in heads))
    return found / len(keys)


@dataclass(frozen=True, slots=True)
class Witness:
    pages: int
    words: Counter[str]
    bookmarks: list[str]
    text: str
    source: Counter[str] | None = None
    """Words of the paper's LaTeX source (scoring/latex.py), when it was fetched and has a main file."""

    @property
    def text_layer_source_recall(self) -> float | None:
        """The raw pdfium text layer's own recall against the source: the reference a text-layer reader is
        measured by (a converter can beat it a little by joining hyphenated words and folding ligatures)."""
        return recall(self.source, self.words) if self.source else None


def witness_dir() -> Path:
    return arxiv_root() / "witness"


def arxiv_id(doc_id: str) -> str:
    """`2301_00845` -> `2301.00845` (document ids are file-name safe; arXiv ids carry a dot)."""
    return doc_id.replace("_", ".", 1)


def witness(doc_id: str, pdf: Path) -> Witness:
    """The PDF's own text layer and bookmarks, extracted once and cached as JSON under the corpus, plus the
    words of the LaTeX source when `fetch --only arxiv-source` has stored it."""
    from tools.bench.scoring.latex import source_text

    path = witness_dir() / f"{doc_id}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(pdf))
        try:
            parts = []
            for page in doc:
                tp = page.get_textpage()
                parts.append(tp.get_text_range())
                tp.close()
                page.close()
            data = {"pages": len(doc), "text": "\n".join(parts), "bookmarks": [b.get_title() for b in doc.get_toc()]}
        finally:
            doc.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    source = source_text(doc_id, arxiv_id(doc_id))
    return Witness(
        int(data["pages"]),
        words(str(data["text"])),
        list(data["bookmarks"]),
        str(data["text"]),
        words(source) if source else None,
    )


_DATA_URI = re.compile(r"data:[a-zA-Z0-9.+/-]+;base64,[A-Za-z0-9+/=\s]+")


def strip_data_uris(text: str) -> str:
    """Base64 images a tool embeds (MinerU) replaced by a short placeholder: they are not text, and a
    tokenizer's pre-split regex can choke on a 300 KB run with no whitespace."""
    return _DATA_URI.sub("data:image", text)


def count_tokens(text: str) -> int:
    """o200k_base tokens of the text a user would feed a model. Images a tool embeds as base64 data URIs
    (MinerU) are not text and are counted as one placeholder each; a model API takes them as images, not
    tokens of Markdown."""
    import tiktoken

    return len(tiktoken.get_encoding("o200k_base").encode(strip_data_uris(text), disallowed_special=()))


def declared_loss(result: DocResult, run_dir: Path) -> bool | None:
    """True/False for a tool with a warning channel (ezmd: `<output>.warnings.json`), None for one without."""
    if not is_ezmd(result.tool) or not result.output:
        return None
    path = run_dir / (result.output + ".warnings.json")
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    kinds = {str(w.get("kind")) for w in data.get("warnings", [])}
    return bool(data.get("truncated")) or bool(kinds & LOSS_KINDS)


@dataclass(frozen=True, slots=True)
class QaScore:
    correct: int
    asked: int
    tail_correct: int
    """Correct answers to questions whose evidence lies in the second half of the paper's text layer."""
    tail_asked: int
    cut: bool
    """The tool's output did not fit the answering model's context and was cut before it was sent."""

    @property
    def accuracy(self) -> float:
        return self.correct / self.asked

    @property
    def tail_accuracy(self) -> float | None:
        return self.tail_correct / self.tail_asked if self.tail_asked else None


def in_second_half(item: dict[str, Any]) -> bool | None:
    """Whether a question's evidence lies in the second half of the text layer (by the midpoint of the segment
    it was written from); None for a question written without a segment (an older question file)."""
    seg = item.get("segment")
    if not isinstance(seg, dict) or not seg.get("of"):
        return None
    return (float(seg.get("from", 0)) + float(seg.get("to", 0))) / 2 >= float(seg["of"]) / 2


def qa_scores(result: DocResult, run_dir: Path) -> QaScore | None:
    """What tools/bench/qa.py's graded file says for this tool and document, None when there is none."""
    path = run_dir / "qa" / result.tool / f"{result.doc_id}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    graded = [it for it in record.get("items", []) if "correct" in it]
    if not graded:
        return None
    tail = [it for it in graded if in_second_half(it)]
    return QaScore(
        correct=sum(1 for it in graded if it["correct"]),
        asked=len(graded),
        tail_correct=sum(1 for it in tail if it["correct"]),
        tail_asked=len(tail),
        cut=bool(record.get("cut")),
    )


def score_doc(result: DocResult, run_dir: Path, inputs: dict[str, Path]) -> dict[str, float | None]:
    w = witness(result.doc_id, inputs[result.doc_id])
    md = read_output(result, run_dir)
    ok = result.status == "ok"
    rec = recall(w.words, words(md)) if ok else 0.0
    lost = rec < 1.0 - LOSS_THRESHOLD
    declared = declared_loss(result, run_dir)
    tokens = count_tokens(md) if ok else None
    from tools.bench.tokens import cached_pdf_count, cached_record  # Claude counts when `tokens` has run

    claude_record = cached_record(run_dir, result) if ok else None
    claude = claude_record["tokens"] if claude_record else None
    pdf_upload = cached_pdf_count(run_dir, result.doc_id, inputs[result.doc_id])
    qa = qa_scores(result, run_dir)
    out: dict[str, float | None] = {
        "arxiv-text-recall": round(rec, 4),
        "arxiv-source-recall": (None if w.source is None else round(recall(w.source, words(md)), 4) if ok else 0.0),
        "arxiv-silent-loss": float(ok and lost and not declared),
        "arxiv-outline-recall": outline_recall(w.bookmarks, headings_of(md) if ok else []),
        "arxiv-tokens-per-page": round(tokens / w.pages, 1) if tokens is not None and w.pages else None,
        "arxiv-claude-tokens-per-page": round(claude / w.pages, 1) if claude is not None and w.pages else None,
        "arxiv-qa": None if qa is None else round(qa.accuracy, 4),
        "arxiv-qa-second-half": None if qa is None or qa.tail_accuracy is None else round(qa.tail_accuracy, 4),
        "arxiv-answers-per-10k-tokens": (
            round(qa.correct / tokens * 10_000, 3) if qa is not None and tokens else (0.0 if qa is not None else None)
        ),
        "qa_asked": None if qa is None else float(qa.asked),
        "qa_correct": None if qa is None else float(qa.correct),
        "qa_tail_asked": None if qa is None else float(qa.tail_asked),
        "qa_tail_correct": None if qa is None else float(qa.tail_correct),
        "qa_cut": None if qa is None else float(qa.cut),
        "lost": float(lost),
        "declared": None if declared is None else float(declared),
        "tokens": None if tokens is None else float(tokens),
        "text_layer_source_recall": w.text_layer_source_recall,
        "claude_model": claude_record["model"] if claude_record else None,
        "claude_pdf_upload": None if pdf_upload is None else float(pdf_upload),
        "claude_share_of_pdf_upload": (round(claude / pdf_upload, 4) if claude is not None and pdf_upload else None),
    }
    return out


def _mean(values: list[float | None]) -> float | None:
    kept = [v for v in values if v is not None]
    return round(sum(kept) / len(kept), 4) if kept else None


def _qa_pooled(per_doc: dict[str, dict[str, float | None]]) -> dict[str, dict[str, Any]]:
    docs = [v for v in per_doc.values() if v.get("qa_asked") is not None]

    def total(key: str) -> int:
        return int(sum(float(v[key] or 0) for v in docs))

    asked, correct = total("qa_asked"), total("qa_correct")
    tail_asked, tail_correct = total("qa_tail_asked"), total("qa_tail_correct")
    head_asked, head_correct = asked - tail_asked, correct - tail_correct
    return {
        "qa_questions": {"value": asked, "n": len(docs)},
        "qa_pooled_accuracy": {"value": round(correct / asked, 4) if asked else None, "n": asked},
        "qa_first_half": {"value": round(head_correct / head_asked, 4) if head_asked else None, "n": head_asked},
        "qa_second_half": {"value": round(tail_correct / tail_asked, 4) if tail_asked else None, "n": tail_asked},
        "qa_outputs_cut": {"value": total("qa_cut"), "n": len(docs)},
    }


def _mean_ratio(per_doc: dict[str, dict[str, float | None]], key: str, inputs: dict[str, Path]) -> float | None:
    """Mean of per_doc[key] per PDF page over the documents that have the value."""
    rows = []
    for doc_id, v in per_doc.items():
        if v.get(key) is not None:
            pages = witness(doc_id, inputs[doc_id]).pages
            if pages:
                rows.append(float(v[key]) / pages)  # type: ignore[arg-type]
    return round(sum(rows) / len(rows), 1) if rows else None


def _inputs(run_dir: Path) -> dict[str, Path]:
    docs = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))
    return {d["id"]: Path(d["input"]) for d in docs["documents"]}


CATEGORIES = (
    "arxiv-qa",
    "arxiv-qa-second-half",
    "arxiv-text-recall",
    "arxiv-source-recall",
    "arxiv-silent-loss",
    "arxiv-outline-recall",
    "arxiv-tokens-per-page",
    "arxiv-claude-tokens-per-page",
    "arxiv-answers-per-10k-tokens",
)
DIRECTION = {
    c: c not in ("arxiv-silent-loss", "arxiv-tokens-per-page", "arxiv-claude-tokens-per-page") for c in CATEGORIES
}


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    inputs = _inputs(run_dir)
    tools: dict[str, Any] = {}
    any_qa = False
    for tool, rs in sorted(by_tool(results).items()):
        rs = attempted(rs)
        if not rs:
            continue
        per_doc = {r.doc_id: score_doc(r, run_dir, inputs) for r in rs}
        cats: dict[str, Any] = {}
        for cat in CATEGORIES:
            values = {d: v[cat] for d, v in per_doc.items() if v[cat] is not None}
            cats[cat] = {**summarize(list(values.values())), "per_doc": values}
        any_qa = any_qa or cats["arxiv-qa"]["n"] > 0
        declared = [v["declared"] for v in per_doc.values() if v["declared"] is not None]
        lost = [v["lost"] for v in per_doc.values()]
        refs = [v["text_layer_source_recall"] for v in per_doc.values() if v["text_layer_source_recall"] is not None]
        secondary = {
            # Answer accuracy pooled over questions rather than averaged over papers (the categories average over
            # papers), split by where the question's evidence lies: a converter that cuts a paper's tail shows
            # in the second half. `qa_outputs_cut` counts documents whose output did not fit the model's context.
            **_qa_pooled(per_doc),
            # The same for every tool: the raw pdfium text layer's own recall against the LaTeX source, the
            # reference to read arxiv-source-recall by.
            "text_layer_source_recall": {"value": round(sum(refs) / len(refs), 4) if refs else None},
            # The model whose tokenizer produced arxiv-claude-tokens-per-page (tools/bench/tokens.py --model).
            "claude_model": {"value": sorted({v["claude_model"] for v in per_doc.values() if v["claude_model"]})},
            # The baseline every tool is measured against: Claude tokens charged for uploading the PDF itself
            # (its text plus an image of each page), per page, over the papers that were counted; and this tool's
            # converted output as a share of that.
            "claude_pdf_upload_tokens_per_page": {"value": _mean_ratio(per_doc, "claude_pdf_upload", inputs)},
            "claude_share_of_pdf_upload": {
                "value": _mean([v["claude_share_of_pdf_upload"] for v in per_doc.values()]),
                "n": sum(1 for v in per_doc.values() if v["claude_share_of_pdf_upload"] is not None),
            },
            "lost_rate": {"value": round(sum(lost) / len(lost), 4) if lost else None},
            "declared_rate": {"value": round(sum(declared) / len(declared), 4) if declared else None},
            "false_alarm_rate": {
                "value": round(sum(1 for v in per_doc.values() if v["declared"] and not v["lost"]) / len(per_doc), 4)
                if declared
                else None
            },
            "median_tokens": {
                "value": sorted(v["tokens"] for v in per_doc.values() if v["tokens"] is not None)[
                    len([v for v in per_doc.values() if v["tokens"] is not None]) // 2
                ]
                if any(v["tokens"] is not None for v in per_doc.values())
                else None
            },
        }
        primary_cat = "arxiv-qa" if cats["arxiv-qa"]["n"] else "arxiv-text-recall"
        tools[tool] = {
            "primary": {k: cats[primary_cat][k] for k in ("value", "ci", "n")},
            # Named per tool: a tool whose answers were not graded falls back to text recall, and the summary must
            # not print that number under the other tools' label.
            "metric": "qa_accuracy" if primary_cat == "arxiv-qa" else "text_recall",
            "categories": cats,
            "per_doc": cats[primary_cat]["per_doc"],
            "secondary": secondary,
        }
    return {
        "corpus": "arxiv",
        "metric": "qa_accuracy" if any_qa else "text_recall",
        "higher_is_better": True,
        "category_direction": DIRECTION,
        "tools": tools,
    }
