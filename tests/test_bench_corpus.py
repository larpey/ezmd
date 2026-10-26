"""The everyday-documents corpus pilot: govdocs1 listing, parallel runs, failure sites and outcome scoring."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench import corpora  # noqa: E402
from tools.bench.adapters.worker import failure_info, failure_site  # noqa: E402
from tools.bench.config import Tool  # noqa: E402
from tools.bench.runner import Launch, run_tool_parallel  # noqa: E402
from tools.bench.schema import Doc, DocResult, append_result, read_results  # noqa: E402
from tools.bench.scoring import corpus as scoring  # noqa: E402

WORKER = textwrap.dedent(
    """
    import json, os, sys, time
    print(json.dumps({"ready": True, "version": "9.9", "startup_seconds": 0.0}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        name = os.path.basename(job["input"])
        if name.startswith("bad"):
            print(json.dumps({"id": job["id"], "ok": False, "error_class": "KeyError",
                              "error": "'x'", "where": "ezmd/a.py:1 f"}), flush=True)
            continue
        time.sleep(0.2)
        os.makedirs(os.path.dirname(job["output"]), exist_ok=True)
        with open(job["output"], "w", encoding="utf-8") as fh:
            fh.write("# out")
        print(json.dumps({"id": job["id"], "ok": True, "chars": 5}), flush=True)
    """
)


def _result(doc_id: str, status: str, cat: str = "pdf", **kw: object) -> DocResult:
    return DocResult("govdocs1", doc_id, cat, "ezmd-main", "1", status, **kw)  # type: ignore[arg-type]


def test_govdocs1_lists_every_thread_file_by_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_GOVDOCS1", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="fetch --only govdocs1"):
        corpora.govdocs1()
    for n in range(corpora.GOVDOCS1_THREADS):
        folder = tmp_path / "threads" / str(n)
        folder.mkdir(parents=True)
        (folder / f"{n:03d}001.PDF").write_bytes(b"%PDF")
        (folder / f"{n:03d}002.html").write_bytes(b"<p>")
    (tmp_path / "threads" / "3" / "003003").write_bytes(b"?")
    docs = corpora.govdocs1()
    assert len(docs) == 21 and docs[0].id == "000001" and docs[0].category == "pdf"
    assert {d.category for d in docs} == {"pdf", "html", "none"}
    assert docs[0].meta == {"thread": 0, "bytes": 4}
    assert [d.id for d in corpora.govdocs1(3)] == sorted(d.id for d in corpora.govdocs1(3))
    assert len(corpora.govdocs1(3)) == 3


def test_failure_site_prefers_the_tools_own_frame() -> None:
    def inner() -> None:
        raise KeyError("x")

    try:
        inner()
    except KeyError as exc:
        site = failure_site(exc, own="test_bench_corpus")
    assert site.endswith(" inner") and "test_bench_corpus.py:" in site
    try:
        json.loads("{")
    except json.JSONDecodeError as exc:
        assert failure_site(exc, own="nothing-matches").endswith(" raw_decode")
        # A venv named after the tool (".../venvs/ezmd-main/Lib/site-packages/json/decoder.py") is not the
        # tool's own code: the match is on the path inside the environment.
        assert "venvs" not in failure_site(exc, own="venvs")


def test_failure_site_ignores_the_environment_path() -> None:
    import types

    def fake_tb(filename: str) -> types.TracebackType | None:
        code = compile("raise KeyError('x')", filename, "exec")
        try:
            exec(code, {})  # a frame with a chosen filename, nothing else
        except KeyError as exc:
            return exc.__traceback__
        return None

    tb = fake_tb(r"C:\cache\venvs\ezmd-main\Lib\site-packages\pydantic\main.py")
    exc = KeyError("x")
    exc.__traceback__ = tb
    assert failure_site(exc, own="ezmd") == "pydantic/main.py:1 <module>"


def test_failure_info_reports_the_wrapped_cause() -> None:
    def crash() -> None:
        raise IndexError("list index out of range")

    def wrap() -> None:
        try:
            crash()
        except Exception as exc:
            raise ValueError("all converters failed: last error: list index out of range") from exc

    try:
        wrap()
    except ValueError as exc:
        info = failure_info(exc)
    assert info["error_class"] == "ValueError" and info["cause"] == "IndexError"
    assert str(info["where"]).endswith(" crash")
    try:
        crash()
    except IndexError as exc:
        assert failure_info(exc)["cause"] is None


def test_where_round_trips_and_old_records_still_load(tmp_path: Path) -> None:
    r = _result("d", "error", error_class="KeyError", error="'x'", where="ezmd/a.py:1 f")
    path = tmp_path / "results.jsonl"
    append_result(path, r)
    assert read_results(path) == [r]
    old = {k: v for k, v in json.loads(r.to_json()).items() if k != "where"}
    assert DocResult.from_dict(old).where is None


def test_parallel_run_records_every_document_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_BENCH_CACHE", str(tmp_path / "cache"))
    script = tmp_path / "worker.py"
    script.write_text(WORKER, encoding="utf-8")
    docs = []
    for i in range(9):
        name = f"{'bad' if i % 4 == 0 else 'good'}{i}.txt"
        (tmp_path / name).write_text("x", encoding="utf-8")
        docs.append(Doc("c", Path(name).stem, tmp_path / name, "txt"))
    tool = Tool(name="fake", kind="venv", adapter="fake", formats=("txt",), license="MIT")
    run_dir = tmp_path / "run"
    launch = Launch([sys.executable, "-I", str(script)])
    results = list(run_tool_parallel(tool, docs, run_dir, 3, timeout=5.0, launch=launch))
    assert sorted(r.doc_id for r in results) == sorted(d.id for d in docs)
    assert sorted(r.doc_id for r in read_results(run_dir / "results.jsonl")) == sorted(d.id for d in docs)
    bad = [r for r in results if r.status == "error"]
    assert len(bad) == 3 and all(r.where == "ezmd/a.py:1 f" for r in bad)
    assert {p.name for p in (run_dir / "logs").glob("fake.*.log")} == {"fake.0.log", "fake.1.log", "fake.2.log"}
    assert list(run_tool_parallel(tool, docs, run_dir, 3, timeout=5.0, launch=launch)) == []


def test_outcomes_and_clusters(tmp_path: Path) -> None:
    results = [
        _result("000001", "ok", output="ezmd-main/000001.md"),
        _result("000002", "error", "swf", error_class="UnsupportedMediaType", error="application/x-shockwave"),
        _result("000003", "error", "xls", error_class="ConversionError", error="LibreOffice exit 77 on 'a.xls'"),
        _result("000004", "error", "xls", error_class="ConversionError", error="LibreOffice exit 81 on 'b.xls'"),
        _result("000005", "error", error_class="KeyError", error="'Font'", where="ezmd_converters/pdf/x.py:10 f"),
        _result("000006", "error", "ppt", error_class="KeyError", error="'A'", where="ezmd_converters/pdf/x.py:10 f"),
        _result("000007", "timeout", error_class="Timeout", error="exceeded 120s"),
        _result("000008", "crash", "doc", error_class="WorkerExited", error="worker process exited"),
        _result(
            "000009",
            "error",
            error_class="ConversionError",
            error="all converters failed for 000009.pdf: tried ['documents.pdfium_text']; last error: 1 validation",
            where="ezmd_converters/pdf/assemble.py:238 _line",
            cause="ValidationError",
        ),
        _result(
            "000010",
            "error",
            "txt",
            error_class="ConversionError",
            error="all converters failed for 000010.txt: tried ['data.yaml']; last error: invalid YAML",
            where="ezmd_converters/data/yaml_conv.py:40 convert",
            cause="YAMLError",
        ),
    ]
    assert [scoring.outcome(r) for r in results[:3]] == ["ok", "declared", "declared"]
    assert {scoring.outcome(r) for r in results[4:9]} == {"bug"}
    assert scoring.outcome(results[9]) == "declared"
    clusters = scoring.cluster(results)
    assert [(c["kind"], c["count"]) for c in clusters] == [
        ("bug", 2),
        ("bug", 1),
        ("bug", 1),
        ("bug", 1),
        ("declared", 2),
        ("declared", 1),
        ("declared", 1),
    ]
    assert clusters[0]["where"] == "ezmd_converters/pdf/x.py:10 f" and clusters[0]["categories"] == {"pdf": 1, "ppt": 1}
    wrapped = [c for c in clusters if c["error_class"] == "ValidationError"]
    assert len(wrapped) == 1 and wrapped[0]["where"] == "ezmd_converters/pdf/assemble.py:238 _line"
    assert clusters[4]["message"] == "LibreOffice exit # on '…'" and clusters[4]["samples"] == ["000003", "000004"]
    scores = scoring.score(results, tmp_path)
    tool = scores["tools"]["ezmd-main"]
    assert scores["metric"] == "clean_rate" and tool["primary"]["value"] == pytest.approx(0.5)
    assert tool["secondary"]["bug"] == 5 and tool["secondary"]["categories"]["pdf"] == {"n": 4, "ok": 1, "bug": 3}
    md = (tmp_path / "clusters.md").read_text(encoding="utf-8")
    assert "| pdf | 4 | 1 | 0 | 3 |" in md and "`ezmd_converters/pdf/x.py:10 f`" in md
