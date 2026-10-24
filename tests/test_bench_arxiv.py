"""The arXiv corpus, its scorer and the local-model QA helpers (tools/bench); no model or competitor needed."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench import corpora, qa  # noqa: E402
from tools.bench.report import _verdict  # noqa: E402
from tools.bench.schema import DocResult  # noqa: E402
from tools.bench.scoring import arxiv  # noqa: E402


def _manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ids: list[str]) -> Path:
    cache = tmp_path / "cache"
    papers = cache / "corpora" / "arxiv" / "papers"
    papers.mkdir(parents=True)
    entries = []
    for i, pid in enumerate(ids):
        (papers / f"{pid}.pdf").write_bytes(b"%PDF-1.4 stub")
        entries.append(
            {
                "id": pid,
                "title": f"Paper {i}",
                "set": "Computer Science" if i % 2 else "Physics and Astronomy",
                "year": 2026,
                "license": "http://creativecommons.org/licenses/by/4.0/",
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setenv("EZMD_BENCH_CACHE", str(cache))
    monkeypatch.setattr(corpora, "ARXIV_MANIFEST", manifest)
    return cache


def test_arxiv_corpus_reads_the_manifest_and_samples_with_the_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _manifest(tmp_path, monkeypatch, [f"2601.{n:05d}" for n in range(40)])
    docs = corpora.arxiv(None)
    assert [d.id for d in docs] == [f"2601_{n:05d}" for n in range(40)]
    assert {d.category for d in docs} == {"computer-science", "physics-and-astronomy"}
    assert docs[0].meta["license"].endswith("/by/4.0/")
    sample = corpora.arxiv(3)
    assert len(sample) == 3 and sample == corpora.arxiv(3)
    assert len(corpora.arxiv()) == corpora.ARXIV_SAMPLE
    assert {d.id for d in corpora.heldout("arxiv")} | {d.id for d in corpora.arxiv()} == {d.id for d in docs}


def test_norm_and_words_fold_tex_typography() -> None:
    text = "Coeﬃcients of the \U0001d465-axis; recon" + chr(0xFFFE) + "\nstruction done"
    assert arxiv.norm(text) == "coefficients of the x-axis; reconstruction done"
    assert arxiv.words(text) == Counter({"coefficients": 1, "the": 1, "axis": 1, "reconstruction": 1, "done": 1})


def test_recall_counts_each_occurrence_once() -> None:
    src = Counter({"alpha": 2, "beta": 1, "gamma": 1})
    assert arxiv.recall(src, Counter({"alpha": 1, "beta": 5})) == pytest.approx(0.5)
    assert arxiv.recall(src, src) == 1.0
    assert arxiv.recall(Counter(), Counter()) == 1.0


def test_headings_and_outline_recall_ignore_numbering_styles() -> None:
    md = "# 1 Introduction\n\ntext\n\nII. Related Work\n----------------\n\n### B.1 Appendix Proofs\n\n**Bold line**\n"
    assert arxiv.headings_of(md) == ["1 Introduction", "II. Related Work", "B.1 Appendix Proofs"]
    bookmarks = ["Introduction", "2 Related Work", "Appendix Proofs", "Conclusion"]
    assert arxiv.outline_recall(bookmarks, arxiv.headings_of(md)) == pytest.approx(0.75)
    assert arxiv.outline_recall(["Only", "Two"], ["Only", "Two"]) is None
    # A long bookmark contained in a wrapped heading counts; a short one needs an exact match.
    assert arxiv.outline_recall(
        ["Experimental Setup", "Results", "Data"], ["3 Experimental Setup and Hyperparameters", "4 Results", "Dataset"]
    ) == pytest.approx(2 / 3)


def _result(tool: str, doc: str = "2601_00001", status: str = "ok") -> DocResult:
    return DocResult("arxiv", doc, "cs", tool, "1", status, output=f"{tool}/{doc}.md" if status == "ok" else None)


def test_declared_loss_needs_a_loss_kind_not_a_furniture_notice(tmp_path: Path) -> None:
    (tmp_path / "ezmd-main").mkdir()
    out = tmp_path / "ezmd-main" / "2601_00001.md"
    out.write_text("# x", encoding="utf-8")
    side = Path(str(out) + ".warnings.json")
    side.write_text(
        json.dumps({"truncated": False, "warnings": [{"kind": "removed_running_header_footer"}]}), encoding="utf-8"
    )
    assert arxiv.declared_loss(_result("ezmd-main"), tmp_path) is False
    side.write_text(json.dumps({"truncated": False, "warnings": [{"kind": "unmapped_glyphs"}]}), encoding="utf-8")
    assert arxiv.declared_loss(_result("ezmd-main"), tmp_path) is True
    side.write_text(json.dumps({"truncated": True, "warnings": []}), encoding="utf-8")
    assert arxiv.declared_loss(_result("ezmd-main"), tmp_path) is True
    assert arxiv.declared_loss(_result("markitdown"), tmp_path) is None


def _fake_witness(cache: Path, doc_id: str, text: str, bookmarks: list[str], pages: int) -> None:
    wdir = cache / "corpora" / "arxiv" / "witness"
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / f"{doc_id}.json").write_text(
        json.dumps({"pages": pages, "text": text, "bookmarks": bookmarks}), encoding="utf-8"
    )


def test_score_separates_silent_from_declared_loss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _manifest(tmp_path, monkeypatch, ["2601.00001"])
    run = tmp_path / "run"
    run.mkdir()
    words = " ".join(f"word{i}" for i in range(100))
    _fake_witness(cache, "2601_00001", words, ["Intro", "Method", "Results"], pages=2)
    (run / "docs.json").write_text(
        json.dumps({"documents": [{"id": "2601_00001", "input": str(cache / "corpora/arxiv/papers/2601.00001.pdf")}]}),
        encoding="utf-8",
    )
    for tool, keep, side in (
        ("ezmd-main", 90, {"truncated": False, "warnings": [{"kind": "unmapped_glyphs"}]}),
        ("ezmd-main-rag", 90, {"truncated": False, "warnings": [{"kind": "engine_fallback"}]}),
        ("markitdown", 90, None),
        ("pymupdf4llm", 100, None),
    ):
        (run / tool).mkdir()
        body = "# Intro\n\n" + " ".join(f"word{i}" for i in range(keep)) + "\n\n## Results\n"
        (run / tool / "2601_00001.md").write_text(body, encoding="utf-8")
        if side is not None:
            (run / tool / "2601_00001.md.warnings.json").write_text(json.dumps(side), encoding="utf-8")
    results = [_result(t) for t in ("ezmd-main", "ezmd-main-rag", "markitdown", "pymupdf4llm")] + [
        _result("docling", status="error")
    ]
    scores = arxiv.score(results, run)
    cats = {t: {c: v["value"] for c, v in s["categories"].items()} for t, s in scores["tools"].items()}
    assert cats["ezmd-main"]["arxiv-text-recall"] == pytest.approx(0.9)
    assert cats["ezmd-main"]["arxiv-silent-loss"] == 0.0  # lost 10%, said so
    assert cats["ezmd-main-rag"]["arxiv-silent-loss"] == 1.0  # lost 10%, engine_fallback is not a loss notice
    assert cats["markitdown"]["arxiv-silent-loss"] == 1.0  # no warning channel at all
    assert cats["pymupdf4llm"]["arxiv-silent-loss"] == 0.0  # lost nothing
    assert cats["docling"]["arxiv-text-recall"] == 0.0 and cats["docling"]["arxiv-silent-loss"] == 0.0  # loud failure
    assert cats["ezmd-main"]["arxiv-outline-recall"] == pytest.approx(2 / 3, abs=1e-3)
    assert cats["ezmd-main"]["arxiv-tokens-per-page"] > 0 and cats["docling"]["arxiv-tokens-per-page"] is None
    assert scores["metric"] == "text_recall" and scores["category_direction"]["arxiv-silent-loss"] is False
    assert scores["tools"]["ezmd-main"]["secondary"]["false_alarm_rate"]["value"] == 0.0
    assert scores["tools"]["markitdown"]["secondary"]["declared_rate"]["value"] is None


def test_qa_scores_become_the_primary_metric(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _manifest(tmp_path, monkeypatch, ["2601.00001"])
    run = tmp_path / "run"
    (run / "ezmd-main").mkdir(parents=True)
    _fake_witness(cache, "2601_00001", "alpha beta gamma", [], pages=1)
    (run / "docs.json").write_text(
        json.dumps({"documents": [{"id": "2601_00001", "input": "x.pdf"}]}), encoding="utf-8"
    )
    (run / "ezmd-main" / "2601_00001.md").write_text("alpha beta gamma", encoding="utf-8")
    (run / "qa" / "ezmd-main").mkdir(parents=True)
    items = [
        {"question": "q", "answer": "a", "answer_given": "a", "correct": True},
        {"question": "q2", "answer": "b", "answer_given": "UNKNOWN", "correct": False},
    ]
    (run / "qa" / "ezmd-main" / "2601_00001.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    scores = arxiv.score([_result("ezmd-main")], run)
    assert scores["metric"] == "qa_accuracy"
    assert scores["tools"]["ezmd-main"]["primary"]["value"] == pytest.approx(0.5)
    assert scores["tools"]["ezmd-main"]["categories"]["arxiv-answers-per-10k-tokens"]["value"] > 0


def test_parse_json_array_tolerates_fences_and_chatter() -> None:
    assert qa.parse_json_array('Sure!\n```json\n["a", "b"]\n```\nDone.') == ["a", "b"]
    assert qa.parse_json_array('[{"question": "q"}]') == [{"question": "q"}]
    tex = '[{"answer": "\\alpha = 1", "quote": "the \\sigma term\\n"}]'
    assert qa.parse_json_array(tex) == [{"answer": "\\alpha = 1", "quote": "the \\sigma term\n"}]
    with pytest.raises(ValueError):
        qa.parse_json_array("no array here")
    with pytest.raises(ValueError):
        qa.parse_json_array('{"a": 1}')


def test_validate_questions_drops_pairs_whose_quote_is_not_in_the_text() -> None:
    text = "The model reaches 92.4% accuracy on the test set.\nTraining took 3 days on 8 GPUs."
    raw = [
        {"question": "What accuracy?", "answer": "92.4%", "quote": "The model reaches 92.4% accuracy on the test set."},
        {"question": "How long?", "answer": "3 days", "quote": "training took 3 DAYS on 8 gpus"},
        {"question": "Invented?", "answer": "yes", "quote": "This sentence is not in the paper."},
        {"question": "Long answer", "answer": " ".join(["w"] * 20), "quote": "Training took 3 days on 8 GPUs."},
        "not a dict",
    ]
    kept = qa.validate_questions(raw, text)
    assert [k["answer"] for k in kept] == ["92.4%", "3 days"]


def test_cut_tokens_keeps_a_prefix_within_the_limit() -> None:
    text = "\n".join(f"line {i} with several words in it" for i in range(400))
    cut = qa.cut_tokens(text, 500)
    assert arxiv.count_tokens(cut) <= 500
    assert text.startswith(cut) and cut.endswith("in it")
    assert qa.cut_tokens("short", 500) == "short"


def test_verdict_respects_lower_is_better() -> None:
    rows = {
        "ezmd-main": {"value": 100.0, "n": 6, "per_doc": {f"d{i}": 100.0 for i in range(6)}},
        "markitdown": {"value": 150.0, "n": 6, "per_doc": {f"d{i}": 150.0 + i for i in range(6)}},
    }
    assert _verdict(rows, "ezmd-main", higher=False)["verdict"] == "leads"
    assert _verdict(rows, "ezmd-main", higher=True)["verdict"] == "trails"
