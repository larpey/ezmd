from __future__ import annotations

import io
import re
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from ezmd.detect import detect
from ezmd.inputs import Detected, FetchRequired, InputRef
from ezmd.ir import CodeBlock, Document, Heading, WarningKind
from ezmd.registry import ConversionError, ConvertOptions, ExtraValue
from ezmd_converters.code.archive import ArchiveLimits, read_archive, safe_path
from ezmd_converters.code.github import is_codeload_url, parse_repo_url
from ezmd_converters.code.repo_pack import RepoPackConverter

GH_TOKEN = "gh" + "p_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"
AWS_ID = "AK" + "IA" + "ZZEXAMPLEFAKE001"
SECRET_VALUE = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"


def _zip(files: dict[str, bytes], *, root: str = "proj/", links: tuple[str, ...] = ()) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(root + name, data)
        for name in links:
            info = zipfile.ZipInfo(root + name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "../../etc/passwd")
    return buf.getvalue()


def _tar_gz(files: dict[str, bytes], commit: str | None = None) -> bytes:
    raw = io.BytesIO()
    headers = {"comment": commit} if commit else {}
    with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.PAX_FORMAT, pax_headers=headers) as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def _pack(data: bytes, name: str = "proj.repo.zip", url: str | None = None, **extra: ExtraValue) -> Document:
    ref = InputRef.from_bytes(data, filename=name, source_url=url)
    detect(ref)
    try:
        return RepoPackConverter().convert(ref, ConvertOptions(extra=dict(extra)))
    finally:
        ref.cleanup()


def _files(doc: Document) -> dict[str, str]:
    return {b.filename: b.code for b in doc.blocks if isinstance(b, CodeBlock) and b.filename}


def _tree(doc: Document) -> str:
    return next(b.code for b in doc.blocks if isinstance(b, CodeBlock) and b.filename is None)


BASE = {
    "README.md": b"# proj\n\nHello.\n",
    "pyproject.toml": b'[project]\nname = "proj"\ndescription = "Demo."\n',
    ".gitignore": b"*.log\n!keep.log\nsecret_dir/\n",
    "keep.log": b"kept\n",
    "drop.log": b"dropped\n",
    "secret_dir/a.py": b"x = 1\n",
    "src/app.py": b"import os\n\n\ndef run() -> None:\n    print('hi')\n",
    "src/pkg/.gitignore": b"*.tmp\n!important.tmp\n",
    "src/pkg/scratch.tmp": b"t\n",
    "src/pkg/important.tmp": b"keep me\n",
    "tests/test_app.py": b"def test_x() -> None:\n    assert True\n",
    "node_modules/x/index.js": b"module.exports = 1\n",
    ".env": b"DB_PASSWORD=" + SECRET_VALUE.encode() + b"\n",
    "img/logo.png": bytes([0x89, 0x50, 0x4E, 0x47]) + bytes(64),
    "blob.dat": bytes([0, 1, 2, 3]) * 100,
    "package-lock.json": b"\n".join(b'"line%d": 1,' % i for i in range(120)) + b"\n",
}


def test_pack_structure_gitignore_and_exclusions() -> None:
    doc = _pack(_zip(BASE))
    files = _files(doc)
    assert set(files) == {
        "README.md",
        "pyproject.toml",
        ".gitignore",
        "keep.log",
        "src/app.py",
        "src/pkg/.gitignore",
        "src/pkg/important.tmp",
        "tests/test_app.py",
        "package-lock.json",
    }
    order = list(files)
    assert order[0] == "README.md" and order[-1] == "tests/test_app.py"
    assert order.index("src/app.py") < order.index("src/pkg/important.tmp")
    tree = _tree(doc)
    assert "node_modules/ (excluded, 1 file)" in tree
    assert ".env (excluded: secret file)" in tree and "logo.png (excluded: binary)" in tree
    assert "blob.dat (excluded: binary)" in tree and "drop.log" not in tree
    assert files["package-lock.json"].endswith("... (lockfile truncated, 70 more lines)")
    h1 = doc.blocks[0]
    assert isinstance(h1, Heading) and h1.spans[0].text == "proj"
    meta = doc.metadata
    assert meta.extra["project"] == "proj" and meta.description == "Demo."
    assert meta.extra["excluded.gitignored"] == 3 and meta.extra["excluded.secret_file"] == 1
    kinds = {w.kind for w in doc.warnings}
    assert WarningKind.SECRET_FILE_EXCLUDED in kinds
    assert SECRET_VALUE not in doc.plain_text()
    code = next(b for b in doc.blocks if isinstance(b, CodeBlock) and b.filename == "src/app.py")
    assert (code.provenance.path, code.provenance.line_start, code.provenance.line_end) == ("src/app.py", 1, 5)
    assert code.language == "python"


def test_planted_secrets_redacted_and_warned() -> None:
    files = {
        "README.md": b"x\n",
        "tests/fixtures/creds.txt": f"aws_id = {AWS_ID}\ngh = {GH_TOKEN}\n".encode(),
        "src/settings.py": f'API_SECRET_KEY = "{SECRET_VALUE}"\n'.encode(),
    }
    doc = _pack(_zip(files))
    text = doc.plain_text()
    for secret in (AWS_ID, GH_TOKEN, SECRET_VALUE):
        assert secret not in text
        assert all(secret not in w.message and secret not in str(w.detail) for w in doc.warnings)
    assert "[REDACTED:aws_access_key_id]" in text and "[REDACTED:github_token]" in text
    w = next(w for w in doc.warnings if w.kind == WarningKind.SECRET_REDACTED)
    assert w.count == 3
    assert w.detail["rule.aws_access_key_id"] == 1 and w.detail["rule.github_token"] == 1
    assert "tests/fixtures/creds.txt:1" in str(w.detail["locations"])
    # Independent regex pass over the rendered output: no provider-shaped token survives.
    assert not re.search(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}", text)


def test_unsafe_members_and_symlinks_skipped() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("proj/ok.py", "x = 1\n")
        zf.writestr("proj/../../evil.py", "boom\n")
        zf.writestr("/abs.py", "boom\n")
    doc = _pack(buf.getvalue())
    assert set(_files(doc)) == {"proj/ok.py"} or set(_files(doc)) == {"ok.py"}
    w = next(w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_ENTRY_SKIPPED)
    assert w.count == 2
    doc = _pack(_zip({"a.py": b"x = 1\n"}, links=("link.py",)))
    assert set(_files(doc)) == {"a.py"}
    assert any(w.kind == WarningKind.ARCHIVE_ENTRY_SKIPPED for w in doc.warnings)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("a/b.py", "a/b.py"), ("./a//b.py", "a/b.py"), ("../x", None), ("/etc/passwd", None), ("C:/x", None)],
)
def test_safe_path(name: str, expected: str | None) -> None:
    assert safe_path(name) == expected


def test_zip_bomb_ratio_refused(tmp_path: Path) -> None:
    p = tmp_path / "bomb.zip"
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("r/zeros.txt", b"0" * 2_000_000)
    with pytest.raises(ConversionError) as e:
        read_archive(p, ArchiveLimits())
    assert e.value.retryable_with_fallback is False


def test_total_size_and_entry_limits(tmp_path: Path) -> None:
    p = tmp_path / "many.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for i in range(30):
            zf.writestr(f"r/f{i}.txt", "abc" * 10)
    res = read_archive(p, ArchiveLimits(max_entries=10))
    assert res.truncated and len(res.members) == 10
    with pytest.raises(ConversionError):
        read_archive(p, ArchiveLimits(max_total_bytes=100))


def test_oversize_member_listed_not_read() -> None:
    doc = _pack(_zip({"big.py": b"x = 1\n" * 200, "a.py": b"y = 2\n"}), max_file_bytes=100)
    assert set(_files(doc)) == {"a.py"}
    assert "big.py (excluded: too large)" in _tree(doc)


def test_github_tarball_with_commit_and_codeload_url() -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    data = _tar_gz({"acme-proj-0123456/README.md": b"# p\n", "acme-proj-0123456/src/m.py": b"x = 1\n"}, sha)
    url = "https://codeload.github.com/acme/proj/tar.gz/main"
    ref = InputRef.from_bytes(data, filename="download", source_url=url)
    detect(ref)
    conv = RepoPackConverter()
    assert conv.can_handle(ref) == 1.0
    doc = conv.convert(ref, ConvertOptions())
    ref.cleanup()
    assert set(_files(doc)) == {"README.md", "src/m.py"}
    assert doc.metadata.extra["commit"] == sha and doc.metadata.extra["ref"] == "main"
    h1 = doc.blocks[0]
    assert isinstance(h1, Heading) and h1.spans[0].text == "acme/proj at main"


def test_github_url_without_body_raises_fetch_required() -> None:
    ref = InputRef.from_url("https://github.com/acme/proj/tree/v1.2/src/lib")
    ref.detected = Detected(mime="text/x-uri", extension=None, confidence=1.0)
    conv = RepoPackConverter()
    assert conv.can_handle(ref) == 0.7
    with pytest.raises(FetchRequired) as e:
        conv.convert(ref, ConvertOptions())
    assert e.value.url == "https://codeload.github.com/acme/proj/tar.gz/v1.2"
    assert e.value.residential is False


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/acme/proj", ("acme", "proj", None, None)),
        ("https://github.com/acme/proj.git", ("acme", "proj", None, None)),
        ("https://github.com/acme/proj/tree/main/docs/api", ("acme", "proj", "main", "docs/api")),
        ("https://github.com/acme/proj/blob/main/a.py", None),
        ("https://github.com/acme/proj/pull/3", None),
        ("https://github.com/settings/profile", None),
        ("https://gitlab.com/acme/proj", None),
        ("https://github.com/acme/proj/tree/../../x", None),
        ("ftp://github.com/acme/proj", None),
    ],
)
def test_parse_repo_url(url: str, expected: tuple[str, str, str | None, str | None] | None) -> None:
    r = parse_repo_url(url)
    assert (None if r is None else (r.owner, r.repo, r.ref, r.subpath)) == expected


def test_codeload_url_parse() -> None:
    r = is_codeload_url("https://codeload.github.com/acme/proj/tar.gz/refs/heads/dev")
    assert r is not None and (r.owner, r.repo, r.ref) == ("acme", "proj", "refs/heads/dev")
    assert is_codeload_url("https://example.com/acme/proj/tar.gz/main") is None


def test_can_handle_by_name_only_for_repo_archives() -> None:
    conv = RepoPackConverter()
    data = _zip({"a.py": b"x = 1\n"})
    for name, score in (("proj.repo.zip", 0.95), ("photos.zip", 0.0)):
        ref = InputRef.from_bytes(data, filename=name)
        detect(ref)
        assert conv.can_handle(ref) == score


def test_signatures_only_include_exclude_and_tests_first() -> None:
    files = {
        "src/a.py": b"import os\n\n\ndef f(x: int) -> int:\n    return x * 2\n",
        "src/b.py": b"y = 1\n",
        "tests/test_a.py": b"def test_f() -> None:\n    assert True\n",
        "docs/guide.txt": b"read me\n",
    }
    doc = _pack(_zip(files), signatures_only=True)
    out = _files(doc)
    assert "return x * 2" not in out["src/a.py"] and "def f(x: int) -> int:" in out["src/a.py"]
    assert any(isinstance(b, Heading) and b.spans[0].text == "src/a.py (signatures only)" for b in doc.blocks)
    doc = _pack(_zip(files), include="src/**", exclude="src/b.py")
    assert set(_files(doc)) == {"src/a.py"}
    assert doc.metadata.extra["excluded.user_excluded"] == 3
    order = list(_files(_pack(_zip(files), tests_first=True)))
    assert order.index("tests/test_a.py") < order.index("src/a.py") < order.index("docs/guide.txt")


def test_subpath_restricts_pack() -> None:
    files = {".gitignore": b"*.tmp\n", "src/a.py": b"x = 1\n", "src/b.tmp": b"t\n", "other/c.py": b"z = 3\n"}
    doc = _pack(_zip(files), subpath="src")
    assert set(_files(doc)) == {"src/a.py"} and doc.metadata.extra["subpath"] == "src"


def test_negation_cannot_reinclude_under_ignored_directory() -> None:
    """git: a file under an excluded directory cannot be re-included by a later `!` rule; a negation of a file
    whose parent directory is not excluded still works."""
    files = {
        ".gitignore": b"secrets/\n!secrets/README.md\n*.tmp\n!keep.tmp\n",
        "secrets/README.md": b"note\n",
        "secrets/prod.txt": b"token\n",
        "keep.tmp": b"k\n",
        "drop.tmp": b"d\n",
        "src/a.py": b"x = 1\n",
    }
    doc = _pack(_zip(files))
    assert set(_files(doc)) == {".gitignore", "keep.tmp", "src/a.py"}
    assert doc.metadata.extra["excluded.gitignored"] == 3


def test_token_budget_all_actions_keep_tree_complete() -> None:
    long_src = "\n".join(f"def f{i}(x: int) -> int:\n    y = x + {i}\n    return y\n" for i in range(150))
    files = {
        "README.md": b"# r\n",
        "uv.lock": b"\n".join(b"pkg%d==1.0" % i for i in range(60)),
        "gen/api_pb2.py": b"# Generated by protoc. DO NOT EDIT!\nX = 1\n",
        "tests/test_x.py": b"def test_x() -> None:\n    assert True\n" * 20,
        "src/big.py": long_src.encode(),
        "src/mid.py": ("\n".join(f"V{i} = {i}" for i in range(200)) + "\n").encode(),
        "src/deep/deeper/z.py": ("\n".join(f"Z{i} = {i}" for i in range(100)) + "\n").encode(),
    }
    full = _pack(_zip(files))
    doc = _pack(_zip(files), token_budget=350)
    w = next(w for w in doc.warnings if w.kind == WarningKind.TOKEN_BUDGET_APPLIED)
    actions = str(w.detail["actions"])
    for step in ("lockfile, generated", "test file", "compressed", "truncated", "deepest"):
        assert step in actions, actions
    assert _tree(doc).count("\n") == _tree(full).count("\n")
    assert "z.py (omitted: token budget)" in _tree(doc)
    assert doc.metadata.extra["tokens"] <= 350  # type: ignore[operator]
    assert "budget_actions" in doc.metadata.extra


def test_small_budget_untouched_when_it_fits() -> None:
    doc = _pack(_zip({"a.py": b"x = 1\n"}), token_budget=100_000)
    assert not any(w.kind == WarningKind.TOKEN_BUDGET_APPLIED for w in doc.warnings)


def test_minified_and_generated_detection() -> None:
    files = {
        "web/app.js": ("var a=1;" * 400).encode(),
        "web/lib.min.js": b"var x=1;",
        "web/app.js.map": b"{}",
        "api_pb2.py": b"# Generated by protoc. DO NOT EDIT!\nX = 1\n",
    }
    doc = _pack(_zip(files))
    out = _files(doc)
    assert set(out) == {"web/app.js", "api_pb2.py"}
    assert "minified, truncated" in out["web/app.js"] and len(out["web/app.js"]) < 2200


def test_bad_archive_raises() -> None:
    with pytest.raises(ConversionError):
        _pack(b"not an archive at all", name="x.repo.tar.gz")


def test_sizes_are_source_bytes() -> None:
    utf16 = "x = 'café'\n".encode("utf-16")
    lock = b"\n".join(b"pkg%d==1.0" % i for i in range(120)) + b"\n"
    doc = _pack(_zip({"u.py": utf16, "uv.lock": lock}))
    heads = {b.spans[0].text: b.attrs for b in doc.blocks if isinstance(b, Heading) and b.level == 3}
    assert heads["u.py"]["bytes"] == str(len(utf16)) and heads["uv.lock"]["bytes"] == str(len(lock))
    assert int(heads["uv.lock"]["packed_bytes"]) < len(lock)
    assert doc.metadata.extra["bytes"] == len(utf16) + len(lock)
    assert f"({len(utf16) + len(lock):,} source bytes" in doc.plain_text()


def test_redactions_in_budget_dropped_files_are_not_reported() -> None:
    files = {
        "README.md": b"# r\n",
        "tests/fixtures/creds.txt": f'API_TOKEN = "{SECRET_VALUE}"\n'.encode(),
        "src/a.py": ("\n".join(f"V{i} = {i}" for i in range(50)) + "\n").encode(),
    }
    doc = _pack(_zip(files), token_budget=200)
    assert "creds.txt (omitted: token budget)" in _tree(doc)
    assert not any(w.kind == WarningKind.SECRET_REDACTED for w in doc.warnings)
