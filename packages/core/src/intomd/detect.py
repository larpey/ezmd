"""intomd.detect: content-type detection by magic, never by extension alone.

Implemented from docs/spec/part1.md section 5.1. Magika (Apache-2.0) runs on the first 1 MiB plus
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

import logging
import mimetypes
import threading
from pathlib import Path
from typing import Any

from intomd.inputs import Detected, InputRef

log = logging.getLogger(__name__)

HEAD_BYTES = 1 << 20
TAIL_BYTES = 64 << 10
MAGIKA_THRESHOLD = 0.9
OCTET = "application/octet-stream"
URI_MIME = "text/x-uri"
EMPTY_MIME = "application/x-empty"

EXECUTABLE_MIMES = frozenset(
    {
        "application/x-executable",
        "application/x-dosexec",
        "application/x-mach-binary",
        "application/x-sharedlib",
        "application/x-pie-executable",
        "application/vnd.microsoft.portable-executable",
        "application/x-msdownload",
        "application/x-elf",
    }
)

# Extension -> mime for types the stdlib table lacks or gets wrong across platforms.
_EXTENSION_MIMES: dict[str, str] = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
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
                        from magika import Magika

                        cls._magika = Magika()
                    except Exception as e:
                        log.warning("magika unavailable: %s", e)
                        cls._magika_failed = True
        return cls._magika

    @classmethod
    def libmagic(cls, sample: bytes) -> str | None:
        if cls._magic_failed:
            return None
        try:
            import magic

            return normalize_mime(magic.from_buffer(sample, mime=True))
        except Exception as e:
            log.warning("libmagic unavailable: %s", e)
            cls._magic_failed = True
            return None


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
        mime: str
        confidence: float
        if mg_mime is not None and score >= MAGIKA_THRESHOLD:
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
