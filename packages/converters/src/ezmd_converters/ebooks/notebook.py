"""documents.ipynb: Jupyter notebooks to the IR (docs/spec/part2.md section 4c steps 14-17).

A stdlib JSON walker (no nbconvert). Markdown cells go through `text.markdown.parse_markdown`; code cells
become CodeBlocks in the kernel language; outputs follow as CodeBlocks fenced `output` (streams, text
results, and ANSI-stripped error tracebacks, with `attrs.role` = output | error), Markdown results through the
Markdown parser, HTML results (DataFrames) through the XHTML walker, and images as Image blocks. Each
output is capped at `text.notebook_max_output_chars` characters. Provenance `path` is `cells[i]` or
`cells[i].outputs[j]`, with `source_id` set to the cell id when present.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from pathlib import Path
from typing import Any

from ezmd.context import Limits
from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef
from ezmd.ir import (
    Block,
    CodeBlock,
    Document,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    ListBlock,
    ListItem,
    Metadata,
    Paragraph,
    Provenance,
    Quote,
    Raw,
    SourceType,
    Table,
    Warning,
)
from ezmd.ir import WarningKind as W
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.ebooks.mathspans import apply_math
from ezmd_converters.ebooks.xhtml import WalkContext, Walker, find_body, parse_document
from ezmd_converters.text.markdown import parse_markdown
from ezmd_converters.text.plain import decode_text

NOTEBOOK_MIMES = ("application/x-ipynb+json", "application/x-ipynb")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
DEFAULT_MAX_OUTPUT_CHARS = 5000
MAX_IMAGE_B64 = 20 * 1024 * 1024
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/svg+xml": ".svg"}
HIDE_TAGS = frozenset({"hide-cell", "remove-cell", "hide_cell", "remove_cell"})


def _text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(v for v in value if isinstance(v, str))
    return value if isinstance(value, str) else ""


class NotebookConverter:
    id = "documents.ipynb"
    family = "documents"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = NOTEBOOK_MIMES
    limits = Limits(max_chars=DEFAULT_MAX_OUTPUT_CHARS, timeout_s=120.0)

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if mime in NOTEBOOK_MIMES:
            return 1.0
        if ref.detected is not None and ref.detected.magika_label in ("ipynb", "jupyter"):
            # Magika labels notebooks `ipynb` but reports application/json as their mime.
            return 1.0
        if mime in ("application/json", "text/plain", "application/octet-stream") and ref.display.lower().endswith(
            ".ipynb"
        ):
            return 0.95
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raw = ref.read()
        meta = Metadata(source=ref.display, source_type=SourceType.NOTEBOOK, mime="application/x-ipynb+json")
        doc = Document(metadata=meta)
        text, _enc, _uncertain = decode_text(raw)
        try:
            nb = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as e:
            raise ConversionError(
                f"{ref.display}: not JSON: {e}", user_message="The notebook is not valid JSON."
            ) from e
        if not isinstance(nb, dict):
            raise ConversionError(f"{ref.display}: notebook root is not an object", user_message="Not a notebook.")
        return _Builder(doc, nb, ref.display, options).run()


class _Builder:
    def __init__(self, doc: Document, nb: dict[str, Any], source: str, options: ConvertOptions) -> None:
        self.doc = doc
        self.nb = nb
        self.source = source
        self.options = options
        self.stats = CleanStats()
        self.truncated = 0
        self.hidden = 0
        self.image_dir = Path(options.image_dir) if options.image_dir and options.extract_images else None
        mode = options.extra.get("text.notebook_outputs", "all")
        self.outputs = mode if mode in ("all", "text", "off") else "all"
        cap = options.extra.get("text.notebook_max_output_chars")
        limit = options.ctx.limits.max_chars or DEFAULT_MAX_OUTPUT_CHARS
        self.max_chars = cap if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0 else limit
        self.honor_tags = options.extra.get("text.notebook_honor_tags", False) is True

    def run(self) -> Document:
        nb, doc = self.nb, self.doc
        cells = self._cells()
        md = nb.get("metadata") if isinstance(nb.get("metadata"), dict) else {}
        assert isinstance(md, dict)
        self.language = _kernel_language(md)
        doc.metadata.extra.update({"kernel_language": self.language, "nbformat": _int(nb.get("nbformat"))})
        if isinstance(md.get("title"), str):
            doc.metadata.title = clean_text(md["title"], self.stats)
        for i, cell in enumerate(cells):
            self.options.ctx.check_deadline()
            if i % 25 == 0:
                self.options.ctx.progress("notebook", i / max(len(cells), 1), f"cell {i}")
            if not isinstance(cell, dict):
                continue
            tags = cell.get("metadata", {}).get("tags", []) if isinstance(cell.get("metadata"), dict) else []
            if self.honor_tags and isinstance(tags, list) and HIDE_TAGS & {t for t in tags if isinstance(t, str)}:
                self.hidden += 1
                continue
            doc.blocks.extend(self._cell(i, cell))
        self._finish()
        return doc.finalize()

    def _cells(self) -> list[Any]:
        nb = self.nb
        cells = nb.get("cells")
        if isinstance(cells, list) and _int(nb.get("nbformat")) >= 4:
            return cells
        worksheets = nb.get("worksheets")
        if isinstance(worksheets, list) and worksheets and isinstance(worksheets[0], dict):
            cells = worksheets[0].get("cells")
        self.doc.warnings.append(
            Warning(
                kind=W.NOTEBOOK_INVALID,
                message="The notebook does not follow nbformat 4; it was read best-effort.",
                detail={"nbformat": _int(nb.get("nbformat"))},
            )
        )
        return cells if isinstance(cells, list) else []

    def _prov(self, path: str, cell: dict[str, Any], **kw: Any) -> Provenance:
        cid = cell.get("id")
        return Provenance(source=self.source, path=path, source_id=cid if isinstance(cid, str) else None, **kw)

    def _cell(self, i: int, cell: dict[str, Any]) -> list[Block]:
        kind = cell.get("cell_type")
        src = clean_text(_text(cell.get("source", cell.get("input"))), self.stats)
        path = f"cells[{i}]"
        if kind == "markdown" or kind == "heading":
            if kind == "heading":
                src = "#" * max(1, min(6, _int(cell.get("level")) or 1)) + " " + src
            blocks = self._markdown(src, path, cell, f"c{i}")
            return self._attachments(blocks, cell, i)
        if kind == "raw":
            if not src.strip():
                return []
            md = cell.get("metadata") if isinstance(cell.get("metadata"), dict) else {}
            fmt = (md or {}).get("format") or (md or {}).get("raw_mimetype") or ""
            return [Raw(format=raw_language(str(fmt)), content=src, provenance=self._prov(path, cell))]
        if kind != "code":
            return []
        out: list[Block] = []
        count = cell.get("execution_count", cell.get("prompt_number"))
        attrs = {"execution_count": str(count)} if isinstance(count, int) else {}
        if src.strip():
            lines = src.count("\n") + 1
            out.append(
                CodeBlock(
                    code=src.rstrip("\n"),
                    language=self.language,
                    attrs=attrs,
                    provenance=self._prov(path, cell, line_start=1, line_end=lines),
                )
            )
        if self.outputs != "off":
            outputs = cell.get("outputs")
            out.extend(self._outputs(i, cell, outputs if isinstance(outputs, list) else []))
        return out

    def _outputs(self, i: int, cell: dict[str, Any], outputs: list[Any]) -> list[Block]:
        """Outputs of one code cell. Consecutive chunks of the same stream are concatenated raw, the way
        Jupyter front ends display them (`print(..., end="")` and progress output continue mid-line), and
        then cleaned, capped and stripped once, keeping the first chunk's provenance."""
        out: list[Block] = []
        run: tuple[int, str, list[str]] | None = None  # (first output index, stream name, raw chunks)

        def flush() -> None:
            if run is not None:
                out.extend(self._stream_block(i, run[0], cell, run[1], "".join(run[2])))

        for j, output in enumerate(outputs):
            if not isinstance(output, dict):
                continue
            name = output.get("name")
            if output.get("output_type") == "stream" and isinstance(name, str) and "text" in output:
                if run is not None and run[1] == name:
                    run[2].append(_text(output.get("text")))
                else:
                    flush()
                    run = (j, name, [_text(output.get("text"))])
                continue
            flush()
            run = None
            out.extend(self._output(i, j, cell, output))
        flush()
        return out

    def _stream_block(self, i: int, j: int, cell: dict[str, Any], name: str, raw: str) -> list[Block]:
        text = self._cap(raw).rstrip(chr(10))
        if not text.strip():
            return []
        attrs = {"role": "output", "stream": name}
        prov = self._prov(f"cells[{i}].outputs[{j}]", cell)
        return [CodeBlock(code=text, language="output", attrs=attrs, provenance=prov)]

    def _markdown(self, src: str, path: str, cell: dict[str, Any], prefix: str) -> list[Block]:
        blocks, _extras = parse_markdown(src, self.source)
        for b in blocks:
            b.provenance = self._prov(path, cell, line_start=b.provenance.line_start, line_end=b.provenance.line_end)
        return apply_math(_rename_footnotes(blocks, prefix))

    def _attachments(self, blocks: list[Block], cell: dict[str, Any], i: int) -> list[Block]:
        att = cell.get("attachments")
        if not isinstance(att, dict):
            return blocks
        for b in blocks:
            if isinstance(b, Image) and b.ref.startswith("attachment:"):
                name = b.ref.split(":", 1)[1]
                bundle = att.get(name)
                if isinstance(bundle, dict):
                    ref = self._save_image(bundle, f"cell{i}-{name}")
                    if ref is not None:
                        b.ref, b.mime = ref
        return blocks

    def _output(self, i: int, j: int, cell: dict[str, Any], output: dict[str, Any]) -> list[Block]:
        path = f"cells[{i}].outputs[{j}]"
        kind = output.get("output_type")
        prov = self._prov(path, cell)
        if kind in ("stream", "pyout", "pyerr") and "text" in output:
            text = self._cap(_text(output.get("text"))).rstrip("\n")
            name = output.get("name")
            attrs = {"role": "output", "stream": name} if isinstance(name, str) else {"role": "output"}
            return [CodeBlock(code=text, language="output", attrs=attrs, provenance=prov)] if text.strip() else []
        if kind == "error":
            tb = output.get("traceback")
            text = _text([f"{t}\n" for t in tb if isinstance(t, str)]) if isinstance(tb, list) else ""
            if not text.strip():
                text = f"{output.get('ename', 'Error')}: {output.get('evalue', '')}"
            text = self._cap(_ANSI.sub("", text)).rstrip("\n")
            return [CodeBlock(code=text, language="output", attrs={"role": "error"}, provenance=prov)]
        if kind in ("execute_result", "display_data"):
            data = output.get("data")
            if isinstance(data, dict):
                return self._mime_bundle(data, path, cell, prov, f"c{i}o{j}")
        return []

    def _mime_bundle(
        self, data: dict[str, Any], path: str, cell: dict[str, Any], prov: Provenance, prefix: str
    ) -> list[Block]:
        rich = self.outputs == "all"
        if rich and "text/markdown" in data:
            return self._markdown(self._cap(clean_text(_text(data["text/markdown"]), self.stats)), path, cell, prefix)
        if rich and "text/html" in data:
            blocks = self._html(_text(data["text/html"]), prov)
            if blocks:
                return blocks
        if rich:
            for mime, ext in IMAGE_TYPES.items():
                if mime in data:
                    saved = self._save_image({mime: data[mime]}, f"{prefix}{ext}")
                    if saved is not None:
                        alt = clean_text(_text(data.get("text/plain")), self.stats).strip()[:200] or None
                        if alt and alt.startswith("<") and alt.endswith(">"):
                            alt = None  # a repr such as <Figure size 400x300 with 1 Axes> is not a description
                        return [Image(ref=saved[0], mime=saved[1], alt=alt, attrs={"role": "output"}, provenance=prov)]
        if "text/plain" in data:
            text = self._cap(clean_text(_text(data["text/plain"]), self.stats))
            if text.strip():
                return [CodeBlock(code=text.rstrip("\n"), language="output", attrs={"role": "output"}, provenance=prov)]
        return []

    def _html(self, markup: str, prov: Provenance) -> list[Block]:
        if not markup.strip() or len(markup) > 4 * self.max_chars + 200_000:
            return []
        root = parse_document(markup.encode("utf-8"), html_mode=True)
        if root is None:
            return []
        ctx = WalkContext(source=self.source, path=prov.path, stats=self.stats)
        blocks = Walker(ctx).blocks(find_body(root))
        self.hidden += ctx.hidden_removed
        for b in blocks:
            b.provenance = prov.model_copy()
        return blocks

    def _save_image(self, bundle: dict[str, Any], name: str) -> tuple[str, str] | None:
        for mime, ext in IMAGE_TYPES.items():
            if mime not in bundle:
                continue
            payload = _text(bundle[mime])
            if len(payload) > MAX_IMAGE_B64:
                self.doc.warnings.append(
                    Warning(kind=W.IMAGE_TOO_LARGE, message=f"Notebook image {name} is too large and was skipped.")
                )
                return None
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
            if not safe.lower().endswith(ext):
                safe += ext
            if self.image_dir is not None:
                try:
                    raw = (
                        payload.encode("utf-8")
                        if mime == "image/svg+xml"
                        else base64.b64decode(payload, validate=False)
                    )
                except (binascii.Error, ValueError):
                    return None
                target = self.image_dir / "images" / safe
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            return f"images/{safe}", mime
        return None

    def _cap(self, text: str) -> str:
        text = clean_text(_ANSI.sub("", text), self.stats)
        if len(text) <= self.max_chars:
            return text
        self.truncated += 1
        return text[: self.max_chars].rstrip() + "\n... [output truncated]"

    def _finish(self) -> None:
        doc = self.doc
        if self.truncated:
            doc.warnings.append(
                Warning(
                    kind=W.TRUNCATED,
                    message=f"{self.truncated} notebook output(s) were cut at {self.max_chars} characters.",
                    count=self.truncated,
                    detail={"reason": "notebook_output", "max_chars": self.max_chars},
                )
            )
        if self.hidden:
            doc.warnings.append(
                Warning(
                    kind=W.REMOVED_HIDDEN_ELEMENTS,
                    severity="info",
                    message=f"{self.hidden} hidden cells or elements were left out.",
                    count=self.hidden,
                    detail={"hidden_elements": self.hidden, "invisible_chars": 0},
                )
            )
        if self.stats.total:
            doc.warnings.append(
                Warning(
                    kind=W.REMOVED_HIDDEN_ELEMENTS,
                    severity="info",
                    message=f"Removed {self.stats.total} control or invisible characters.",
                    count=self.stats.total,
                    detail={
                        "invisible_chars": self.stats.total,
                        "control": self.stats.control,
                        "invisible": self.stats.invisible,
                        "surrogates": self.stats.surrogates,
                    },
                )
            )
        if not doc.blocks:
            doc.warnings.append(Warning(kind=W.EXTRACTION_EMPTY, message="The notebook has no cells with content."))
        if doc.metadata.title is None:
            first = next((b for b in doc.blocks if isinstance(b, Heading)), None)
            if first is not None:
                doc.metadata.title = "".join(s.text for s in first.spans)


RAW_LANGUAGES = {
    "text/x-rst": "rst",
    "text/restructuredtext": "rst",
    "text/latex": "latex",
    "text/x-latex": "latex",
    "text/html": "html",
    "text/markdown": "markdown",
    "text/x-python": "python",
    "text/asciidoc": "asciidoc",
    "application/json": "json",
    "text/plain": "text",
}


def raw_language(fmt: str) -> str:
    """A fence language name for a raw cell's `format`/`raw_mimetype` (`text/x-rst` -> `rst`)."""
    fmt = fmt.strip().lower()
    if not fmt:
        return "text"
    if fmt in RAW_LANGUAGES:
        return RAW_LANGUAGES[fmt]
    name = fmt.split("/", 1)[-1].removeprefix("x-")
    return re.sub(r"[^a-z0-9+#.-]+", "-", name).strip("-") or "text"


def _kernel_language(md: dict[str, Any]) -> str:
    for key in ("kernelspec", "language_info"):
        section = md.get(key)
        if isinstance(section, dict):
            lang = section.get("language") or section.get("name")
            if isinstance(lang, str) and lang.strip() and re.fullmatch(r"[A-Za-z0-9_+#.-]{1,32}", lang.strip()):
                return lang.strip().lower()
    return "python"


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _rename_footnotes(blocks: list[Block], prefix: str) -> list[Block]:
    """Footnote ids from parse_markdown are `fn-<label>`; make them unique per cell (`fn-<prefix>-<label>`)."""
    mapping: dict[str, str] = {}
    for b in blocks:
        if isinstance(b, Footnote) and b.id.startswith("fn-"):
            mapping[b.id] = f"fn-{prefix}-{b.id[3:]}"
            b.id = mapping[b.id]
    if not mapping:
        return blocks

    def fix(spans: list[InlineSpan]) -> None:
        for s in spans:
            if s.footnote_ref in mapping:
                s.footnote_ref = mapping[s.footnote_ref]

    def fix_items(items: list[ListItem]) -> None:
        for it in items:
            fix(it.spans)
            fix_items(it.children)

    for b in blocks:
        if isinstance(b, Heading | Paragraph | Quote | Footnote):
            fix(b.spans)
        elif isinstance(b, ListBlock):
            fix_items(b.items)
        elif isinstance(b, Table):
            for c in b.cells:
                fix(c.spans)
    return blocks
