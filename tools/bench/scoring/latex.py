"""The LaTeX source of an arXiv paper as a witness no PDF text layer produced.

`text recall` against the PDF's own text layer favours whichever tool reads that layer with the same library the
witness used (ezmd and pypdfium2). The paper's source is independent of every converter: its prose is what the
author wrote, and the compiled PDF contains it. `fetch --only arxiv-source` stores each e-print under the corpus;
`source_text` turns one into plain text once (pylatexenc, math removed, preamble and reference-label macros
dropped) and caches it next to the text-layer witness.

The source over-counts a little (words in macros pylatexenc does not know, text only in a `\\iffalse` block) and
under-counts a little (words inside math, figure labels drawn as vectors), so no tool reaches 1.0 against it;
scoring/arxiv.py reports the raw text layer's own recall against the source as the reference to read the others by.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import tarfile
from pathlib import Path

from tools.bench.corpora import arxiv_root, arxiv_source_dir

TEX_SUFFIXES = (".tex", ".ltx", ".bbl", ".pdf_tex")
_COMMENT = re.compile(r"(?<!\\)%.*")
_INPUT = re.compile(r"\\(?:input|include|subfile)\{([^}]*)\}")
_BIBLIOGRAPHY = re.compile(r"\\bibliography\{[^}]*\}")
_BEGIN_DOCUMENT = re.compile(r"\\begin\{document\}")
_LABEL_MACROS = re.compile(
    r"\\(?:[cC]?ref|eqref|autoref|pageref|nameref|label|bibitem|cite\w*|nocite|index|glossary|"
    r"includegraphics|bibliographystyle|setcounter|addtocounter|vspace\*?|hspace\*?|hypersetup|"
    r"newtheorem\*?|theoremstyle|numberwithin|url|href)"
    r"(?:\[[^\]]*\])*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})+"
)
"""Macros whose arguments are labels, keys, paths or lengths: words in them never appear on the page."""
_URL = re.compile(r"(?:https?://|www\.|doi:|arXiv:)\S+|\b10\.\d{4,9}/\S+", re.I)
"""Link targets and identifiers, mostly in the bibliography: a PDF shows them as a link, not as words, and
whether a converter writes the target out is a formatting choice, not fidelity."""


def members(raw: bytes) -> dict[str, bytes]:
    """Files of an arXiv e-print: a tar archive (usually gzipped), a gzipped single file, or a bare file."""
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
            out: dict[str, bytes] = {}
            for member in tf.getmembers():
                if member.isfile():
                    handle = tf.extractfile(member)
                    if handle is not None:
                        out[member.name] = handle.read()
            return out
    except tarfile.ReadError:
        pass
    try:
        return {"main.tex": gzip.decompress(raw)}
    except (OSError, EOFError):
        return {"main.tex": raw}


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def tex_files(files: dict[str, bytes]) -> dict[str, str]:
    return {name: _decode(data) for name, data in files.items() if name.lower().endswith(TEX_SUFFIXES)}


def main_file(tex: dict[str, str]) -> str | None:
    """The file with `\\documentclass`; among several, the one that also begins the document, then the largest."""
    candidates = [n for n, t in tex.items() if re.search(r"^\s*\\documentclass", t, re.M)]
    if not candidates:
        return None
    with_body = [n for n in candidates if _BEGIN_DOCUMENT.search(tex[n])]
    pool = with_body or candidates
    return max(pool, key=lambda n: len(tex[n]))


def flatten(tex: dict[str, str], name: str, seen: set[str] | None = None) -> str:
    """`name` with comments removed and `\\input`/`\\include` files and the `.bbl` bibliography spliced in."""
    seen = seen if seen is not None else {name}
    text = _COMMENT.sub("", tex.get(name, ""))

    def splice(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        for candidate in (target, target + ".tex"):
            if candidate in tex and candidate not in seen:
                seen.add(candidate)
                return "\n" + flatten(tex, candidate, seen) + "\n"
        return ""

    text = _INPUT.sub(splice, text)
    bbls = [n for n in tex if n.lower().endswith(".bbl") and n not in seen]
    if bbls and _BIBLIOGRAPHY.search(text):
        seen.add(bbls[0])
        text = _BIBLIOGRAPHY.sub(lambda _m: "\n" + _COMMENT.sub("", tex[bbls[0]]) + "\n", text)
    return text


def body(text: str) -> str:
    """From `\\begin{document}` on (the preamble defines macros and theorem names that never print), with
    label-carrying macros removed."""
    match = _BEGIN_DOCUMENT.search(text)
    if match:
        text = text[match.end() :]
    return _LABEL_MACROS.sub(" ", text)


def latex_to_text(text: str) -> str:
    """Plain text of LaTeX via pylatexenc with math removed. Nodes pylatexenc cannot render (a macro missing an
    argument it expects) fall back to the text of their arguments instead of failing the whole paper."""
    from pylatexenc.latex2text import LatexNodes2Text

    class Tolerant(LatexNodes2Text):  # type: ignore[misc]
        def macro_node_to_text(self, node):  # type: ignore[no-untyped-def]
            try:
                return super().macro_node_to_text(node)
            except (IndexError, TypeError, AttributeError, ValueError):
                args = getattr(getattr(node, "nodeargd", None), "argnlist", None) or []
                return " " + " ".join(self.nodelist_to_text([a]) for a in args if a is not None) + " "

        def environment_node_to_text(self, node):  # type: ignore[no-untyped-def]
            try:
                return super().environment_node_to_text(node)
            except (IndexError, TypeError, AttributeError, ValueError):
                return self.nodelist_to_text(node.nodelist)

    converter = Tolerant(math_mode="remove", keep_comments=False, strict_latex_spaces=False)
    return str(converter.latex_to_text(text, tolerant_parsing=True))


def source_plain_text(raw: bytes) -> str | None:
    """Plain text of one e-print archive, or None when no file in it declares a document class."""
    tex = tex_files(members(raw))
    main = main_file(tex)
    if main is None:
        return None
    return _URL.sub(" ", latex_to_text(body(flatten(tex, main))))


def _cache_path(doc_id: str) -> Path:
    return arxiv_root() / "witness" / f"{doc_id}.source.json"


def source_text(doc_id: str, arxiv_id: str) -> str | None:
    """The paper's source as plain text, cached; None when the source was not fetched, the paper was submitted
    as PDF only (empty marker file), or the archive has no main file."""
    cache = _cache_path(doc_id)
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        text = data.get("text")
        return str(text) if text is not None else None
    src = arxiv_source_dir() / f"{arxiv_id}.src"
    if not src.exists():
        return None
    raw = src.read_bytes()
    text = source_plain_text(raw) if raw else None
    reason = None if text is not None else ("pdf-only" if not raw else "no-main-file")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"text": text, "reason": reason}, ensure_ascii=False), encoding="utf-8")
    return text
