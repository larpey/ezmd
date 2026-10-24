"""`python -m tools.bench <command>`.

install  [--tools a,b] [--force]          create competitor environments under the cache directory
run      --corpus NAME [--tools a,b] [--sample N | --split heldout] [--timeout S] [--date YYYY-MM-DD]
score    --corpus NAME [--date ...]       score raw outputs (per-document scores.jsonl)
report   [--date ...]                     aggregate into bench/results/<date>/results.json + summary.md
qa       generate|answer|grade|all --corpus NAME [--date ...] [--tools a,b]   local-model QA (tools/bench/qa.py)
smoke                                     run + score + report on the smoke corpus with every tool
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from tools.bench.config import cache_dir, load_tools


def _names(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


def run_dir(date: str, corpus: str) -> Path:
    return cache_dir() / "runs" / date / corpus


def cmd_run(
    corpus: str, tools: list[str] | None, sample: int | None, timeout: float, date: str, split: str = "sample"
) -> int:
    from tools.bench.corpora import CORPORA, heldout
    from tools.bench.install import binary_path
    from tools.bench.runner import run_tool

    all_tools = load_tools()
    names = tools or list(all_tools)
    unknown = [n for n in names if n not in all_tools]
    if unknown:
        print(f"unknown tools: {unknown}", file=sys.stderr)
        return 2
    if split == "heldout":
        if sample is not None:
            print("--sample and --split heldout are exclusive", file=sys.stderr)
            return 2
        docs = heldout(corpus)
    else:
        docs = CORPORA[corpus](sample) if sample is not None else CORPORA[corpus]()  # type: ignore[call-arg]
    out = run_dir(date, corpus)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "corpus": corpus,
        "sample": sample,
        "split": split,
        "documents": [{"id": d.id, "category": d.category, "input": str(d.input), **d.meta} for d in docs],
    }
    existing = out / "docs.json"
    if existing.exists():
        # results.jsonl is append-only and the scorers read this manifest, so one run directory holds one
        # document set; another sample or split needs another --date.
        old = {d["id"] for d in json.loads(existing.read_text(encoding="utf-8"))["documents"]}
        if old != {d.id for d in docs}:
            print(f"{out} already holds a run over a different document set; use another --date", file=sys.stderr)
            return 2
    existing.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    print(f"{corpus}: {len(docs)} documents -> {out}")
    for name in names:
        tool = all_tools[name]
        pandoc = binary_path(tool) if tool.kind == "binary" else None
        counts: dict[str, int] = {}
        for r in run_tool(tool, docs, out, timeout=timeout, pandoc=pandoc):
            counts[r.status] = counts.get(r.status, 0) + 1
            if r.status in ("error", "timeout", "crash"):
                print(f"  {name} {r.doc_id}: {r.status} {r.error_class}: {(r.error or '')[:160]}", flush=True)
        print(f"{name}: {counts}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("install", help="create competitor environments")
    p.add_argument("--tools")
    p.add_argument("--force", action="store_true")
    today = dt.date.today().isoformat()
    for name in ("run", "score"):
        p = sub.add_parser(name)
        p.add_argument("--corpus", required=True)
        p.add_argument("--tools")
        p.add_argument("--date", default=today)
        if name == "run":
            p.add_argument("--sample", type=int, default=None)
            p.add_argument("--timeout", type=float, default=300.0)
            p.add_argument("--split", choices=("sample", "heldout"), default="sample")
    p = sub.add_parser("fetch", help="download corpora and set up the official scorers")
    p.add_argument("--only")
    p = sub.add_parser("compare", help="ezmd before/after on the same documents")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--rivals", default="pymupdf4llm,unstructured")
    p = sub.add_parser("report")
    p.add_argument("--date", default=today)
    p = sub.add_parser("smoke")
    p.add_argument("--date", default=today)
    p.add_argument("--tools")
    p = sub.add_parser("qa", help="question answering over converted documents with a local model")
    p.add_argument("step", choices=("generate", "answer", "grade", "all"))
    p.add_argument("--corpus", required=True)
    p.add_argument("--tools")
    p.add_argument("--date", default=today)
    p.add_argument("--model", default=None, help="model id on the local OpenAI-compatible server")
    p.add_argument("--base-url", default=None, help="default http://localhost:1234/v1 (LM Studio)")
    p.add_argument(
        "--workers", type=int, default=1, help="parallel requests; the model is loaded with 32k context each"
    )
    p = sub.add_parser("tokens", help="exact Claude token counts of each output (Anthropic count_tokens, free)")
    p.add_argument("--corpus", required=True)
    p.add_argument("--tools")
    p.add_argument("--date", default=today)
    p.add_argument("--model", default=None, help="model whose tokenizer counts; default claude-sonnet-5-5")
    args = ap.parse_args(argv)
    if args.cmd == "tokens":
        from tools.bench.tokens import main as tokens

        return tokens(run_dir(args.date, args.corpus), _names(args.tools), model=args.model)
    if args.cmd == "install":
        from tools.bench.install import main as install

        return install(_names(args.tools), force=args.force)
    if args.cmd == "compare":
        from tools.bench.compare import main as compare

        return compare(args.before, args.after, _names(args.rivals) or [])
    if args.cmd == "fetch":
        from tools.bench.fetch import main as fetch

        return fetch(_names(args.only))
    if args.cmd == "run":
        return cmd_run(args.corpus, _names(args.tools), args.sample, args.timeout, args.date, args.split)
    if args.cmd == "score":
        from tools.bench.scoring import score_corpus

        return score_corpus(args.corpus, run_dir(args.date, args.corpus), _names(args.tools))
    if args.cmd == "report":
        from tools.bench.report import write_report

        return write_report(args.date)
    if args.cmd == "qa":
        from tools.bench.qa import main as qa

        return qa(
            args.step,
            args.corpus,
            run_dir(args.date, args.corpus),
            _names(args.tools),
            model=args.model,
            base_url=args.base_url,
            workers=args.workers,
        )
    if args.cmd == "smoke":
        from tools.bench.report import write_report
        from tools.bench.scoring import score_corpus

        rc = cmd_run("smoke", _names(args.tools), None, 300.0, args.date)
        rc = rc or score_corpus("smoke", run_dir(args.date, "smoke"), _names(args.tools))
        return rc or write_report(args.date)
    return 2
