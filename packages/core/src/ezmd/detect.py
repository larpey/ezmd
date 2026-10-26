"""ezmd.detect: content-type detection by magic, never by extension alone.

Implemented from docs/internal/spec/part1.md section 5.1. Magika (Apache-2.0) runs on the first 1 MiB plus
the last 64 KiB; libmagic runs on the same sample; the extension is mapped through a small table.

Resolution order:
1. Magika confidence >= 0.9 (and Magika did not answer "unknown"): Magika's mime.
2. libmagic and extension agree: that mime.
3. libmagic says something other than application/octet-stream or text/plain: libmagic.
4. The extension's mime.
5. libmagic's text/plain, then Magika's low-confidence answer, then application/octet-stream
   (step 5 extends the spec so extensionless text files are not reported as binary; D-0005).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import mimetypes
import os
import re
import threading
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ezmd.inputs import Detected, InputRef

log = logging.getLogger(__name__)

HEAD_BYTES = 1 << 20
TAIL_BYTES = 64 << 10
MAGIKA_THRESHOLD = 0.9
OCTET = "application/octet-stream"
URI_MIME = "text/x-uri"
EMPTY_MIME = "application/x-empty"

_STATIC_EXECUTABLE_MIMES = frozenset(
    {
        # libmagic and the IANA/Microsoft names
        "application/x-executable",
        "application/x-dosexec",
        "application/x-mach-binary",
        "application/x-sharedlib",
        "application/x-pie-executable",
        "application/vnd.microsoft.portable-executable",
        "application/x-msdownload",
        "application/x-elf",
        # Magika's "executable" group (magika 1.0 content_types_kb), also read from Magika itself below
        "application/x-executable-elf",
        "application/x-mach-o",
        "application/x-coff",
        "application/x-android-dex",
        "application/x-android-dey",
        "application/x-windows-driver",
        "application/x-bytecode.python",
    }
)


def _magika_executable_mimes() -> frozenset[str]:
    """Mime types of Magika's "executable" content-type group, read from its knowledge base without importing
    magika (which loads onnxruntime). Empty when magika is not installed or the file moved."""
    try:
        spec = importlib.util.find_spec("magika")
        if spec is None or spec.origin is None:
            return frozenset()
        kb = json.loads((Path(spec.origin).parent / "config" / "content_types_kb.min.json").read_text("utf-8"))
        return frozenset(
            str(v["mime_type"])
            for v in kb.values()
            if isinstance(v, dict) and v.get("group") == "executable" and v.get("mime_type")
        )
    except (OSError, ValueError, ImportError, KeyError):
        return frozenset()


EXECUTABLE_MIMES = (_STATIC_EXECUTABLE_MIMES | _magika_executable_mimes()) - {"application/octet-stream"}
"""Refused outright (part1 8.2). Magika's executable group also lists `rll` as application/octet-stream,
which is every unknown binary, so that one is never in the set."""

_ISO_OFFSETS = (0x8001, 0x8801, 0x9001)
_CONTAINER_SIGNATURES: dict[str, Callable[[bytes], bool]] = {
    "iso": lambda b: any(b[o : o + 5] == b"CD001" for o in _ISO_OFFSETS),
    "zip": lambda b: b.startswith(b"PK\x03\x04") or b"PK\x05\x06" in b[-(64 << 10) :],
    "sevenzip": lambda b: b.startswith(b"7z\xbc\xaf\x27\x1c"),
    "rar": lambda b: b.startswith(b"Rar!\x1a\x07"),
    "gzip": lambda b: b.startswith(b"\x1f\x8b"),
    "bzip": lambda b: b.startswith(b"BZh"),
    "xz": lambda b: b.startswith(b"\xfd7zXZ\x00"),
    "zst": lambda b: b.startswith(b"\x28\xb5\x2f\xfd"),
    "tar": lambda b: b[257:262] == b"ustar",
    "cab": lambda b: b.startswith(b"MSCF"),
    "rpm": lambda b: b.startswith(b"\xed\xab\xee\xdb"),
    "deb": lambda b: b.startswith(b"!<arch>"),
    "lha": lambda b: b[2:5] == b"-lh",
    "arj": lambda b: b.startswith(b"\x60\xea"),
}
"""Magic bytes for Magika's archive labels. Magika labels 1 MiB of one repeated byte `iso` at 0.9986; when
libmagic disagrees with a container label, the label stands only if its signature is present."""

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_OLE_APPLICATIONS = frozenset(
    {
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.ms-outlook",
        "application/vnd.visio",
        "application/vnd.ms-publisher",
        "application/vnd.ms-project",
        "application/vnd.ms-works",
    }
)
"""What an OLE2 container can hold. libmagic names the application from the stream names, which is the
strongest evidence there is; a generic `application/cdfv2` or `application/vnd.ms-office` is only "some OLE
file" and must not outrank the extension or Magika's label."""
XLSB = "application/vnd.ms-excel.sheet.binary.macroenabled.12"


def _ole_verdict(
    sample: bytes, libmagic: str | None, magika: str | None, score: float, ext_mime: str | None
) -> tuple[str, float] | None:
    """The type of an OLE2 container, or None when nothing names the application (the generic verdict stands)."""
    if not sample.startswith(_OLE_MAGIC):
        return None
    if libmagic in _OLE_APPLICATIONS:
        return libmagic, 0.9
    if ext_mime in _OLE_APPLICATIONS:
        return ext_mime, 0.7
    if magika in _OLE_APPLICATIONS and score >= MAGIKA_THRESHOLD:
        return magika, score
    return None


# Extension -> mime for types the stdlib table lacks or gets wrong across platforms.
_EXTENSION_MIMES: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".msg": "application/vnd.ms-outlook",
    ".vsd": "application/vnd.visio",
    ".vsdx": "application/vnd.visio",
    # Only some systems' mime.types list .mbox (Ubuntu's does; Windows and slim images do not).
    ".mbox": "application/mbox",
    ".mdx": "text/markdown",
    ".txt": "text/plain",
    ".text": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".jsonl": "application/jsonl",
    ".ndjson": "application/jsonl",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".tar": "application/x-tar",
    ".tgz": "application/gzip",
    ".gz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".xz": "application/x-xz",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".epub": "application/epub+zip",
    ".docm": "application/vnd.ms-word.document.macroenabled.12",
    ".dotx": "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    ".dotm": "application/vnd.ms-word.template.macroenabled.12",
    ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
    ".xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    ".xltm": "application/vnd.ms-excel.template.macroenabled.12",
    ".pptm": "application/vnd.ms-powerpoint.presentation.macroenabled.12",
    ".potx": "application/vnd.openxmlformats-officedocument.presentationml.template",
    ".potm": "application/vnd.ms-powerpoint.template.macroenabled.12",
    ".ppsx": "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    ".ppsm": "application/vnd.ms-powerpoint.slideshow.macroenabled.12",
    ".ipynb": "application/x-ipynb+json",
    ".sqlite": "application/vnd.sqlite3",
    ".sqlite3": "application/vnd.sqlite3",
    ".db": "application/vnd.sqlite3",
    ".parquet": "application/vnd.apache.parquet",
    ".py": "text/x-python",
    ".ts": "application/typescript",
    ".mts": "application/typescript",
    ".cts": "application/typescript",
    ".tsx": "application/typescript",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".cjs": "application/javascript",
    ".rtf": "application/rtf",
    ".eml": "message/rfc822",
}

# Normalize aliases emitted by different detectors to one canonical mime.
_ALIASES: dict[str, str] = {
    "text/x-markdown": "text/markdown",
    "text/x-script.python": "text/x-python",
    "application/x-python-code": "text/x-python",
    "text/x-python3": "text/x-python",
    "application/x-yaml": "application/yaml",
    "text/yaml": "application/yaml",
    "text/x-yaml": "application/yaml",
    "text/xml": "application/xml",
    "audio/x-wav": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/x-mpeg": "audio/mpeg",
    "image/jpg": "image/jpeg",
    "application/x-zip-compressed": "application/zip",
    "text/x-csv": "text/csv",
    "application/csv": "text/csv",
    "application/x-pdf": "application/pdf",
    "inode/x-empty": EMPTY_MIME,
    "text/rtf": "application/rtf",
    "application/x-rtf": "application/rtf",
    "application/x-sqlite3": "application/vnd.sqlite3",
    "application/vnd.sqlite3": "application/vnd.sqlite3",
    "application/x-parquet": "application/vnd.apache.parquet",
    "application/vnd.apache.parquet": "application/vnd.apache.parquet",
}

# Magika labels whose mime we override (Magika reports generic or legacy mimes for these).
_MAGIKA_LABEL_MIMES: dict[str, str] = {
    "markdown": "text/markdown",
    "txt": "text/plain",
    "python": "text/x-python",
    "empty": EMPTY_MIME,
    "yaml": "application/yaml",
    "toml": "application/toml",
    "jsonl": "application/jsonl",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "ipynb": "application/x-ipynb+json",
    "sqlite": "application/vnd.sqlite3",
    "parquet": "application/vnd.apache.parquet",
}


def normalize_mime(mime: str | None) -> str | None:
    if mime is None:
        return None
    m = mime.split(";", 1)[0].strip().lower()
    return _ALIASES.get(m, m) or None


def extension_mime(name: str) -> str | None:
    suffix = Path(name).suffix.lower()
    if not suffix:
        return None
    if suffix in _EXTENSION_MIMES:
        return _EXTENSION_MIMES[suffix]
    guess, _ = mimetypes.guess_type(f"x{suffix}", strict=False)
    return normalize_mime(guess)


# Macro-enabled and template OOXML variants -> the base document type a converter handles. Detectors
# report the base type for these (same container, same parts), so the pair is not a misnamed file.
_OOXML = "application/vnd.openxmlformats-officedocument."
_DOCX = _OOXML + "wordprocessingml.document"
_XLSX = _OOXML + "spreadsheetml.sheet"
_PPTX = _OOXML + "presentationml.presentation"
_MIME_FAMILY: dict[str, str] = {
    "application/vnd.ms-word.document.macroenabled.12": _DOCX,
    _OOXML + "wordprocessingml.template": _DOCX,
    "application/vnd.ms-word.template.macroenabled.12": _DOCX,
    "application/vnd.ms-excel.sheet.macroenabled.12": _XLSX,
    _OOXML + "spreadsheetml.template": _XLSX,
    "application/vnd.ms-excel.template.macroenabled.12": _XLSX,
    "application/vnd.ms-powerpoint.presentation.macroenabled.12": _PPTX,
    _OOXML + "presentationml.template": _PPTX,
    "application/vnd.ms-powerpoint.template.macroenabled.12": _PPTX,
    # An mbox is concatenated RFC 5322 messages; Magika labels one "eml", which is not a misnamed file.
    "application/mbox": "message/rfc822",
    _OOXML + "presentationml.slideshow": _PPTX,
    "application/vnd.ms-powerpoint.slideshow.macroenabled.12": _PPTX,
}


def mime_family(mime: str) -> str:
    """The base mime a variant belongs to (`docm`/`dotx` -> docx), after alias normalization."""
    m = normalize_mime(mime) or mime
    return _MIME_FAMILY.get(m, m)


def same_family(a: str, b: str) -> bool:
    """True when two mimes name the same format family (identical, aliases, or OOXML variants)."""
    return mime_family(a) == mime_family(b)


def is_executable(mime: str) -> bool:
    return mime in EXECUTABLE_MIMES


_TEXTUAL_APPLICATION = frozenset(
    {
        "application/json",
        "application/jsonl",
        "application/xml",
        "application/yaml",
        "application/toml",
        "application/javascript",
        "application/typescript",
        "application/x-sh",
        "application/x-httpd-php",
        "application/sql",
        "application/x-ipynb+json",
        "application/rtf",
    }
)


def is_textual(mime: str) -> bool:
    """True for text formats (text/*, JSON/XML/YAML/TOML, source code mimes, +json/+xml suffixes)."""
    return (
        mime.startswith("text/")
        or mime in _TEXTUAL_APPLICATION
        or mime.endswith(("+json", "+xml"))
        or (mime.startswith("application/x-") and mime.split("/", 1)[1][2:] in _CODE_SUBTYPES)
    )


_CODE_SUBTYPES = frozenset({"python", "rust", "golang", "ruby", "perl", "lua", "kotlin", "scala", "csharp", "dart"})


class _Engines:
    """Lazily constructed, process-wide detector engines. Missing engines degrade to None."""

    _lock = threading.Lock()
    _magika: Any = None
    _magika_failed = False
    _magic_failed = False

    @classmethod
    def magika(cls) -> Any:
        if cls._magika is None and not cls._magika_failed:
            with cls._lock:
                if cls._magika is None and not cls._magika_failed:
                    try:
                        cls._magika = _bounded_magika()
                    except Exception as e:
                        log.warning("magika unavailable: %s", e)
                        cls._magika_failed = True
        return cls._magika

    @classmethod
    def libmagic(cls, sample: bytes) -> str | None:
        if cls._magic_failed:
            return None
        try:
            magic = import_magic()
            return normalize_mime(magic.from_buffer(sample, mime=True))
        except Exception as e:
            log.warning("libmagic unavailable: %s", e)
            cls._magic_failed = True
            return None


def magika_threads() -> int:
    """ONNX Runtime threads for Magika (intra- and inter-op): `EZMD_MAGIKA_THREADS`, default 1. Magika's
    session otherwise sizes its pool to the machine and ignores OMP_NUM_THREADS, which trips RLIMIT_NPROC in
    the API worker; one thread is plenty for one 1 MiB sample."""
    raw = os.environ.get("EZMD_MAGIKA_THREADS", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else 1


def _bounded_magika() -> Any:
    """A Magika whose ONNX session has bounded thread pools. Magika (1.0) exposes no session options, so its
    `_init_onnx_session` is overridden; if that private API changes, plain Magika() is used."""
    from magika import Magika

    threads = magika_threads()

    class _Bounded(Magika):
        def _init_onnx_session(self) -> Any:
            import onnxruntime as rt  # type: ignore[import-untyped]

            opts = rt.SessionOptions()
            opts.intra_op_num_threads = threads
            opts.inter_op_num_threads = threads
            opts.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
            return rt.InferenceSession(self._model_path, sess_options=opts, providers=["CPUExecutionProvider"])

    try:
        return _Bounded()
    except Exception as e:  # a changed private API must not cost the user Magika
        log.warning("magika session options not applied (%s); using the default session", e)
        return Magika()


def import_magic() -> Any:
    """Import python-magic without its compile-time noise. python-magic-bin (the Windows wheel) has an
    `is -1` comparison that makes CPython print a SyntaxWarning the first time the module compiles; users
    would see it on every fresh install, so that one warning from that one module is silenced."""
    import importlib

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"magic(\..*)?$")
        warnings.filterwarnings("ignore", category=SyntaxWarning, message=r".*\"is\" with '?int'? literal.*")
        return importlib.import_module("magic")


def _sample(ref: InputRef) -> tuple[bytes, int]:
    """Head plus tail sample and total size, without reading more than HEAD+TAIL bytes."""
    if ref.data is not None:
        data = ref.data
        size = len(data)
        if size <= HEAD_BYTES + TAIL_BYTES:
            return data, size
        return data[:HEAD_BYTES] + data[-TAIL_BYTES:], size
    path = ref.path()
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(HEAD_BYTES)
        if size <= HEAD_BYTES + TAIL_BYTES:
            return head + f.read(), size
        f.seek(size - TAIL_BYTES)
        return head + f.read(TAIL_BYTES), size


def _magika_guess(sample: bytes) -> tuple[str | None, str | None, float]:
    m = _Engines.magika()
    if m is None:
        return None, None, 0.0
    try:
        res = m.identify_bytes(sample)
        out = res.prediction.output
        label = str(out.label)
        score = float(res.prediction.score)
    except Exception as e:
        log.warning("magika failed: %s", e)
        return None, None, 0.0
    if label in ("unknown", "undefined"):
        return label, None, score
    mime = _MAGIKA_LABEL_MIMES.get(label) or normalize_mime(str(out.mime_type))
    return label, mime, score


RFC822 = "message/rfc822"
_HEADER_LINE = re.compile(rb"[!-9;-~]{1,76}:[ \t]")
_MAIL_EVIDENCE = re.compile(rb"(?i)(message-id|received|mime-version|return-path):")
_FROM = re.compile(rb"(?i)from:[ \t]")
TEXTUAL_EXTENSIONS = frozenset(
    {".md", ".markdown", ".mdown", ".txt", ".text", ".rst", ".adoc", ".asciidoc", ".org", ".log", ".csv", ".tsv",
     ".tex", ".html", ".htm", ".xml", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
)  # fmt: skip
"""Extensions a header sniff overrides only on strong evidence (part2 13.1: the extension decides between
text-like formats)."""


def rfc822_evidence(sample: bytes) -> int:
    """How strongly the start of `sample` looks like an RFC 5322 message: 0 unless the input opens with a header
    block in which every line is a header field or a folded continuation and one field is `From:`; otherwise the
    number of distinct mail-only fields (Message-ID, Received, MIME-Version, Return-Path) in it. `Date:` and
    `Subject:` count for nothing (notes and HTTP header dumps have them). An mbox `From ` line scores 0."""
    head = sample[:2048]
    end = re.search(rb"\r?\n\r?\n", head)
    block = head[: end.start()] if end else head
    lines = block.splitlines()
    if not lines or not _HEADER_LINE.match(lines[0]):
        return 0
    checked = lines if end else lines[:-1]  # the last line of a cut sample may be partial
    if any(not (_HEADER_LINE.match(ln) or ln[:1] in (b" ", b"\t")) for ln in checked):
        return 0
    fields = [ln for ln in lines if _HEADER_LINE.match(ln)]
    if not any(_FROM.match(ln) for ln in fields):
        return 0
    found = {m.group(1).lower() for ln in fields if (m := _MAIL_EVIDENCE.match(ln))}
    return len(found)


def looks_like_rfc822(sample: bytes, extension: str | None = None) -> bool:
    """A header block with `From:` and at least one mail-only field; two when the extension names another
    text-like format (`notes.md` with `Title:/From:/Date:` lines stays Markdown)."""
    need = 2 if extension in TEXTUAL_EXTENSIONS else 1
    return rfc822_evidence(sample) >= need


class MagicDetector:
    """The default Detector."""

    def detect(self, ref: InputRef) -> Detected:
        ext = Path(ref.display).suffix.lower() or None
        ext_mime = extension_mime(ref.display)
        if not ref.has_body:
            return Detected(mime=URI_MIME, extension=ext, confidence=1.0, extension_mime=ext_mime)
        sample, size = _sample(ref)
        if size == 0:
            return Detected(mime=EMPTY_MIME, extension=ext, confidence=1.0, extension_mime=ext_mime)
        label, mg_mime, score = _magika_guess(sample)
        lm = _Engines.libmagic(sample)
        check = _CONTAINER_SIGNATURES.get(label or "")
        if check is not None and mg_mime is not None and lm != mg_mime and not check(sample):
            mg_mime = None  # a container label without the container's signature
        mime: str
        confidence: float
        ole = _ole_verdict(sample, lm, mg_mime, score, ext_mime)
        if ole is not None:
            mime, confidence = ole
        elif mg_mime is not None and score >= MAGIKA_THRESHOLD:
            mime, confidence = mg_mime, score
        elif lm is not None and ext_mime is not None and lm == ext_mime:
            mime, confidence = lm, 1.0
        elif lm is not None and lm not in (OCTET, "text/plain"):
            mime, confidence = lm, 0.8
        elif ext_mime is not None:
            mime, confidence = ext_mime, 0.6
        elif lm == "text/plain":
            mime, confidence = lm, 0.6
        elif mg_mime is not None:
            mime, confidence = mg_mime, score
        else:
            mime, confidence = OCTET, 0.0
        if mime == _XLSX and b"xl/workbook.bin" in sample:
            # An Excel binary workbook is the same package with .bin parts; openpyxl cannot read it, LibreOffice can.
            mime, confidence = XLSB, max(confidence, 0.9)
        if mime != RFC822 and (mime.startswith("text/") or mime == OCTET) and looks_like_rfc822(sample, ext):
            # An email whose body is HTML is "html"/"mht" to Magika and libmagic; its leading RFC 5322 headers
            # decide (docs/internal/spec/part2.md 9a: From:/Received:/Return-Path: in the first 2 KB).
            mime, confidence = RFC822, max(confidence, 0.9)
        return Detected(
            mime=mime,
            extension=ext,
            confidence=confidence,
            magika_label=label,
            libmagic_mime=lm,
            extension_mime=ext_mime,
        )


_default_detector = MagicDetector()


def detect(ref: InputRef) -> Detected:
    """Detect and record the content type on `ref`. Returns the Detected result."""
    d = _default_detector.detect(ref)
    ref.detected = d
    return d
