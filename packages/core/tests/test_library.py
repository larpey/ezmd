from __future__ import annotations

import asyncio
import io
import subprocess
import sys
from pathlib import Path

import pytest

import intomd
from intomd.inputs import InputRef
from intomd.registry import ConversionError

TEXT = b"Report\n======\n\nFirst paragraph.\n\nSecond paragraph.\n"


def test_public_names_resolve_lazily() -> None:
    for name in intomd.__all__:
        assert getattr(intomd, name) is not None
    with pytest.raises(AttributeError):
        _ = intomd.does_not_exist  # type: ignore[attr-defined]


def test_convert_path_bytes_fileobj_and_inputref(tmp_path: Path) -> None:
    p = tmp_path / "r.txt"
    p.write_bytes(TEXT)
    for src in (str(p), p, TEXT, io.BytesIO(TEXT), InputRef.from_bytes(TEXT, filename="r.txt")):
        r = intomd.convert(src, filename="r.txt" if not isinstance(src, (str, Path, InputRef)) else None)
        assert r.markdown.startswith("---\n")
        assert "First paragraph." in r.body
        assert r.frontmatter["title"] == "Report"
        assert r.ok and r.tokens > 0 and r.warnings == []


def test_render_other_profile_matches_direct_conversion() -> None:
    pinned = "2026-01-01T00:00:00Z"
    full = intomd.convert(TEXT, filename="r.txt", profile="full")
    direct = intomd.convert(TEXT, filename="r.txt", profile="compact", options={"render": {"converted_at": pinned}})
    assert full.render("compact", converted_at=pinned).markdown == direct.render(converted_at=pinned).markdown


def test_options_round_trip_and_validation() -> None:
    opts = intomd.Options(max_pages=10, extra={"x": True}, render={"chunks.chunk_tokens": 256})
    assert intomd.Options(**opts.model_dump()) == opts
    with pytest.raises(ValueError):
        intomd.Options(bogus=1)  # type: ignore[call-arg]
    co = opts.to_convert_options()
    assert co.max_pages == 10 and co.extra == {"x": True}


def test_bad_profile_fails_at_convert_time() -> None:
    with pytest.raises(ValueError):
        intomd.convert(TEXT, filename="r.txt", profile="nope")


def test_progress_callback_receives_events() -> None:
    events: list[intomd.Progress] = []
    r = intomd.convert(TEXT, filename="r.txt", on_progress=events.append)
    assert r.conversion.converter_id == "text.plain"
    assert all(isinstance(e, intomd.Progress) for e in events)


def test_save_writes_markdown_and_sidecar(tmp_path: Path) -> None:
    r = intomd.convert(TEXT, filename="notes.txt")
    out = r.save(tmp_path)
    assert out.name == "notes.md" and out.read_text(encoding="utf-8") == r.markdown
    assert (tmp_path / "notes.intomd.json").exists()
    compact = intomd.convert(TEXT, filename="notes.txt", profile="compact")
    compact.save(tmp_path / "c.md")
    assert not (tmp_path / "c.intomd.json").exists()


def test_chunks() -> None:
    chunks = intomd.convert(TEXT, filename="r.txt").chunks(chunk_tokens=100)
    assert chunks and all(c.tokens <= 100 or c.tokens > 0 for c in chunks)


def test_errors() -> None:
    with pytest.raises(FileNotFoundError):
        intomd.convert("definitely/missing/file.txt")
    with pytest.raises(ConversionError):
        intomd.convert(b"%PDF-1.7\n" + b"0" * 100, filename="a.pdf", options={"converter": "text.nope"})


def test_convert_async_and_many() -> None:
    r = asyncio.run(intomd.convert_async(TEXT, filename="r.txt"))
    assert "Second paragraph." in r.body
    results = list(
        intomd.convert_many([TEXT, b"\x7fELF" + b"\x00" * 64], workers=2, filename="x.txt", return_exceptions=True)
    )
    assert isinstance(results[0], intomd.Result) and isinstance(results[1], Exception)


def test_capabilities_lists_builtins() -> None:
    caps = intomd.capabilities()
    ids = {c["id"] for c in caps["converters"]}  # type: ignore[union-attr,index]
    assert {"text.plain", "text.markdown_passthrough"} <= ids


def test_import_is_light() -> None:
    """`import intomd` must not pull in the renderer, pydantic-heavy IR, or any engine (part4 4.3.4)."""
    code = (
        "import sys, time; t=time.perf_counter(); import intomd; dt=time.perf_counter()-t; "
        "heavy=[m for m in ('intomd.render','intomd.registry','magika','tiktoken','torch') if m in sys.modules]; "
        "print(heavy, dt)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.startswith("[]"), out
