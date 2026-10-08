"""IR emission for repository packs (docs/spec/part2.md 8c steps 5 and 10)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from intomd.ir import CodeBlock, Document, Heading, InlineSpan, Paragraph, Provenance
from intomd_converters.code.budget import PackFile
from intomd_converters.code.collect import Collected
from intomd_converters.code.languages import is_code_name
from intomd_converters.code.tree import render_tree

__all__ = ["PackInfo", "emit_pack"]

_REASON_WORDS = {
    "gitignored": "ignored by .gitignore/.intomdignore",
    "default_excluded": "in default-excluded directories",
    "user_excluded": "excluded by include/exclude globs",
    "secret_file": "credential files",
    "binary": "binary",
    "minified": "minified or source maps",
    "too_large": "over the size limit",
}


@dataclass(frozen=True, slots=True)
class PackInfo:
    source: str
    name: str
    ref: str | None
    commit: str | None
    subpath: str | None
    root_label: str


def _heading(level: int, text: str, prov: Provenance, attrs: dict[str, str] | None = None) -> Heading:
    return Heading(level=level, spans=[InlineSpan(text=text)], provenance=prov, attrs=attrs or {})


def _summary(info: PackInfo, coll: Collected, files: list[PackFile]) -> str:
    live = [f for f in files if f.dropped is None]
    total_bytes = sum(f.size for f in live)
    total_tokens = sum(f.tokens for f in live)
    langs: Counter[str] = Counter()
    for e in coll.packed:
        if e.language and is_code_name(e.path):
            langs[e.language] += e.size
    parts = [f"{len(live):,} files packed ({total_bytes:,} source bytes, {total_tokens:,} tokens)."]
    if langs:
        total = sum(langs.values()) or 1
        mix = ", ".join(f"{lang} {round(100 * n / total)}%" for lang, n in langs.most_common(5))
        parts.append(f"Languages: {mix}.")
    if info.commit:
        parts.append(f"Commit {info.commit[:12]}.")
    if info.subpath:
        parts.append(f"Restricted to {info.subpath}/.")
    excluded = [f"{n:,} {_REASON_WORDS.get(r, r)}" for r, n in sorted(coll.reasons.items()) if n]
    if excluded:
        parts.append("Not packed: " + "; ".join(excluded) + ".")
    dropped = sum(1 for f in files if f.dropped)
    if dropped:
        parts.append(f"{dropped:,} files left out to fit the token budget (still listed in the tree).")
    return " ".join(parts)


def emit_pack(doc: Document, info: PackInfo, coll: Collected, files: list[PackFile]) -> None:
    src = info.source
    root = Provenance(source=src, path=".")
    title = f"{info.name} at {info.ref}" if info.ref else info.name
    doc.blocks.append(_heading(1, title, root))
    doc.blocks.append(Paragraph(spans=[InlineSpan(text=_summary(info, coll, files))], provenance=root.model_copy()))
    doc.blocks.append(_heading(2, "Directory tree", root.model_copy()))
    dropped = {f.path for f in files if f.dropped}
    entries = [(e.path, "omitted: token budget" if e.path in dropped else (e.excluded or "")) for e in coll.files]
    tree = render_tree(info.root_label, entries, coll.excluded_dirs)
    doc.blocks.append(CodeBlock(code=tree, language="text", provenance=root.model_copy()))
    doc.blocks.append(_heading(2, "Files", root.model_copy()))
    for f in files:
        if f.dropped is not None:
            continue
        prov = Provenance(source=src, path=f.path, line_start=1, line_end=max(1, f.lines))
        label = f"{f.path} (signatures only)" if f.compressed else f.path
        attrs = {
            "tokens": str(f.tokens),
            "bytes": str(f.size),
            "packed_bytes": str(len(f.text.encode("utf-8"))),
            "language": f.language or "text",
        }
        doc.blocks.append(_heading(3, label, prov, attrs))
        code = f.text if f.note is None else f"{f.text}\n{f.note}"
        doc.blocks.append(
            CodeBlock(code=code, language=f.language or "text", filename=f.path, provenance=prov.model_copy())
        )
