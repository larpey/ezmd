"""Damaged arXiv variants (tools/bench/damage.py) and their scorer; built from a fixture PDF, no network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench import damage  # noqa: E402
from tools.bench.schema import DocResult  # noqa: E402
from tools.bench.scoring import damaged  # noqa: E402
from tools.bench.scoring.arxiv import recall, witness, words  # noqa: E402

FIXTURE = ROOT / "fixtures" / "pdf" / "born-digital-report" / "input.pdf"


def _layer(pdf: Path) -> list[str]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        out = []
        for page in doc:
            tp = page.get_textpage()
            out.append(tp.get_text_range())
            tp.close()
            page.close()
        return out
    finally:
        doc.close()


def test_damaged_pages_is_a_block_that_spares_the_first_page() -> None:
    assert damage.damaged_pages(1) == [0]
    assert damage.damaged_pages(2) == [1]
    block = damage.damaged_pages(36)
    assert block == list(range(block[0], block[0] + len(block)))
    assert block[0] >= 1 and len(block) == round(36 * damage.PAGES_SHARE)
    assert damage.damaged_pages(5) == [1]


def test_scan_and_pages_variants_remove_the_text_layer_where_they_should(tmp_path: Path) -> None:
    original = _layer(FIXTURE)
    assert len(original) >= 2 and sum(len(t) for t in original) > 200
    meta = damage.build("scan", FIXTURE, tmp_path / "scan.pdf")
    scanned = _layer(tmp_path / "scan.pdf")
    assert len(scanned) == len(original) == meta["pages"]
    assert all(not t.strip() for t in scanned)
    assert meta["damaged_pages"] == list(range(1, len(original) + 1))
    meta = damage.build("pages", FIXTURE, tmp_path / "pages.pdf")
    partial = _layer(tmp_path / "pages.pdf")
    hit = {p - 1 for p in meta["damaged_pages"]}
    assert hit and 0 not in hit
    for i, text in enumerate(partial):
        if i in hit:
            assert not text.strip()
        else:
            assert words(text) == words(original[i])
    assert meta["textless_pages"] == []


def test_trunc_variant_is_a_prefix_of_the_file(tmp_path: Path) -> None:
    meta = damage.build("trunc", FIXTURE, tmp_path / "trunc.pdf")
    data = FIXTURE.read_bytes()
    cut = (tmp_path / "trunc.pdf").read_bytes()
    assert cut == data[: len(cut)] and len(cut) == int(len(data) * damage.TRUNC_SHARE)
    assert meta["damaged_pages"] == []
    with pytest.raises(ValueError, match="unknown damage kind"):
        damage.build("fold", FIXTURE, tmp_path / "x.pdf")


def test_page_accuracy_counts_textless_pages_of_the_intact_paper_as_expected() -> None:
    assert damaged.page_accuracy(None, [3, 4]) is None
    assert damaged.page_accuracy({3, 4}, []) is None
    assert damaged.page_accuracy({3, 4}, [3, 4]) == 1.0
    assert damaged.page_accuracy({3, 4, 9}, [3, 4]) == pytest.approx(2 / 3, abs=1e-3)
    assert damaged.page_accuracy({3, 4, 9}, [3, 4], textless=[9]) == 1.0
    assert damaged.page_accuracy({3}, [3, 4]) == 0.5


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, str]]:
    """A run directory over the fixture: ezmd declares, a rival says nothing, and a loud failure."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("EZMD_BENCH_CACHE", str(cache))
    run = tmp_path / "run"
    run.mkdir()
    pages = damage.build("pages", FIXTURE, cache / "pages.pdf")
    scan = damage.build("scan", FIXTURE, cache / "scan.pdf")
    w = witness("paper", FIXTURE)
    layer = _layer(FIXTURE)
    kept = "\n".join(t for i, t in enumerate(layer) if i + 1 not in pages["damaged_pages"])
    docs = {
        "corpus": "arxiv-damaged",
        "documents": [
            {
                "id": "paper~pages",
                "category": "pages",
                "input": str(cache / "pages.pdf"),
                "source": str(FIXTURE),
                "paper": "paper",
                **pages,
            },
            {
                "id": "paper~scan",
                "category": "scan",
                "input": str(cache / "scan.pdf"),
                "source": str(FIXTURE),
                "paper": "paper",
                **scan,
            },
            {
                "id": "paper~trunc",
                "category": "trunc",
                "input": str(cache / "trunc.pdf"),
                "source": str(FIXTURE),
                "paper": "paper",
                "kind": "trunc",
                "damaged_pages": [],
                "pages": w.pages,
                "textless_pages": [],
            },
        ],
    }
    (run / "docs.json").write_text(json.dumps(docs), encoding="utf-8")
    for tool in ("ezmd-main", "rival"):
        (run / tool).mkdir()
        (run / tool / "paper~pages.md").write_text(kept, encoding="utf-8")
        (run / tool / "paper~scan.md").write_text("", encoding="utf-8")
    listed = ",".join(str(p) for p in pages["damaged_pages"])
    (run / "ezmd-main" / "paper~pages.md.warnings.json").write_text(
        json.dumps(
            {
                "truncated": False,
                "warnings": [
                    {
                        "kind": "pages_without_text",
                        "count": len(pages["damaged_pages"]),
                        "page": pages["damaged_pages"][0],
                        "detail": {"pages": listed},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run / "ezmd-main" / "paper~scan.md.warnings.json").write_text(
        json.dumps(
            {
                "truncated": False,
                "warnings": [
                    {
                        "kind": "pages_without_text",
                        "count": w.pages,
                        "page": 1,
                        "detail": {"pages": ",".join(str(p) for p in range(1, w.pages + 1))},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return run, {"kept": kept}


def test_damaged_scorer_separates_declared_silent_and_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run, _ = _run(tmp_path, monkeypatch)

    def result(tool: str, doc: str, status: str = "ok") -> DocResult:
        return DocResult(
            "arxiv-damaged",
            doc,
            doc.split("~")[1],
            tool,
            "1",
            status,
            output=f"{tool}/{doc}.md" if status == "ok" else None,
        )

    results = [
        result("ezmd-main", "paper~pages"),
        result("ezmd-main", "paper~scan"),
        result("ezmd-main", "paper~trunc", "error"),
        result("rival", "paper~pages"),
        result("rival", "paper~scan"),
        result("rival", "paper~trunc", "error"),
    ]
    scores = damaged.score(results, run)
    assert scores["higher_is_better"] is False and scores["metric"] == "silent_loss"
    ez, rival = scores["tools"]["ezmd-main"], scores["tools"]["rival"]
    assert ez["categories"]["damaged-silent-loss"]["value"] == 0.0
    assert rival["categories"]["damaged-silent-loss"]["value"] == pytest.approx(2 / 3, abs=1e-3)
    assert rival["categories"]["damaged-scan-silent-loss"]["value"] == 1.0
    assert ez["categories"]["damaged-scan-text-recall"]["value"] == 0.0
    assert ez["categories"]["damaged-page-accuracy"]["value"] == 1.0
    assert rival["categories"]["damaged-page-accuracy"]["n"] == 0
    # the loud failure is neither lost nor silent, and shows in the failure rate
    assert ez["categories"]["damaged-trunc-silent-loss"]["value"] == 0.0
    assert ez["secondary"]["failed_rate"]["value"] == pytest.approx(1 / 3, abs=1e-3)
    assert ez["secondary"]["declared_when_lost"]["value"] == 1.0
    assert rival["secondary"]["declared_when_lost"]["value"] is None
    # the pages variant lost exactly the block
    pages_recall = ez["categories"]["damaged-pages-text-recall"]["value"]
    w = witness("paper", FIXTURE)
    assert pages_recall == pytest.approx(round(recall(w.words, words(_run_kept(run))), 4))


def _run_kept(run: Path) -> str:
    return (run / "ezmd-main" / "paper~pages.md").read_text(encoding="utf-8")


def test_damaged_heldout_is_the_held_out_papers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.bench import corpora
    from tools.bench.corpora import Doc

    monkeypatch.setenv("EZMD_BENCH_CACHE", str(tmp_path / "cache"))
    papers = [Doc("arxiv", f"p{i:02d}", tmp_path / f"p{i:02d}.pdf", "c", {"title": f"t{i}"}) for i in range(40)]

    def arxiv(sample: int | None = 30) -> list[Doc]:
        return corpora._sample(papers, sample)

    monkeypatch.setattr(corpora, "arxiv", arxiv)
    monkeypatch.setitem(corpora.CORPORA, "arxiv", arxiv)

    def build(kind: str, src: Path, dest: Path) -> dict[str, object]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        return {"kind": kind, "damaged_pages": [], "pages": 3, "textless_pages": []}

    monkeypatch.setattr(damage, "build", build)
    default = corpora.arxiv_damaged()
    assert len(default) == 3 * damage.DAMAGED_SAMPLE
    default_papers = {d.meta["paper"] for d in default}
    assert default_papers <= {d.id for d in corpora.arxiv()}
    held = corpora.heldout("arxiv-damaged")
    held_papers = {d.meta["paper"] for d in held}
    assert held_papers == {d.id for d in corpora.heldout("arxiv")} and len(held) == 3 * len(held_papers)
    assert not held_papers & default_papers and len(held_papers) == 10
    assert {d.id for d in held} == {f"{p}~{k}" for p in held_papers for k in damage.KINDS}
