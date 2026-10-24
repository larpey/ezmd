"""Claude token counting over a run (tools/bench/tokens.py) with the API replaced by a fake; no key needed."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench import tokens  # noqa: E402
from tools.bench.schema import DocResult, append_result  # noqa: E402


def _run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "ezmd-main").mkdir(parents=True)
    (run / "rival").mkdir()
    (run / "ezmd-main" / "d1.md").write_text("---\ntitle: x\n---\nalpha beta gamma", encoding="utf-8")
    (run / "rival" / "d1.md").write_text("alpha beta ![](data:image/png;base64,AAAA) gamma", encoding="utf-8")
    for tool, status in (("ezmd-main", "ok"), ("rival", "ok"), ("rival", "error")):
        doc = "d1" if status == "ok" else "d2"
        append_result(
            run / "results.jsonl",
            DocResult("arxiv", doc, "c", tool, "1", status, output=f"{tool}/{doc}.md" if status == "ok" else None),
        )
    return run


def test_count_run_caches_by_content_and_skips_failed_documents(tmp_path: Path) -> None:
    run = _run(tmp_path)
    calls: list[str] = []
    models: list[str] = []

    def fake(text: str, model: str) -> int:
        calls.append(text)
        models.append(model)
        return len(text.split())

    counted = tokens.count_run(run, None, model="m", counter=fake)
    assert counted == {"ezmd-main": 1, "rival": 1}
    assert len(calls) == 2
    assert "data:image/png" not in "".join(calls) and "title: x" not in "".join(calls)  # placeholder, no frontmatter
    cached = json.loads(tokens.cache_path(run, "rival", "d1").read_text(encoding="utf-8"))
    assert cached["tokens"] == 4 and cached["model"] == "m" and len(cached["sha256"]) == 64
    # a second pass makes no request; a changed output is counted again
    tokens.count_run(run, None, model="m", counter=fake)
    assert len(calls) == 2
    (run / "rival" / "d1.md").write_text("alpha", encoding="utf-8")
    tokens.count_run(run, ["rival"], model="m", counter=fake)
    assert len(calls) == 3
    # another model's tokenizer is another count: the cache is per model as well as per content
    tokens.count_run(run, ["rival"], model="m2", counter=fake)
    assert len(calls) == 4 and models == ["m", "m", "m", "m2"]
    assert json.loads(tokens.cache_path(run, "rival", "d1").read_text(encoding="utf-8"))["model"] == "m2"


def test_cached_count_is_none_when_missing_or_stale(tmp_path: Path) -> None:
    run = _run(tmp_path)
    r = DocResult("arxiv", "d1", "c", "ezmd-main", "1", "ok", output="ezmd-main/d1.md")
    assert tokens.cached_count(run, r) is None
    tokens.count_run(run, ["ezmd-main"], model="m", counter=lambda t, m: 3)
    assert tokens.cached_count(run, r) == 3
    assert tokens.cached_record(run, r) == {"tokens": 3, "model": "m"}
    (run / "ezmd-main" / "d1.md").write_text("changed", encoding="utf-8")
    assert tokens.cached_count(run, r) is None


def test_count_pdfs_caches_by_file_hash_and_skips_long_documents(tmp_path: Path) -> None:
    run = _run(tmp_path)
    short, long = tmp_path / "short.pdf", tmp_path / "long.pdf"
    short.write_bytes(b"%PDF short")
    long.write_bytes(b"%PDF long")
    docs = {"documents": [{"id": "d1", "input": str(short)}, {"id": "d2", "input": str(long)}]}
    (run / "docs.json").write_text(json.dumps(docs), encoding="utf-8")
    calls: list[bytes] = []

    def fake(data: bytes, model: str) -> int:
        calls.append(data)
        return 1000 * len(data)

    pages = {short: 10, long: tokens.PDF_MAX_PAGES + 1}
    assert tokens.count_pdfs(run, model="m", counter=fake, pages_of=lambda p: pages[p]) == 1
    assert calls == [b"%PDF short"]  # the long document is recorded as skipped, never sent
    assert tokens.cached_pdf_count(run, "d1", short) == 10_000
    assert tokens.cached_pdf_count(run, "d2", long) is None
    assert tokens.count_pdfs(run, model="m", counter=fake, pages_of=lambda p: pages[p]) == 1
    assert len(calls) == 1  # cached, including the skip
    short.write_bytes(b"%PDF other")
    assert tokens.cached_pdf_count(run, "d1", short) is None
    # a file over the byte limit is skipped the same way
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF" + b"0" * 64)
    (run / "docs.json").write_text(json.dumps({"documents": [{"id": "d3", "input": str(big)}]}), encoding="utf-8")
    tokens.PDF_MAX_BYTES, saved = 16, tokens.PDF_MAX_BYTES
    try:
        assert tokens.count_pdfs(run, model="m", counter=fake, pages_of=lambda p: 1) == 0
    finally:
        tokens.PDF_MAX_BYTES = saved
    assert len(calls) == 1 and tokens.cached_pdf_count(run, "d3", big) is None


def test_count_run_without_a_key_exits_with_a_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = _run(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(tokens, "api_key", lambda: None)
    with pytest.raises(SystemExit, match="no Anthropic API key"):
        tokens.count_run(run, None)
