"""Runs inside the olmOCR scoring venv (olmocr[bench]); stdlib + olmocr only.

    <score-olmocr python> -I olmocr_eval.py --bench DIR --candidates DIR --out FILE

Loads every `<bench>/*.jsonl` with olmocr's own `load_tests`, adds olmocr's `BaselineTest` for each PDF exactly as
olmocr.bench.benchmark does, and runs each test's official `run()` against `<candidates>/<tool>/<pdf stem>.md`.
Writes one JSON line per (tool, test): {"tool", "test", "jsonl", "pdf", "type", "passed"}. A missing Markdown
file is an empty output (the test runs on ""), matching a failed conversion.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olmocr.bench.tests import BaselineTest, load_tests


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, type=Path)
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    tests = []
    for jsonl in sorted(args.bench.glob("*.jsonl")):
        for t in load_tests(str(jsonl)):
            tests.append((jsonl.name, t))
    pdfs = sorted({t.pdf for _, t in tests})
    for pdf in pdfs:
        if not any(t.type == "baseline" and t.pdf == pdf for _, t in tests):
            tests.append(("baseline", BaselineTest(id=f"{pdf}_baseline", pdf=pdf, page=1, type="baseline")))
    with args.out.open("w", encoding="utf-8") as out:
        for tool_dir in sorted(p for p in args.candidates.iterdir() if p.is_dir()):
            cache: dict[str, str] = {}
            for jsonl, t in tests:
                if t.pdf not in cache:
                    md = tool_dir / (t.pdf.removesuffix(".pdf") + ".md")
                    cache[t.pdf] = md.read_text(encoding="utf-8") if md.exists() else ""
                try:
                    passed, _ = t.run(cache[t.pdf])
                except Exception:
                    passed = False
                rec = {"tool": tool_dir.name, "test": t.id, "jsonl": jsonl, "pdf": t.pdf, "type": str(t.type)}
                out.write(json.dumps({**rec, "passed": bool(passed)}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
