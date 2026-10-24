"""Benchmark corpora. Each returns a deterministic list of documents; samples are seeded and recorded.

Corpus content is never committed: public sets are downloaded to the cache directory (see bench/CORPORA.md for
sources, revisions and licenses). The ezmd fixture corpus is read in place from fixtures/.
"""

from __future__ import annotations

import gzip
import json
import random
import tomllib
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.bench.config import ROOT, cache_dir
from tools.bench.schema import Doc

SEED = 20261013
OLMOCR_REVISION = "54a96a6fb6a2bd3b297e59869491db4d3625b711"
OMNIDOC_GT_REVISION = "aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec"  # main: OmniDocBench.json (1651 pages)
OMNIDOC_PDF_REVISION = "f5f559bddf50e36f7f9899d842d0006f13ce8afc"  # v1_0: ori_pdfs (original PDF page slices)
AEB_REVISION = "4a3bc979f76c0df73cb95fe272e2fc1b96f9f010"

SMOKE_FIXTURES = (
    "pdf/born-digital-report",
    "pdf/two-column-page",
    "office/docx-structure",
    "office/pptx-lecture",
    "office/xlsx-multi-sheet",
    "web/article-full-body",
    "ebooks/epub3-novel",
    "comms/eml-attachments",
    "data/csv-wide",
    "text/markdown-kitchen-sink",
)


def corpora_dir() -> Path:
    return cache_dir() / "corpora"


def _fixture_docs(names: tuple[str, ...] | None, corpus: str) -> list[Doc]:
    root = ROOT / "fixtures"
    docs = []
    for meta_path in sorted(root.glob("*/*/meta.toml")):
        fx = meta_path.parent
        rel = f"{fx.parent.name}/{fx.name}"
        if names is not None and rel not in names:
            continue
        inputs = sorted(p for p in fx.iterdir() if p.name.startswith("input.") and p.suffix != ".url")
        if not inputs:
            continue
        meta = tomllib.loads(meta_path.read_text(encoding="utf-8"))
        docs.append(
            Doc(
                corpus=corpus,
                id=f"{fx.parent.name}__{fx.name}",
                input=inputs[0],
                category=fx.parent.name,
                meta={"fixture": rel, "converter": meta.get("converter", ""), "requires": meta.get("requires", [])},
            )
        )
    return docs


def fixtures(sample: int | None = None) -> list[Doc]:
    return _sample(_fixture_docs(None, "fixtures"), sample)


def smoke(sample: int | None = None) -> list[Doc]:
    return _fixture_docs(SMOKE_FIXTURES, "smoke")


def _sample(docs: list[Doc], n: int | None) -> list[Doc]:
    if n is None or n >= len(docs):
        return docs
    picked = random.Random(SEED).sample(docs, n)
    return sorted(picked, key=lambda d: d.id)


def stratified(docs: list[Doc], per_category: int | None) -> list[Doc]:
    """Seeded sample of up to `per_category` documents from each category (all when None)."""
    if per_category is None:
        return docs
    by_cat: dict[str, list[Doc]] = defaultdict(list)
    for d in docs:
        by_cat[d.category].append(d)
    rng = random.Random(SEED)
    out: list[Doc] = []
    for cat in sorted(by_cat):
        group = sorted(by_cat[cat], key=lambda d: d.id)
        out.extend(group if len(group) <= per_category else rng.sample(group, per_category))
    return sorted(out, key=lambda d: (d.category, d.id))


def olmocr_root() -> Path:
    return corpora_dir() / "olmocr-bench" / "bench_data"


def olmocr(sample: int | None = 50) -> list[Doc]:
    """olmOCR-Bench: one PDF page per document; category = the test file (arxiv_math, old_scans, ...)."""
    root = olmocr_root()
    pdfs: dict[str, str] = {}
    for jsonl in sorted(root.glob("*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pdfs.setdefault(json.loads(line)["pdf"], jsonl.stem)
    docs = []
    for rel, cat in sorted(pdfs.items()):
        path = root / "pdfs" / rel
        if path.exists():
            doc_id = rel.removesuffix(".pdf").replace("/", "__")
            docs.append(Doc("olmocr", doc_id, path, cat, {"pdf": rel}))
    return stratified(docs, sample)


def omnidoc_root() -> Path:
    return corpora_dir() / "omnidocbench"


def omnidoc(sample: int | None = 300) -> list[Doc]:
    """OmniDocBench pages whose original PDF slice exists (v1_0 ori_pdfs), scored against the main GT."""
    root = omnidoc_root()
    gt = json.loads((root / "main" / "OmniDocBench.json").read_text(encoding="utf-8"))
    pdf_dir = root / "v1_0" / "ori_pdfs"
    docs = []
    for page in gt:
        info = page["page_info"]
        stem = Path(info["image_path"]).stem
        pdf = pdf_dir / f"{stem}.pdf"
        if pdf.exists():
            attrs = info.get("page_attribute", {})
            docs.append(
                Doc(
                    "omnidoc",
                    stem,
                    pdf,
                    str(attrs.get("data_source", "unknown")),
                    {"image_path": info["image_path"], "language": attrs.get("language", "")},
                )
            )
    docs.sort(key=lambda d: d.id)
    return _sample(docs, sample)


def aeb_root() -> Path:
    return corpora_dir() / "aeb"


def web(sample: int | None = None) -> list[Doc]:
    """ScrapingHub article-extraction-benchmark: 181 article pages (gzip HTML, decompressed once to the cache)."""
    root = aeb_root()
    out_dir = corpora_dir() / "aeb-html"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = []
    for gz in sorted((root / "html").glob("*.html.gz")):
        doc_id = gz.name.removesuffix(".html.gz")
        html = out_dir / f"{doc_id}.html"
        if not html.exists():
            html.write_bytes(gzip.decompress(gz.read_bytes()))
        docs.append(Doc("web", doc_id, html, "web-article"))
    return _sample(docs, sample)


ARXIV_MANIFEST = ROOT / "bench" / "corpora" / "arxiv-manifest.json"
"""109 arXiv papers under CC BY 4.0 (OpenAlex sample, licence re-checked on each paper's arXiv page):
ids, titles, subject sets and licences. `fetch --only arxiv` downloads the PDFs from arxiv.org."""
ARXIV_SAMPLE = 30


def arxiv_root() -> Path:
    return corpora_dir() / "arxiv"


def arxiv_manifest() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = json.loads(ARXIV_MANIFEST.read_text(encoding="utf-8"))
    return entries


def _slug(text: str) -> str:
    return "-".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())


def arxiv(sample: int | None = ARXIV_SAMPLE) -> list[Doc]:
    """Whole born-digital papers (not single pages): the documents an LLM user actually feeds a converter.
    Category = the paper's OpenAlex subject set; the seeded sample is drawn over the whole corpus so a
    30-paper run keeps the subject mix of the 109."""
    pdf_dir = arxiv_root() / "papers"
    docs = []
    missing = []
    for entry in arxiv_manifest():
        path = pdf_dir / f"{entry['id']}.pdf"
        if not path.exists():
            missing.append(str(entry["id"]))
            continue
        meta = {"title": entry["title"], "license": entry["license"], "year": entry.get("year")}
        docs.append(Doc("arxiv", str(entry["id"]).replace(".", "_"), path, _slug(entry["set"]), meta))
    if missing:
        # A seeded sample of a partial corpus is a different cohort; say so instead of sampling what is there.
        raise FileNotFoundError(
            f"arxiv: {len(missing)} of {len(missing) + len(docs)} papers are not in {pdf_dir} "
            f"(first: {missing[0]}); run `python -m tools.bench fetch --only arxiv`"
        )
    docs.sort(key=lambda d: d.id)
    return _sample(docs, sample)


CORPORA: dict[str, Callable[[int | None], list[Doc]]] = {
    "smoke": smoke,
    "fixtures": fixtures,
    "olmocr": olmocr,
    "omnidoc": omnidoc,
    "web": web,
    "arxiv": arxiv,
}


def heldout(corpus: str) -> list[Doc]:
    """The documents of `corpus` outside its default sample: never used to develop or tune ezmd, so a score
    on them is not fitted to the published sample (D-0032 "on a held-out split")."""
    seen = {d.id for d in CORPORA[corpus]()}  # type: ignore[call-arg]
    rest = [d for d in CORPORA[corpus](None) if d.id not in seen]
    if not rest:
        raise ValueError(f"{corpus}: the default sample is the whole corpus, so there is no held-out split")
    return rest
