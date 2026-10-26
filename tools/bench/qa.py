"""Question answering over converted documents with a local model (LM Studio or any OpenAI-compatible server).

    uv run python -m tools.bench qa generate --corpus arxiv --date D   # questions from each PDF's text layer
    uv run python -m tools.bench qa answer   --corpus arxiv --date D   # each tool's output answers them
    uv run python -m tools.bench qa grade    --corpus arxiv --date D   # the model grades against the reference
    uv run python -m tools.bench qa all      --corpus arxiv --date D

Why a text-layer witness: the questions are written from the PDF's own text (pypdfium2), never from any tool's
output, so no converter gets to choose what is asked. Every question must come with a quote, and a question
whose quote is not grounded in the text layer (verbatim, or most of its words plus every word of the answer)
is thrown away: that filters invented facts. The same model answers from
each tool's Markdown with the instruction to say UNKNOWN when the text does not contain the answer, then grades
each answer against the reference. Grading short factual answers is an easy task for a local model; writing the
questions is the hard one, which is why their quotes are checked mechanically.

Why segments: asked for questions over a whole paper, a model takes most of them from the first pages, so a
converter that drops the tail (ezmd's `compact` profile cuts at 16k tokens) is barely measured. The text layer
is therefore split into SEGMENT_TOKENS-token segments and each segment is asked for its own questions, whose
quotes must be grounded in that segment; every question records where in the paper its evidence lies
(`segment: {from, to, of}` in text-layer tokens), and the scorer reports accuracy over the second half of the
papers separately. The answering model then reads each tool's whole output: the context is CONTEXT_TOKENS and
an output that does not fit is cut, which the answer record says (`cut`).

Questions are cached per document under the corpus (`corpora/arxiv/qa/<doc>.json`) and shared by every tool and
run; a file written under an older scheme (`scheme`) is generated again. Answers and grades go to
`<run_dir>/qa/<tool>/<doc>.json`, which tools/bench/scoring/arxiv.py reads.

Determinism: temperature 0 and a fixed seed; the model id and the server are recorded in every file. Nothing
leaves the machine.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.bench.corpora import arxiv_root
from tools.bench.schema import DocResult, read_results
from tools.bench.scoring.arxiv import WORD, count_tokens, norm, strip_data_uris, witness
from tools.bench.scoring.text import read_output

DEFAULT_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "openai/gpt-oss-20b"
CONTEXT_TOKENS = 131_072
"""Context the model is loaded with by default (gpt-oss-20b's maximum): the longest output of the 30-paper
sample is 104k tokens, so every tool's whole output fits. llama.cpp shares one KV cache between parallel
requests, so the model is loaded with the context times the worker count; `--context` lowers it on a smaller
GPU, and outputs that do not fit are cut and marked."""
PROMPT_RESERVE = 4_096
"""Context kept free of the document for the prompt, the questions and the reply."""
SEGMENT_TOKENS = 8_000
"""Questions are written per segment of this many text-layer tokens (about three pages), so the tail of a
paper is asked about as much as its abstract."""
MODEL_TTL_SECONDS = 4 * 3600
"""LM Studio unloads the model after this long idle; a run keeps it busy, the next morning does not."""
QUESTIONS_WANTED = 3
"""Asked per segment."""
QUESTIONS_KEPT = 2
"""Kept per segment, so a 25-page paper gets about eight questions and a 75-page paper about sixteen."""
SCHEME = "segments-8k"
"""Written into every question file; a file from another scheme is generated again."""
SEED = 20261013
UNKNOWN = "UNKNOWN"

GENERATE_PROMPT = """You are writing a reading-comprehension test for a scientific paper. Below is part {part} of
{parts} of the paper's text.

Write {n} question/answer pairs that check whether a reader has the content of this part. Rules:
- Each answer is a specific fact stated explicitly in the text: a number with its unit, a name, a term, a short
  phrase. Answers are at most 12 words.
- Prefer facts a reader of the whole paper is expected to know: results, definitions, methods, settings. Ask at
  least one question about a numeric result if this part states one, and if it has a table, ask one question
  whose answer is a value in it.
- Each question must make sense on its own to a reader who has the whole paper: name the quantity, method or
  object asked about; never write "this section", "the table above" or "the excerpt".
- Do not ask about figures, images or anything that needs a picture to answer. Do not ask about the authors,
  the venue, the date or the reference list.
- Each pair carries a "quote": the exact sentence or table row from the text that contains the answer, copied
  verbatim.

Reply with a JSON array only, no prose: [{{"question": "...", "answer": "...", "quote": "..."}}, ...]

PART {part} OF {parts}:
{text}"""

ANSWER_PROMPT = """Answer each question using only the document below. Reply with the fact asked for, in at most
12 words, no explanation. If the document does not contain the information, reply exactly {unknown}.

Reply with a JSON array of strings only, one answer per question, in order.

QUESTIONS:
{questions}

DOCUMENT:
{text}"""

GRADE_PROMPT = """You are grading short answers against reference answers. For each item decide whether the
candidate answer states the same fact as the reference: numbers must agree (rounding and unit conversion are
fine), names and terms must refer to the same thing, extra correct detail is fine, and "{unknown}" or a missing
answer is wrong.

Reply with a JSON array of booleans only, one per item, in order.

ITEMS:
{items}"""


class Client:
    """A minimal OpenAI-compatible chat client (standard library only)."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def models(self) -> list[str]:
        with urllib.request.urlopen(f"{self.base_url}/models", timeout=30) as resp:  # noqa: S310 (local server)
            data = json.load(resp)
        return [str(m.get("id")) for m in data.get("data", [])]

    def chat(self, prompt: str, *, max_tokens: int) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": SEED,
            "max_tokens": max_tokens,
            "reasoning_effort": "low",
        }
        req = urllib.request.Request(  # noqa: S310 (local server)
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1800) as resp:  # noqa: S310 (local server)
            data = json.load(resp)
        return str(data["choices"][0]["message"].get("content") or "")


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.M)
_BAD_ESCAPE = re.compile(r"\\\\|\\(?![\\\"/bfnrtu])")
"""An escaped backslash (kept as it is) or a backslash that starts no JSON escape (doubled). Matching the pair
first keeps `\\\\sum` (a TeX command the model escaped correctly) from becoming three backslashes."""


def _fix_escapes(body: str) -> str:
    return _BAD_ESCAPE.sub(lambda m: "\\\\", body)  # a pair stays a pair, a lone backslash becomes one


def _note(exc: Exception) -> None:
    """A reply that was not the JSON asked for; the call is retried once."""
    print(f"qa: retrying after {type(exc).__name__}: {str(exc)[:120]}", file=sys.stderr, flush=True)


def parse_json_array(text: str) -> list[Any]:
    """The first JSON array in a reply (code fences and chatter around it ignored)."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        raise ValueError(f"no JSON array in reply: {text[:200]!r}")
    body = cleaned[start : end + 1]
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        # Models copy TeX into quotes as written (\alpha, \Delta): a backslash that starts no JSON escape is a
        # literal backslash.
        value = json.loads(_fix_escapes(body))
    if not isinstance(value, list):
        raise ValueError("reply is not a JSON array")
    return value


def cut_tokens(text: str, limit: int) -> str:
    """The longest prefix of `text` within `limit` o200k tokens (cut at a line end)."""
    if count_tokens(text) <= limit:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count_tokens(text[:mid]) <= limit:
            lo = mid
        else:
            hi = mid - 1
    cut = text[:lo]
    nl = cut.rfind("\n")
    return cut[:nl] if nl > lo // 2 else cut


@dataclass(frozen=True, slots=True)
class Segment:
    start: int
    """Token offset of the segment's first line in the whole text."""
    end: int
    text: str

    def where(self, total: int) -> dict[str, int]:
        return {"from": self.start, "to": self.end, "of": total}


def segments(text: str, size: int = SEGMENT_TOKENS) -> list[Segment]:
    """The text in consecutive pieces of at most `size` o200k tokens, cut at line ends (a single line longer
    than `size` is cut inside). A trailing piece shorter than a quarter of `size` joins the one before it, so a
    paper's last lines are asked about with their context rather than alone."""
    if not text:
        return [Segment(0, 0, "")]
    pieces: list[tuple[int, list[str]]] = []  # (tokens, lines)
    tokens = 0
    lines: list[str] = []
    for line in text.split("\n"):
        n = count_tokens(line + "\n")
        if n > size:
            if lines:
                pieces.append((tokens, lines))
                tokens, lines = 0, []
            rest = line
            while rest:
                part = cut_tokens(rest, size) or rest[: max(1, len(rest) // 2)]
                pieces.append((count_tokens(part), [part]))
                rest = rest[len(part) :]
            continue
        if tokens + n > size and lines:
            pieces.append((tokens, lines))
            tokens, lines = 0, []
        tokens += n
        lines.append(line)
    if lines or not pieces:
        pieces.append((tokens, lines))
    if len(pieces) > 1 and pieces[-1][0] < size // 4:
        tail_tokens, tail_lines = pieces.pop()
        head_tokens, head_lines = pieces.pop()
        pieces.append((head_tokens + tail_tokens, head_lines + tail_lines))
    out: list[Segment] = []
    start = 0
    for n, ls in pieces:
        out.append(Segment(start, start + n, "\n".join(ls)))
        start += n
    return out


def answer_budget(context: int) -> int:
    """Document tokens that fit a request in a model loaded with `context`."""
    return max(1, context - PROMPT_RESERVE)


QUOTE_WORDS_FOUND = 0.8
TOKEN = re.compile(r"[a-z0-9]+")
"""Any alphanumeric run: an answer's numbers ("8", "92") must be in the text layer too."""
"""Share of a quote's words (3+ alphanumerics) that must occur in the text layer for the pair to be kept."""


def grounded(quote: str, answer: str, text_words: set[str], haystack: str) -> bool:
    """Whether a question is backed by the text layer: every word and number of the answer occurs in it, and
    its quote occurs verbatim (whitespace and case folded) or at least QUOTE_WORDS_FOUND of the quote's words do.
    Models rarely copy a sentence byte for byte across a PDF's hyphenation and line breaks; the word test keeps
    such quotes while still throwing out invented facts."""
    awords = TOKEN.findall(norm(answer))
    if not all(w in text_words for w in awords):
        return False
    if norm(quote) in haystack:
        return True
    qwords = WORD.findall(norm(quote))
    if not qwords:
        return False
    return sum(1 for w in qwords if w in text_words) / len(qwords) >= QUOTE_WORDS_FOUND


def validate_questions(raw: list[Any], text: str, limit: int = QUESTIONS_KEPT) -> list[dict[str, str]]:
    """Keep pairs that are grounded in `text` (see `grounded`), at most `limit`."""
    haystack = norm(text)
    text_words = set(TOKEN.findall(haystack))
    kept: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        q, a, quote = (str(item.get(k, "")).strip() for k in ("question", "answer", "quote"))
        if not (q and a and quote) or len(a.split()) > 16:
            continue
        if not grounded(quote, a, text_words, haystack):
            continue
        kept.append({"question": q, "answer": a, "quote": quote})
        if len(kept) == limit:
            break
    return kept


def qa_dir() -> Path:
    return arxiv_root() / "qa"


def _docs(run_dir: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))["documents"]
    return docs


def cached_questions(path: Path) -> int | None:
    """How many questions a cached file holds when it was written under the current scheme and has at least
    one question per segment on average; None when it must be generated again."""
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    have = len(record.get("questions", []))
    if record.get("scheme") != SCHEME or have < int(record.get("segments", 1)):
        return None
    return have


def generate_questions(client: Client, text: str) -> tuple[list[dict[str, Any]], int]:
    """Questions for one paper, QUESTIONS_KEPT per SEGMENT_TOKENS-token segment of its text, each recording
    where its evidence lies. Returns (questions, number of segments)."""
    segs = segments(text, SEGMENT_TOKENS)
    total = segs[-1].end
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(segs):
        kept: list[dict[str, str]] = []
        for _attempt in range(2):
            prompt = GENERATE_PROMPT.format(n=QUESTIONS_WANTED, part=i + 1, parts=len(segs), text=seg.text)
            try:
                kept = validate_questions(parse_json_array(client.chat(prompt, max_tokens=2000)), seg.text)
            except (ValueError, json.JSONDecodeError) as exc:
                _note(exc)
                continue
            if kept:
                break
        out.extend({**q, "segment": seg.where(total)} for q in kept)
    return out, len(segs)


def generate(client: Client, run_dir: Path, workers: int) -> int:
    docs = _docs(run_dir)
    qa_dir().mkdir(parents=True, exist_ok=True)

    def one(doc: dict[str, Any]) -> str:
        path = qa_dir() / f"{doc['id']}.json"
        have = cached_questions(path)
        if have is not None:
            return f"{doc['id']}: cached ({have} questions)"
        questions, parts = generate_questions(client, witness(doc["id"], Path(doc["input"])).text)
        record = {
            "model": client.model,
            "server": client.base_url,
            "scheme": SCHEME,
            "doc": doc["id"],
            "segments": parts,
            "questions": questions,
        }
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        return f"{doc['id']}: {len(questions)} questions over {parts} segments"

    with ThreadPoolExecutor(workers) as pool:
        for line in pool.map(one, docs):
            print(line, flush=True)
    return 0


def _questions(doc_id: str) -> list[dict[str, Any]]:
    path = qa_dir() / f"{doc_id}.json"
    if not path.exists():
        return []
    items: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["questions"]
    return items


RUN_CAP = 32
"""A run of one non-ASCII character longer than this is squeezed to this many before the text is sent: the
server's tokenizer failed ("Failed to process regex", HTTP 400) on a 764-character run of one CJK character that
MinerU read off a table's rules. Such a run carries nothing a question could ask about."""

_LONG_RUN = re.compile(rf"([^\x00-\x7f])\1{{{RUN_CAP},}}")


def squeeze_runs(text: str) -> str:
    return _LONG_RUN.sub(lambda m: m.group(1) * RUN_CAP, text)


def document_text(md: str, context: int) -> tuple[str, bool]:
    """The output as the model sees it: whole when it fits the context, else cut. Returns (text, cut)."""
    md = squeeze_runs(md)
    budget = answer_budget(context)
    if count_tokens(md) <= budget:
        return md, False
    return cut_tokens(md, budget), True


def answer(client: Client, run_dir: Path, tools: list[str] | None, workers: int, context: int = CONTEXT_TOKENS) -> int:
    results = [r for r in read_results(run_dir / "results.jsonl") if tools is None or r.tool in tools]
    results = [r for r in results if r.status != "unsupported"]

    def one(r: DocResult) -> str:
        path = run_dir / "qa" / r.tool / f"{r.doc_id}.json"
        if path.exists() and all("answer" in it for it in json.loads(path.read_text(encoding="utf-8"))["items"]):
            return f"{r.tool} {r.doc_id}: cached"
        questions = _questions(r.doc_id)
        if not questions:
            return f"{r.tool} {r.doc_id}: no questions"
        md = strip_data_uris(read_output(r, run_dir))
        answers: list[str]
        cut = False
        if r.status != "ok" or not md.strip():
            answers = [UNKNOWN] * len(questions)
        else:
            # Like the verdicts, answers are cached by the exact text the model saw: a sampled model answers the
            # same text differently on another day, and a tool whose output did not change between two runs
            # must score the same in both.
            text, cut = document_text(md, context)
            hit = cached_answers(r.doc_id, questions, text)
            if hit is not None:
                answers = hit
            else:
                listed = "\n".join(f"{i + 1}. {q['question']}" for i, q in enumerate(questions))
                prompt = ANSWER_PROMPT.format(unknown=UNKNOWN, questions=listed, text=text)
                answers = []
                for _attempt in range(2):
                    try:
                        got = parse_json_array(client.chat(prompt, max_tokens=3000))
                    except (ValueError, json.JSONDecodeError) as exc:
                        _note(exc)
                        continue
                    except urllib.error.HTTPError as exc:
                        if exc.code != 400:
                            raise
                        # The server refused this text (its tokenizer, not the context): this document fails
                        # for this tool and the pass goes on; a server that stopped answering is an OSError.
                        reason = exc.read().decode("utf-8", "replace")[:120]
                        return f"{r.tool} {r.doc_id}: FAILED, the server refused the text ({reason})"
                    answers = [str(a) if a is not None else UNKNOWN for a in got][: len(questions)]
                    if len(answers) == len(questions):
                        break
                if len(answers) != len(questions):
                    # Not written: a padded record would be cached as answered and graded as wrong.
                    return f"{r.tool} {r.doc_id}: FAILED, the model returned {len(answers)} of {len(questions)} answers"
                store_answers(r.doc_id, questions, text, answers, client.model)
        items = [{**q, "answer_given": a} for q, a in zip(questions, answers, strict=True)]
        record = {
            "model": client.model,
            "server": client.base_url,
            "tool": r.tool,
            "doc": r.doc_id,
            "context": context,
            "cut": cut,
            "items": items,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        note = " (output cut to fit the context)" if cut else ""
        return f"{r.tool} {r.doc_id}: {sum(a != UNKNOWN for a in answers)}/{len(answers)} answered{note}"

    with ThreadPoolExecutor(workers) as pool:
        for line in pool.map(one, results):
            print(line, flush=True)
    return 0


def answer_cache_dir() -> Path:
    return qa_dir() / "answers"


def _answer_key(doc_id: str, questions: list[dict[str, str]], text: str) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(doc_id.encode("utf-8"))
    for q in questions:
        h.update(b"\n")
        h.update(" ".join(q["question"].split()).encode("utf-8"))
    h.update(b"\n\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:32]


def cached_answers(doc_id: str, questions: list[dict[str, str]], text: str) -> list[str] | None:
    path = answer_cache_dir() / f"{_answer_key(doc_id, questions, text)}.json"
    if not path.exists():
        return None
    answers = json.loads(path.read_text(encoding="utf-8"))["answers"]
    return [str(a) for a in answers] if len(answers) == len(questions) else None


def store_answers(doc_id: str, questions: list[dict[str, str]], text: str, answers: list[str], model: str) -> None:
    path = answer_cache_dir() / f"{_answer_key(doc_id, questions, text)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"doc": doc_id, "model": model, "answers": answers}
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8", newline="\n")


def seed_answers(run_dir: Path, tools: list[str] | None, context: int = CONTEXT_TOKENS) -> int:
    """Put the answers of an already answered run into the cache (keyed by the text the model saw), where no
    answer for that text exists yet. Returns the number of documents added."""
    added = 0
    for r in read_results(run_dir / "results.jsonl"):
        if (tools is not None and r.tool not in tools) or r.status != "ok":
            continue
        path = run_dir / "qa" / r.tool / f"{r.doc_id}.json"
        if not path.exists():
            continue
        items = json.loads(path.read_text(encoding="utf-8"))["items"]
        if not items or not all("answer_given" in it for it in items):
            continue
        questions = _questions(r.doc_id)
        if [q["question"] for q in questions] != [it["question"] for it in items]:
            continue
        md = strip_data_uris(read_output(r, run_dir))
        if not md.strip():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        text, _cut = document_text(md, int(record.get("context", context)))
        if cached_answers(r.doc_id, questions, text) is None:
            store_answers(r.doc_id, questions, text, [str(it["answer_given"]) for it in items], "seeded")
            added += 1
    print(f"answer cache: {added} documents added from {run_dir}")
    return added


def grade_cache_dir() -> Path:
    return qa_dir() / "grades"


def _grade_key(doc_id: str, question: str, answer_given: str) -> str:
    import hashlib

    text = "\n".join([doc_id, " ".join(question.split()), " ".join(answer_given.split()).casefold()])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def cached_grade(doc_id: str, question: str, answer_given: str) -> bool | None:
    path = grade_cache_dir() / f"{_grade_key(doc_id, question, answer_given)}.json"
    if not path.exists():
        return None
    return bool(json.loads(path.read_text(encoding="utf-8"))["correct"])


def store_grade(doc_id: str, question: str, answer_given: str, correct: bool, grader: str) -> None:
    path = grade_cache_dir() / f"{_grade_key(doc_id, question, answer_given)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"doc": doc_id, "question": question, "answer_given": answer_given, "correct": correct, "grader": grader}
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8", newline="\n")


def seed_grades(run_dir: Path, tools: list[str] | None) -> int:
    """Put the verdicts of an already graded run into the cache (where no verdict for that answer exists yet),
    so later runs grade an identical answer identically. Returns the number of verdicts added."""
    added = 0
    files = sorted((run_dir / "qa").glob("*/*.json")) if (run_dir / "qa").exists() else []
    for path in files:
        if tools is not None and path.parent.name not in tools:
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        for it in record["items"]:
            if "correct" not in it or "answer_given" not in it:
                continue
            if it["answer_given"].strip() in ("", UNKNOWN):
                continue  # the shortcut, never the model's verdict
            if cached_grade(record["doc"], it["question"], it["answer_given"]) is None:
                store_grade(
                    record["doc"],
                    it["question"],
                    it["answer_given"],
                    bool(it["correct"]),
                    str(record.get("grader", "")),
                )
                added += 1
    print(f"grade cache: {added} verdicts added from {run_dir}")
    return added


def ungrade(run_dir: Path, tools: list[str] | None) -> int:
    """Remove the verdicts of a run so `grade` decides again (from the cache where it can)."""
    n = 0
    files = sorted((run_dir / "qa").glob("*/*.json")) if (run_dir / "qa").exists() else []
    for path in files:
        if tools is not None and path.parent.name not in tools:
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for it in record["items"]:
            if it.pop("correct", None) is not None:
                changed = True
                n += 1
        record.pop("grader", None)
        if changed:
            path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"ungraded {n} answers under {run_dir}")
    return n


def grade(client: Client, run_dir: Path, tools: list[str] | None, workers: int) -> int:
    files = sorted((run_dir / "qa").glob("*/*.json")) if (run_dir / "qa").exists() else []
    if tools is not None:
        files = [f for f in files if f.parent.name in tools]

    def one(path: Path) -> str:
        record = json.loads(path.read_text(encoding="utf-8"))
        items = record["items"]
        if all("correct" in it for it in items):
            return f"{record['tool']} {record['doc']}: cached"
        pending = [it for it in items if "answer_given" in it]
        verdicts: list[bool] = []
        shortcut = [it["answer_given"].strip() == UNKNOWN or not it["answer_given"].strip() for it in pending]
        to_grade = [it for it, s in zip(pending, shortcut, strict=True) if not s]
        # The grader is a sampled model: the same answer can get a different verdict on another day, which
        # would show up as a change in accuracy between two runs that produced identical answers. So a verdict
        # is cached by (document, question, answer) under the corpus and reused by every run and tool.
        cached: dict[int, bool] = {}
        for i, it in enumerate(to_grade):
            hit = cached_grade(record["doc"], it["question"], it["answer_given"])
            if hit is not None:
                cached[i] = hit
        fresh = [it for i, it in enumerate(to_grade) if i not in cached]
        graded: list[bool] = []
        if fresh:
            listed = "\n".join(
                f"{i + 1}. question: {it['question']}\n   reference: {it['answer']}\n   candidate: {it['answer_given']}"
                for i, it in enumerate(fresh)
            )
            prompt = GRADE_PROMPT.format(unknown=UNKNOWN, items=listed)
            for _attempt in range(2):
                try:
                    got = parse_json_array(client.chat(prompt, max_tokens=2000))
                except (ValueError, json.JSONDecodeError) as exc:
                    _note(exc)
                    continue
                graded = [bool(v) for v in got][: len(fresh)]
                if len(graded) == len(fresh):
                    break
            if len(graded) != len(fresh):
                # Left ungraded so the next run retries it; a padded False would hide the failure in the score.
                return f"{record['tool']} {record['doc']}: FAILED, the grader returned {len(graded)} of {len(fresh)}"
            for it, v in zip(fresh, graded, strict=True):
                store_grade(record["doc"], it["question"], it["answer_given"], v, client.model)
        it_fresh = iter(graded)
        merged = [cached[i] if i in cached else next(it_fresh) for i in range(len(to_grade))]
        it_graded = iter(merged)
        verdicts = [False if s else next(it_graded) for s in shortcut]
        for it, v in zip(pending, verdicts, strict=True):
            it["correct"] = v
        record["grader"] = client.model
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        return f"{record['tool']} {record['doc']}: {sum(verdicts)}/{len(verdicts)} correct"

    with ThreadPoolExecutor(workers) as pool:
        for line in pool.map(one, files):
            print(line, flush=True)
    return 0


def _lms() -> str | None:
    found = shutil.which("lms")
    if found:
        return found
    local = Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms")
    return str(local) if local.exists() else None


def loaded_context(lms: str, model: str) -> int | None:
    """Context length the model is loaded with in LM Studio (`lms ps --json`), None when it is not loaded."""
    out = subprocess.run([lms, "ps", "--json"], capture_output=True, text=True, check=False)
    try:
        rows = json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return None
    for row in rows:
        if row.get("identifier") == model or row.get("modelKey") == model:
            return int(row.get("contextLength") or 0)
    return None


def ensure_model(client: Client, workers: int, context: int = CONTEXT_TOKENS) -> None:
    """Have LM Studio serve the model with at least `context` tokens of context per worker. `/v1/models` lists
    every model on disk, loaded or not, and a request to an unloaded one makes LM Studio load it with its
    default 4k context, which this pipeline's prompts overflow; so the loaded context is checked with `lms ps`
    and the model is reloaded when it is missing or too small."""
    lms = _lms()
    if lms is None:
        try:
            if client.model in client.models():
                print(f"qa: lms not installed; trusting {client.base_url} to serve {client.model}", flush=True)
                return
        except (urllib.error.URLError, OSError):
            pass
        raise SystemExit(f"{client.base_url} is not serving {client.model} and lms is not installed to load it")
    subprocess.run([lms, "server", "start"], check=False, capture_output=True)
    needed = context * workers
    have = loaded_context(lms, client.model)
    if have is not None and have >= needed:
        return
    if have is not None:
        subprocess.run([lms, "unload", client.model], check=False, capture_output=True)
    subprocess.run(
        [
            lms,
            "load",
            client.model,
            "--gpu",
            "max",
            "--context-length",
            str(needed),
            "--parallel",
            str(workers),
            "--ttl",
            str(MODEL_TTL_SECONDS),
            "--identifier",
            client.model,
            "-y",
        ],
        check=True,
    )
    have = loaded_context(lms, client.model)
    if have is None or have < needed:
        raise SystemExit(f"{client.model} did not come up with a {needed}-token context (got {have})")


def main(
    step: str,
    corpus: str,
    run_dir: Path,
    tools: list[str] | None,
    *,
    model: str | None,
    base_url: str | None,
    workers: int,
    context: int = CONTEXT_TOKENS,
) -> int:
    if corpus != "arxiv":
        print(f"qa: no witness text for corpus {corpus}", file=sys.stderr)
        return 2
    if not (run_dir / "docs.json").exists():
        print(f"qa: no run under {run_dir} (run the corpus first)", file=sys.stderr)
        return 1
    if step == "seed":  # no model needed
        seed_answers(run_dir, tools, context)
        seed_grades(run_dir, tools)
        return 0
    if step == "ungrade":
        ungrade(run_dir, tools)
        return 0
    client = Client(
        base_url or os.environ.get("EZMD_BENCH_LLM_URL", DEFAULT_URL),
        model or os.environ.get("EZMD_BENCH_LLM_MODEL", DEFAULT_MODEL),
    )
    ensure_model(client, workers, context)
    steps = ("generate", "answer", "grade") if step == "all" else (step,)
    rc = 0
    try:
        for s in steps:
            if s == "generate":
                rc = rc or generate(client, run_dir, workers)
            elif s == "answer":
                rc = rc or answer(client, run_dir, tools, workers, context)
            else:
                rc = rc or grade(client, run_dir, tools, workers)
    except OSError as exc:  # the server stopped answering (a timeout is an OSError): stop, the caches resume
        print(f"qa: {client.base_url} stopped answering ({exc}); nothing partial was written, rerun to resume")
        return 1
    return rc
