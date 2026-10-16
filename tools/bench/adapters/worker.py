"""Benchmark worker: runs inside one tool's isolated environment and converts documents on request.

    <tool venv python> -I worker.py --tool <name> [--pandoc PATH]

Protocol (one JSON object per line). The worker keeps the original stdout only for protocol messages and
points fd 1 at stderr, so library prints (and C-level writes) cannot corrupt the stream.

    worker -> {"ready": true, "tool": ..., "version": ..., "startup_seconds": ...}
    harness -> {"id": ..., "input": <path>, "output": <path>}
    worker -> {"id": ..., "ok": true, "seconds": ...}  |  {"id": ..., "ok": false, "error_class": ..., "error": ...}

The harness owns timeouts and memory sampling; a timed-out or crashed worker is killed and restarted. This file
must only use the standard library at module level: it runs under each tool's interpreter, not the repo's.
Each adapter calls the tool's documented default entry point with default options.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

Convert = Callable[[Path], str]


def _ezmd() -> tuple[str, Convert]:
    import ezmd

    def convert(path: Path) -> str:
        return str(ezmd.convert(str(path)).markdown)

    return metadata.version("ezmd"), convert


def _markitdown() -> tuple[str, Convert]:
    from markitdown import MarkItDown

    md = MarkItDown()

    def convert(path: Path) -> str:
        return str(md.convert(str(path)).text_content)

    return metadata.version("markitdown"), convert


def _docling() -> tuple[str, Convert]:
    from docling.document_converter import DocumentConverter

    conv = DocumentConverter()

    def convert(path: Path) -> str:
        return str(conv.convert(str(path)).document.export_to_markdown())

    return metadata.version("docling"), convert


def _marker() -> tuple[str, Convert]:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered

    conv = PdfConverter(artifact_dict=create_model_dict())

    def convert(path: Path) -> str:
        text, _, _ = text_from_rendered(conv(str(path)))
        return str(text)

    return metadata.version("marker-pdf"), convert


def _mineru() -> tuple[str, Convert]:
    from mineru.parser import parse

    def convert(path: Path) -> str:
        return str(parse(str(path)).markdown())

    return metadata.version("mineru"), convert


def _pymupdf4llm() -> tuple[str, Convert]:
    import pymupdf4llm

    def convert(path: Path) -> str:
        return str(pymupdf4llm.to_markdown(str(path)))

    return metadata.version("pymupdf4llm"), convert


def _unstructured() -> tuple[str, Convert]:
    from unstructured.partition.auto import partition
    from unstructured.staging.base import elements_to_md

    def convert(path: Path) -> str:
        return str(elements_to_md(partition(filename=str(path))))

    return metadata.version("unstructured"), convert


def _trafilatura() -> tuple[str, Convert]:
    import trafilatura

    def convert(path: Path) -> str:
        html = path.read_bytes()
        out = trafilatura.extract(html, output_format="markdown")
        if out is None:
            raise ValueError("trafilatura extracted nothing")
        return str(out)

    return metadata.version("trafilatura"), convert


def _pandoc(binary: str) -> tuple[str, Convert]:
    exe = binary or shutil.which("pandoc") or "pandoc"
    first = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]

    def convert(path: Path) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.md"
            proc = subprocess.run([exe, str(path), "-t", "gfm", "-o", str(out)], capture_output=True, timeout=600)
            if proc.returncode != 0:
                raise RuntimeError(f"pandoc exit {proc.returncode}: {proc.stderr.decode(errors='replace')[:1000]}")
            return out.read_text(encoding="utf-8")

    return first.split()[-1], convert


ADAPTERS: dict[str, Callable[[], tuple[str, Convert]]] = {
    "ezmd_adapter": _ezmd,
    "markitdown_adapter": _markitdown,
    "docling_adapter": _docling,
    "marker_adapter": _marker,
    "mineru_adapter": _mineru,
    "pymupdf4llm_adapter": _pymupdf4llm,
    "unstructured_adapter": _unstructured,
    "trafilatura_adapter": _trafilatura,
}


def _protocol_stream() -> object:
    """Duplicate the real stdout for protocol messages and send fd 1 (and sys.stdout) to stderr."""
    proto_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(proto_fd, "w", encoding="utf-8", buffering=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--pandoc", default="")
    ap.add_argument("--warmup", default="", help="convert this file once before reporting ready")
    args = ap.parse_args()
    proto = _protocol_stream()

    def send(msg: dict[str, object]) -> None:
        proto.write(json.dumps(msg) + "\n")  # type: ignore[attr-defined]
        proto.flush()  # type: ignore[attr-defined]

    start = time.perf_counter()
    try:
        version, convert = _pandoc(args.pandoc) if args.adapter == "pandoc_adapter" else ADAPTERS[args.adapter]()
    except Exception as exc:
        send({"ready": False, "error_class": type(exc).__name__, "error": str(exc)[:2000]})
        return 1
    warmup_error = None
    if args.warmup:
        try:
            convert(Path(args.warmup))
        except Exception as exc:
            traceback.print_exc()
            warmup_error = f"{type(exc).__name__}: {exc}"[:500]
    send(
        {
            "ready": True,
            "warmup_error": warmup_error,
            "adapter": args.adapter,
            "version": version,
            "startup_seconds": time.perf_counter() - start,
        }
    )
    for line in sys.stdin:
        if not line.strip():
            continue
        job = json.loads(line)
        t0 = time.perf_counter()
        try:
            text = convert(Path(job["input"]))
            out = Path(job["output"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8", newline="\n")
            send({"id": job["id"], "ok": True, "seconds": time.perf_counter() - t0, "chars": len(text)})
        except Exception as exc:
            traceback.print_exc()
            send(
                {
                    "id": job["id"],
                    "ok": False,
                    "seconds": time.perf_counter() - t0,
                    "error_class": type(exc).__name__,
                    "error": str(exc)[:2000],
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
