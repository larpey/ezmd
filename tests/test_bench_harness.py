"""The competitive benchmark harness's own logic (tools/bench); runs without any competitor installed."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench.config import Tool  # noqa: E402
from tools.bench.runner import Launch, parse_mem_usage, run_tool  # noqa: E402
from tools.bench.schema import Doc, DocResult, append_result, read_results  # noqa: E402
from tools.bench.scoring.text import markdown_to_text, strip_frontmatter  # noqa: E402
from tools.bench.stats import bootstrap_ci, paired_diff_ci, percentile  # noqa: E402
from tools.bench.warmup import _pdf_bytes  # noqa: E402

FAKE_WORKER = textwrap.dedent(
    """
    import json, os, sys, time
    print(json.dumps({"ready": True, "version": "9.9", "startup_seconds": 0.0}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        name = os.path.basename(job["input"])
        if name.startswith("slow"):
            time.sleep(60)
        if name.startswith("crash"):
            os._exit(3)
        if name.startswith("bad"):
            print(json.dumps({"id": job["id"], "ok": False, "error_class": "ValueError", "error": "nope"}), flush=True)
            continue
        os.makedirs(os.path.dirname(job["output"]), exist_ok=True)
        with open(job["output"], "w", encoding="utf-8") as fh:
            fh.write("# out")
        print(json.dumps({"id": job["id"], "ok": True, "chars": 5}), flush=True)
    """
)


def _tool() -> Tool:
    return Tool(name="fake", kind="venv", adapter="fake", formats=("txt",), license="MIT")


def test_doc_result_schema_round_trip(tmp_path: Path) -> None:
    r = DocResult("c", "d1", "cat", "t", "1.0", "ok", seconds=0.5, peak_rss_mb=10.0, output="t/d1.md", chars=3)
    path = tmp_path / "results.jsonl"
    append_result(path, r)
    assert read_results(path) == [r]
    with pytest.raises(ValueError, match="unknown status"):
        DocResult("c", "d", "cat", "t", "1", "weird")
    with pytest.raises(ValueError, match="output path"):
        DocResult("c", "d", "cat", "t", "1", "ok")
    with pytest.raises(ValueError, match="unknown DocResult fields"):
        DocResult.from_dict({**json.loads(r.to_json()), "extra": 1})
    assert DocResult("c", "d", "cat", "t", "1", "timeout").failed
    assert not DocResult("c", "d", "cat", "t", "1", "unsupported").failed


def test_percentile_matches_linear_interpolation() -> None:
    xs = [1.0, 2.0, 3.0, 4.0]
    assert percentile(xs, 50) == 2.5
    assert percentile(xs, 0) == 1.0
    assert percentile(xs, 100) == 4.0
    assert percentile(xs, 95) == pytest.approx(3.85)
    with pytest.raises(ValueError):
        percentile([], 50)


def test_bootstrap_ci_brackets_the_mean_and_is_deterministic() -> None:
    values = [0.0, 1.0] * 50
    lo, hi = bootstrap_ci(values)
    assert lo < 0.5 < hi
    assert (lo, hi) == bootstrap_ci(values)
    assert bootstrap_ci([0.7]) == (0.7, 0.7)
    assert bootstrap_ci([0.3] * 10) == (pytest.approx(0.3), pytest.approx(0.3))


def test_paired_diff_detects_a_consistent_gap() -> None:
    a = [0.9, 0.8, 0.95, 0.85] * 10
    b = [x - 0.1 for x in a]
    diff, (lo, hi) = paired_diff_ci(a, b)
    assert diff == pytest.approx(0.1)
    assert lo > 0 and hi > 0
    with pytest.raises(ValueError):
        paired_diff_ci([1.0], [1.0, 2.0])


def test_run_tool_records_ok_error_timeout_crash_and_unsupported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_BENCH_CACHE", str(tmp_path / "cache"))  # a fresh machine has no cache yet
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER, encoding="utf-8")
    inputs = {}
    for name in ("good.txt", "bad.txt", "slow.txt", "crash.txt", "after.txt", "skip.pdf"):
        inputs[name] = tmp_path / name
        inputs[name].write_text("x", encoding="utf-8")
    docs = [Doc("c", Path(n).stem, p, "cat") for n, p in inputs.items()]
    run_dir = tmp_path / "run"
    launch = Launch([sys.executable, "-I", str(script)])
    results = {r.doc_id: r for r in run_tool(_tool(), docs, run_dir, timeout=2.0, launch=launch)}
    assert results["good"].status == "ok" and results["good"].tool_version == "9.9"
    assert (run_dir / results["good"].output).read_text(encoding="utf-8") == "# out"  # type: ignore[operator]
    assert results["bad"].status == "error" and results["bad"].error_class == "ValueError"
    assert results["slow"].status == "timeout" and results["slow"].seconds is not None
    assert results["crash"].status == "crash"
    # A fresh worker takes over after the timeout and the crash.
    assert results["after"].status == "ok"
    assert results["skip"].status == "unsupported"
    assert results["good"].peak_rss_mb is not None and results["good"].peak_rss_mb > 0
    # Re-running resumes: nothing left to do.
    assert list(run_tool(_tool(), docs, run_dir, timeout=2.0, launch=launch)) == []
    assert len(read_results(run_dir / "results.jsonl")) == len(docs)


def test_parse_mem_usage_units() -> None:
    assert parse_mem_usage("1.5GiB / 31.2GiB") == int(1.5 * 2**30)
    assert parse_mem_usage("512MiB / 2GiB") == 512 * 2**20
    assert parse_mem_usage("0B / 0B") == 0
    with pytest.raises(ValueError):
        parse_mem_usage("-- / --")


def test_output_normalization() -> None:
    md = '---\ntitle: "x"\nwarnings: []\n---\n\n# Head\n\nBody [link](http://e.x) and `code`.\n'
    assert strip_frontmatter(md).startswith("# Head")
    assert strip_frontmatter("# no frontmatter\n") == "# no frontmatter\n"
    text = markdown_to_text(strip_frontmatter(md) + "\n<table><tr><td>a</td><td>b</td></tr></table>\n")
    assert text == "Head\n\nBody link and code.\n\na b"


def test_warmup_pdf_is_well_formed() -> None:
    pdf = _pdf_bytes()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    xref = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    assert pdf[xref : xref + 4] == b"xref"
