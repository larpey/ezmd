"""The LaTeX-source witness (tools/bench/scoring/latex.py): archive handling, flattening, text extraction."""

from __future__ import annotations

import gzip
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench.scoring import latex  # noqa: E402
from tools.bench.scoring.arxiv import words  # noqa: E402

MAIN = r"""
\documentclass{article}
\newtheorem{thm}{Theorem}[section]
\newcommand{\R}{\mathbb{R}}
\begin{document}
\title{Weak solutions to the reflector problem}
\maketitle
% a comment with the word invisible in it
\section{Introduction}\label{sec:intro}
We study reflectors as in \cite{karakhanyan2010} and Section~\ref{sec:intro}; see Figure~\cref{fig:one}.
Let $x \in \R^n$ be a point and $\int_0^1 f(t)\,dt$ an integral.
\input{body}
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""
BODY = r"""
\subsection{Setting}
The aperture is bounded and the irradiance \emph{positive}.
\includegraphics[width=\linewidth]{figures/plane-reflector.pdf}
"""
BBL = r"""
\begin{thebibliography}{1}
\bibitem{karakhanyan2010} A.~Karakhanyan. Existence of reflectors. \emph{Journal}, 2010.
  doi:10.1000/xyz123 https://ui.adsabs.harvard.edu/abs/2010J.....1K
\end{thebibliography}
"""


def _tar(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_members_reads_tar_gzip_and_bare_files() -> None:
    files = latex.members(_tar({"main.tex": MAIN, "body.tex": BODY}))
    assert set(files) == {"main.tex", "body.tex"}
    assert latex.members(gzip.compress(MAIN.encode())) == {"main.tex": MAIN.encode()}
    assert latex.members(MAIN.encode()) == {"main.tex": MAIN.encode()}


def test_main_file_prefers_the_file_that_begins_the_document() -> None:
    tex = {"a.tex": "\\documentclass{article}\n", "b.tex": MAIN, "c.bbl": BBL}
    assert latex.main_file(tex) == "b.tex"
    assert latex.main_file({"notes.tex": "no class here"}) is None


def test_source_plain_text_keeps_prose_and_drops_preamble_labels_math_and_comments() -> None:
    raw = _tar({"paper.tex": MAIN, "body.tex": BODY, "paper.bbl": BBL, "figures/plane-reflector.pdf": "%PDF"})
    text = latex.source_plain_text(raw)
    assert text is not None
    got = words(text)
    for word in ("weak", "solutions", "reflector", "aperture", "bounded", "positive", "karakhanyan", "existence"):
        assert got[word] >= 1, word
    for word in ("theorem", "newtheorem", "invisible", "intro", "karakhanyan2010", "linewidth", "plain", "mathbb"):
        assert got[word] == 0, word
    for word in ("doi", "xyz123", "https", "adsabs", "harvard"):  # link targets never print on the page
        assert got[word] == 0, word
    assert got["int"] == 0 and got["figures"] == 0


def test_source_text_caches_and_records_pdf_only_papers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    monkeypatch.setenv("EZMD_BENCH_CACHE", str(cache))
    src = cache / "corpora" / "arxiv" / "source"
    src.mkdir(parents=True)
    assert latex.source_text("2601_00001", "2601.00001") is None  # not fetched: no cache entry either
    assert not (cache / "corpora" / "arxiv" / "witness" / "2601_00001.source.json").exists()
    (src / "2601.00002.src").write_bytes(b"")
    assert latex.source_text("2601_00002", "2601.00002") is None
    cached = json.loads((cache / "corpora" / "arxiv" / "witness" / "2601_00002.source.json").read_text("utf-8"))
    assert cached == {"text": None, "reason": "pdf-only"}
    (src / "2601.00003.src").write_bytes(_tar({"main.tex": MAIN, "body.tex": BODY}))
    text = latex.source_text("2601_00003", "2601.00003")
    assert text is not None and "aperture" in text
    (src / "2601.00003.src").write_bytes(b"garbage")  # the cache answers from now on
    assert latex.source_text("2601_00003", "2601.00003") == text
