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

Questions are cached per document under the corpus (`corpora/arxiv/qa/<doc>.json`) and shared by every tool and
run. Answers and grades go to `<run_dir>/qa/<tool>/<doc>.json`, which tools/bench/scoring/arxiv.py reads.

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
from pathlib import Path
from typing import Any

from tools.bench.corpora import arxiv_root
from tools.bench.schema import DocResult, read_results
from tools.bench.scoring.arxiv import WORD, count_tokens, norm, strip_data_uris, witness
from tools.bench.scoring.text import read_output

DEFAULT_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "openai/gpt-oss-20b"
CONTEXT_TOKENS = 32_768
"""Context each request needs; the document is cut to DOC_TOKENS so prompt and answer fit. llama.cpp shares
one KV cache between parallel requests, so the model is loaded with CONTEXT_TOKENS times the worker count."""
DOC_TOKENS = 24_000
MODEL_TTL_SECONDS = 4 * 3600
"""LM Studio unloads the model after this long idle; a run keeps it busy, the next morning does not."""
QUESTIONS_WANTED = 6
QUESTIONS_KEPT = 5
MIN_QUESTIONS = 3
"""A paper with fewer valid questions than this is generated again on the next run."""
SEED = 20261013
UNKNOWN = "UNKNOWN"

GENERATE_PROMPT = """You are writing a reading-comprehension test for a scientific paper. Below is the paper's text.

Write {n} question/answer pairs that check whether a reader has the paper's content. Rules:
- Each answer is a specific fact stated explicitly in the text: a number with its unit, a name, a term, a short
  phrase. Answers are at most 12 words.
- Spread the questions over the whole paper: at most one from the abstract, at least two from the second half,
  and at least one about a numeric result. If the paper has a table, ask one question whose answer is a value
  in it.
- Do not ask about figures, images or anything that needs a picture to answer. Do not ask about the authors,
  the venue or the date.
- Each pair carries a "quote": the exact sentence or table row from the text that contains the answer, copied
  verbatim.

Reply with a JSON array only, no prose: [{{"question": "...", "answer": "...", "quote": "..."}}, ...]

PAPER TEXT:
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
_BAD_ESCAPE = re.compile(r"\\(?![\\\"/bfnrtu])")


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
        value = json.loads(_BAD_ESCAPE.sub(r"\\\\", body))
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


def validate_questions(raw: list[Any], text: str) -> list[dict[str, str]]:
    """Keep pairs that are grounded in the text layer (see `grounded`), at most QUESTIONS_KEPT."""
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
        if len(kept) == QUESTIONS_KEPT:
            break
    return kept


def qa_dir() -> Path:
    return arxiv_root() / "qa"


def _docs(run_dir: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))["documents"]
    return docs


def generate(client: Client, run_dir: Path, workers: int) -> int:
    docs = _docs(run_dir)
    qa_dir().mkdir(parents=True, exist_ok=True)

    def one(doc: dict[str, Any]) -> str:
        path = qa_dir() / f"{doc['id']}.json"
        if path.exists():
            have = len(json.loads(path.read_text(encoding="utf-8"))["questions"])
            if have >= MIN_QUESTIONS:
                return f"{doc['id']}: cached ({have} questions)"
        text = cut_tokens(witness(doc["id"], Path(doc["input"])).text, DOC_TOKENS)
        kept: list[dict[str, str]] = []
        for _attempt in range(2):
            reply = client.chat(GENERATE_PROMPT.format(n=QUESTIONS_WANTED, text=text), max_tokens=4000)
            try:
                kept = validate_questions(parse_json_array(reply), text)
            except (ValueError, json.JSONDecodeError) as exc:
                _note(exc)
                continue
            if len(kept) >= MIN_QUESTIONS:
                break
        record = {"model": client.model, "server": client.base_url, "doc": doc["id"], "questions": kept}
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        return f"{doc['id']}: {len(kept)} questions"

    with ThreadPoolExecutor(workers) as pool:
        for line in pool.map(one, docs):
            print(line, flush=True)
    return 0


def _questions(doc_id: str) -> list[dict[str, str]]:
    path = qa_dir() / f"{doc_id}.json"
    if not path.exists():
        return []
    items: list[dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))["questions"]
    return items


def answer(client: Client, run_dir: Path, tools: list[str] | None, workers: int) -> int:
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
        if r.status != "ok" or not md.strip():
            answers = [UNKNOWN] * len(questions)
        else:
            listed = "\n".join(f"{i + 1}. {q['question']}" for i, q in enumerate(questions))
            prompt = ANSWER_PROMPT.format(unknown=UNKNOWN, questions=listed, text=cut_tokens(md, DOC_TOKENS))
            answers = []
            for _attempt in range(2):
                try:
                    got = parse_json_array(client.chat(prompt, max_tokens=3000))
                except (ValueError, json.JSONDecodeError) as exc:
                    _note(exc)
                    continue
                answers = [str(a) if a is not None else UNKNOWN for a in got][: len(questions)]
                if len(answers) == len(questions):
                    break
            if len(answers) != len(questions):
                # Not written: a padded record would be cached as answered and graded as wrong.
                return f"{r.tool} {r.doc_id}: FAILED, the model returned {len(answers)} of {len(questions)} answers"
        items = [{**q, "answer_given": a} for q, a in zip(questions, answers, strict=True)]
        record = {"model": client.model, "server": client.base_url, "tool": r.tool, "doc": r.doc_id, "items": items}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        return f"{r.tool} {r.doc_id}: {sum(a != UNKNOWN for a in answers)}/{len(answers)} answered"

    with ThreadPoolExecutor(workers) as pool:
        for line in pool.map(one, results):
            print(line, flush=True)
    return 0


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


def ensure_model(client: Client, workers: int) -> None:
    """Have LM Studio serve the model with at least CONTEXT_TOKENS of context. `/v1/models` lists every model on
    disk, loaded or not, and a request to an unloaded one makes LM Studio load it with its default 4k context,
    which this pipeline's prompts overflow; so the loaded context is checked with `lms ps` and the model is
    reloaded when it is missing or too small."""
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
    needed = CONTEXT_TOKENS * workers
    context = loaded_context(lms, client.model)
    if context is not None and context >= needed:
        return
    if context is not None:
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
    context = loaded_context(lms, client.model)
    if context is None or context < needed:
        raise SystemExit(f"{client.model} did not come up with a {needed}-token context (got {context})")


def main(
    step: str,
    corpus: str,
    run_dir: Path,
    tools: list[str] | None,
    *,
    model: str | None,
    base_url: str | None,
    workers: int,
) -> int:
    if corpus != "arxiv":
        print(f"qa: no witness text for corpus {corpus}", file=sys.stderr)
        return 2
    if not (run_dir / "docs.json").exists():
        print(f"qa: no run under {run_dir} (run the corpus first)", file=sys.stderr)
        return 1
    if step == "seed":  # no model needed
        seed_grades(run_dir, tools)
        return 0
    if step == "ungrade":
        ungrade(run_dir, tools)
        return 0
    client = Client(
        base_url or os.environ.get("EZMD_BENCH_LLM_URL", DEFAULT_URL),
        model or os.environ.get("EZMD_BENCH_LLM_MODEL", DEFAULT_MODEL),
    )
    ensure_model(client, workers)
    steps = ("generate", "answer", "grade") if step == "all" else (step,)
    rc = 0
    for s in steps:
        if s == "generate":
            rc = rc or generate(client, run_dir, workers)
        elif s == "answer":
            rc = rc or answer(client, run_dir, tools, workers)
        else:
            rc = rc or grade(client, run_dir, tools, workers)
    return rc
