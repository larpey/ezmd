from __future__ import annotations

import pytest

from intomd.detect import detect
from intomd.inputs import Detected, InputRef
from intomd.ir import CodeBlock, Document, Heading, ListBlock, WarningKind
from intomd.pipeline import convert_ref
from intomd.registry import ConversionError, ConverterRegistry, ConvertOptions
from intomd_converters.code import CHAINS
from intomd_converters.code.languages import language_for, shebang
from intomd_converters.code.signatures import outline, signatures
from intomd_converters.code.source_file import SourceFileConverter
from intomd_converters.text.plain import PlainTextConverter

PY = b'import os\n\nLIMIT = 3\n\n\ndef add(a: int, b: int) -> int:\n    """Add."""\n    return a + b\n'
GO = b'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("hi")\n}\n'
TS = b"export function f(x: number): string {\n  return String(x);\n}\ninterface A { b: string }\n"
RS = b'fn main() {\n    println!("hi");\n}\n'


def _ref(data: bytes, name: str, mime: str | None = None) -> InputRef:
    ref = InputRef.from_bytes(data, filename=name)
    if mime is None:
        detect(ref)
    else:
        ref.detected = Detected(mime=mime, extension=None, confidence=1.0)
    return ref


def _convert(data: bytes, name: str, mime: str | None = None, **extra: str | int | bool) -> Document:
    return SourceFileConverter().convert(_ref(data, name, mime), ConvertOptions(extra=dict(extra)))


def _last_code(doc: Document) -> str:
    block = doc.blocks[-1]
    assert isinstance(block, CodeBlock)
    return block.code


@pytest.mark.parametrize(("data", "name"), [(PY, "a.py"), (GO, "main.go"), (TS, "a.ts")])
def test_detected_code_files_reach_source_file(data: bytes, name: str) -> None:
    ref = InputRef.from_bytes(data, filename=name)
    result = convert_ref(ref)
    assert result.converter_id == "code.source_file"
    code = [b for b in result.document.blocks if isinstance(b, CodeBlock)]
    assert code and code[0].filename == name and code[0].language is not None


@pytest.mark.parametrize(("data", "name"), [(PY, "a.py"), (GO, "main.go"), (TS, "a.ts"), (RS, "main.rs")])
def test_text_plain_code_outranks_text_plain_without_a_pinned_chain(data: bytes, name: str) -> None:
    """With no chain pinning text/plain, confidence sorting picks code.source_file (0.95 > 0.9)."""
    reg = ConverterRegistry()
    reg.register(PlainTextConverter())
    reg.register(SourceFileConverter())
    ref = _ref(data, name, "text/plain")
    cands = reg.candidates(ref)
    assert cands[0][1].id == "code.source_file" and cands[0][0] > 0.9
    assert reg.convert(ref, ConvertOptions()).converter_id == "code.source_file"


def test_code_chain_falls_back_to_text_plain() -> None:
    reg = ConverterRegistry()
    reg.register(PlainTextConverter())
    reg.register(SourceFileConverter())
    for mime, ids in CHAINS.items():
        reg.set_chain(mime, ids)
    ref = _ref(PY, "a.py", "text/x-python")
    assert [c.id for _s, c in reg.candidates(ref)] == ["code.source_file", "text.plain"]
    assert "text/plain" not in CHAINS and "text/markdown" not in CHAINS and "application/zip" not in CHAINS


@pytest.mark.parametrize(
    ("name", "mime", "score"),
    [
        ("a.py", "text/x-python", 1.0),
        ("main.go", "text/plain", 0.95),
        ("notes.txt", "text/plain", 0.0),
        ("README.md", "text/markdown", 0.0),
        ("data.json", "application/json", 0.0),
    ],
)
def test_can_handle(name: str, mime: str, score: float) -> None:
    assert SourceFileConverter().can_handle(_ref(b"x", name, mime)) == score


def test_source_file_blocks_and_metadata() -> None:
    doc = _convert(PY, "calc.py")
    blocks = doc.blocks
    h, code = blocks
    assert isinstance(h, Heading) and h.spans[0].text == "calc.py"
    assert isinstance(code, CodeBlock) and code.code == PY.decode().rstrip("\n") and code.language == "python"
    assert (code.provenance.path, code.provenance.line_start, code.provenance.line_end) == ("calc.py", 1, 8)
    extra = doc.metadata.extra
    assert extra["language"] == "python" and extra["lines"] == 8 and int(str(extra["tokens"])) > 0


def test_signatures_only_option() -> None:
    doc = _convert(PY, "calc.py", signatures_only=True)
    blocks = doc.blocks
    assert isinstance(blocks[0], Heading) and blocks[0].spans[0].text == "calc.py (signatures only)"
    code = _last_code(doc)
    assert "def add(a: int, b: int) -> int:" in code and '"""Add."""' in code and "return a + b" not in code
    assert "LIMIT = 3" in code and "import os" in code


def test_outline_auto_for_long_files() -> None:
    src = "\n".join(f"def f{i}():\n    return {i}\n" for i in range(260)).encode()
    blocks = _convert(src, "long.py").blocks
    lists = [b for b in blocks if isinstance(b, ListBlock)]
    assert lists and lists[0].items[0].spans[0].text == "f0 (function) line 1"
    short = _convert(PY, "calc.py").blocks
    assert not any(isinstance(b, ListBlock) for b in short)


def test_secret_redacted_and_warned() -> None:
    src = b'API_SECRET_KEY = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"\nprint(1)\n'
    doc = _convert(src, "s.py")
    code = _last_code(doc)
    assert "9f8e7d6c5b4a" not in code and "[REDACTED:generic_secret]" in code
    warn = [w for w in doc.warnings if w.kind == WarningKind.SECRET_REDACTED]
    assert warn and warn[0].count == 1 and warn[0].detail["rule.generic_secret"] == 1


def test_trojan_source_characters_removed() -> None:
    bidi = chr(0x202E).encode()
    doc = _convert(b"x = 1  # " + bidi + b"evil\n", "t.py")
    assert chr(0x202E) not in _last_code(doc)
    assert any(w.kind == WarningKind.REMOVED_HIDDEN_ELEMENTS for w in doc.warnings)


def test_binary_and_empty_inputs() -> None:
    with pytest.raises(ConversionError):
        _convert(bytes([0, 1, 2, 0, 0, 0]) * 10, "x.py", "text/x-python")
    doc = _convert(b"  \n", "e.py", "text/x-python")
    assert doc.blocks == [] and doc.warnings[0].kind == WarningKind.EXTRACTION_EMPTY


def test_utf16_source_decodes() -> None:
    doc = _convert("x = 'café'\n".encode("utf-16"), "u.py", "text/x-python")
    assert _last_code(doc) == "x = 'café'"


def test_language_and_shebang() -> None:
    assert language_for("Dockerfile") == "dockerfile"
    assert language_for("tool", "#!/usr/bin/env python3\nprint(1)") == "python"
    assert language_for("run", "#!/bin/bash\necho") == "bash"
    assert language_for("x", "", "text/x-golang") == "go"
    assert shebang("#!/usr/bin/env -S node --flag\n") == "node"
    assert language_for("noext", "plain words") is None


def test_regex_signatures_and_outline_for_other_languages() -> None:
    go = GO.decode()
    sig = signatures(go, "go")
    assert "package main" in sig and "func main() {" in sig
    syms = outline(TS.decode(), "typescript")
    assert [(s.name, s.kind) for s in syms] == [("f", "function"), ("A", "interface")]


def test_python_signatures_edge_cases() -> None:
    src = (
        "class A: pass\n\n"
        "def one(): return 1\n\n"
        "@decorator\n"
        "def multi(\n    a: int,\n    b: int,\n) -> int:\n    # comment\n    return a\n\n"
        "def broken(:\n"
    )
    out = signatures(src, "python")  # does not parse: regex fallback
    assert "def one(): return 1" in out
    good = src.replace("def broken(:\n", "")
    out = signatures(good, "python")
    assert "class A: ..." in out and "def one(): ..." in out
    assert "@decorator" in out and ") -> int:" in out and "return a" not in out and "# comment" not in out
