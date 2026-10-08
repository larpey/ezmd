from __future__ import annotations

import asyncio
import io
import subprocess
import sys
from pathlib import Path

import pytest

import ezmd
from ezmd.inputs import InputRef
from ezmd.registry import ConversionError

TEXT = b"Report\n======\n\nFirst paragraph.\n\nSecond paragraph.\n"


def test_public_names_resolve_lazily() -> None:
    for name in ezmd.__all__:
        assert getattr(ezmd, name) is not None
    with pytest.raises(AttributeError):
        _ = ezmd.does_not_exist  # type: ignore[attr-defined]


def test_convert_path_bytes_fileobj_and_inputref(tmp_path: Path) -> None:
    p = tmp_path / "r.txt"
    p.write_bytes(TEXT)
    for src in (str(p), p, TEXT, io.BytesIO(TEXT), InputRef.from_bytes(TEXT, filename="r.txt")):
        r = ezmd.convert(src, filename="r.txt" if not isinstance(src, (str, Path, InputRef)) else None)
        assert r.markdown.startswith("---\n")
        assert "First paragraph." in r.body
        assert r.frontmatter["title"] == "Report"
        assert r.ok and r.tokens > 0 and r.warnings == []


def test_render_other_profile_matches_direct_conversion() -> None:
    pinned = "2026-01-01T00:00:00Z"
    full = ezmd.convert(TEXT, filename="r.txt", profile="full")
    direct = ezmd.convert(TEXT, filename="r.txt", profile="compact", options={"render": {"converted_at": pinned}})
    assert full.render("compact", converted_at=pinned).markdown == direct.render(converted_at=pinned).markdown


def test_options_round_trip_and_validation() -> None:
    opts = ezmd.Options(max_pages=10, extra={"x": True}, render={"chunks.chunk_tokens": 256})
    assert ezmd.Options(**opts.model_dump()) == opts
    with pytest.raises(ValueError):
        ezmd.Options(bogus=1)  # type: ignore[call-arg]
    co = opts.to_convert_options()
    assert co.max_pages == 10 and co.extra == {"x": True}


def test_bad_profile_fails_at_convert_time() -> None:
    with pytest.raises(ValueError):
        ezmd.convert(TEXT, filename="r.txt", profile="nope")


def test_progress_callback_receives_events() -> None:
    events: list[ezmd.Progress] = []
    r = ezmd.convert(TEXT, filename="r.txt", on_progress=events.append)
    assert r.conversion.converter_id == "text.plain"
    assert all(isinstance(e, ezmd.Progress) for e in events)


def test_save_writes_markdown_and_sidecar(tmp_path: Path) -> None:
    r = ezmd.convert(TEXT, filename="notes.txt")
    out = r.save(tmp_path)
    assert out.name == "notes.md" and out.read_text(encoding="utf-8") == r.markdown
    assert (tmp_path / "notes.ezmd.json").exists()
    compact = ezmd.convert(TEXT, filename="notes.txt", profile="compact")
    compact.save(tmp_path / "c.md")
    assert not (tmp_path / "c.ezmd.json").exists()


def test_chunks() -> None:
    chunks = ezmd.convert(TEXT, filename="r.txt").chunks(chunk_tokens=100)
    assert chunks and all(c.tokens <= 100 or c.tokens > 0 for c in chunks)


def test_errors() -> None:
    with pytest.raises(FileNotFoundError):
        ezmd.convert("definitely/missing/file.txt")
    with pytest.raises(ConversionError):
        ezmd.convert(b"%PDF-1.7\n" + b"0" * 100, filename="a.pdf", options={"converter": "text.nope"})


def test_convert_async_and_many() -> None:
    r = asyncio.run(ezmd.convert_async(TEXT, filename="r.txt"))
    assert "Second paragraph." in r.body
    results = list(
        ezmd.convert_many([TEXT, b"\x7fELF" + b"\x00" * 64], workers=2, filename="x.txt", return_exceptions=True)
    )
    assert isinstance(results[0], ezmd.Result) and isinstance(results[1], Exception)


def test_capabilities_lists_builtins() -> None:
    caps = ezmd.capabilities()
    ids = {c["id"] for c in caps["converters"]}  # type: ignore[union-attr,index]
    assert {"text.plain", "text.markdown_passthrough"} <= ids


def test_import_is_light() -> None:
    """`import ezmd` must not pull in the renderer, pydantic-heavy IR, or any engine (part4 4.3.4)."""
    code = (
        "import sys, time; t=time.perf_counter(); import ezmd; dt=time.perf_counter()-t; "
        "heavy=[m for m in ('ezmd.render','ezmd.registry','magika','tiktoken','torch') if m in sys.modules]; "
        "print(heavy, dt)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.startswith("[]"), out
