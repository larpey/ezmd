"""ezmd.inputs: input abstraction over local files, uploaded bytes, URLs, and residential fetches.

Implemented from docs/spec/part1.md section 5.1.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ezmd.ir import InputKind, InputRefInfo

DEFAULT_MAX_BYTES = 100 * 1024 * 1024


class InputTooLarge(Exception):
    pass


MAX_FETCH_DEPTH = 2
"""Most fetch round trips one job may chain (a fetched body asking for another fetch). D-0017 item 4."""


class FetchRequired(Exception):
    """Raised by a converter when it needs the body of a URL that has not been fetched yet.
    The pipeline catches it and enqueues a fetch (ordinary or residential) before retrying.

    `url` and `residential` are requests, not instructions: the parent re-validates the URL with netguard
    and the platform policy and decides residential routing itself. `fetch_depth` counts the fetches
    already chained for this job; the caller refuses once it would exceed MAX_FETCH_DEPTH."""

    def __init__(self, url: str, residential: bool, reason: str, *, fetch_depth: int = 0) -> None:
        super().__init__(reason)
        self.url = url
        self.residential = residential
        self.reason = reason
        self.fetch_depth = fetch_depth


@dataclass(slots=True)
class Detected:
    """Content-type detection result. `mime` is authoritative; `magika_label` and `libmagic_mime`
    are kept for diagnostics. `confidence` is Magika's score, or 1.0 when libmagic and extension agree."""

    mime: str
    extension: str | None
    confidence: float
    magika_label: str | None = None
    libmagic_mime: str | None = None
    extension_mime: str | None = None


@dataclass(slots=True)
class InputRef:
    """One input to convert.

    kind:
      path: a local file (CLI, worker after upload materialization).
      bytes: in-memory upload (API). Materialized to a temp path on demand.
      url: a URL whose body has not been fetched, or has been fetched into `fetched_path`.
      residential_fetch: a URL that must be fetched by a fetch node; `fetched_path` is set once the
        node uploads the result (usually an audio file plus a metadata JSON).
      transcript_segments / captions_json3 / media_upload: client-supplied bodies (browser Whisper,
        extension caption JSON, extension media upload). They carry a body like `bytes` plus the
        source URL in `url`.

    All byte access goes through `path()` or `read()` which enforce `max_bytes`.
    """

    kind: InputKind
    display: str
    local_path: Path | None = None
    data: bytes | None = None
    url: str | None = None
    fetched_path: Path | None = None
    fetched_headers: dict[str, str] = field(default_factory=dict)
    fetch_meta: dict[str, object] = field(default_factory=dict)
    """Platform metadata from a fetch (title, uploader, duration, captions available, ...)."""
    declared_mime: str | None = None
    """Mime from the upload or the HTTP Content-Type. Advisory only; detection decides."""
    detected: Detected | None = None
    max_bytes: int = DEFAULT_MAX_BYTES
    _tmpdir: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    @classmethod
    def from_path(cls, p: Path, *, max_bytes: int | None = None) -> InputRef:
        ref = cls(kind="path", display=p.name, local_path=p)
        if max_bytes is not None:
            ref.max_bytes = max_bytes
        return ref

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        filename: str,
        declared_mime: str | None = None,
        max_bytes: int | None = None,
        kind: InputKind = "bytes",
        source_url: str | None = None,
    ) -> InputRef:
        ref = cls(kind=kind, display=filename, data=data, declared_mime=declared_mime, url=source_url)
        if max_bytes is not None:
            ref.max_bytes = max_bytes
        if len(data) > ref.max_bytes:
            raise InputTooLarge(f"{len(data)} bytes exceeds cap {ref.max_bytes}")
        return ref

    @classmethod
    def from_url(cls, url: str, *, residential: bool = False, max_bytes: int | None = None) -> InputRef:
        ref = cls(kind="residential_fetch" if residential else "url", display=url, url=url)
        if max_bytes is not None:
            ref.max_bytes = max_bytes
        return ref

    @property
    def has_body(self) -> bool:
        return self.local_path is not None or self.data is not None or self.fetched_path is not None

    def path(self) -> Path:
        """A readable local path. Materializes bytes to a temp file on first call. Raises FetchRequired
        for URL kinds whose body is not present."""
        if self.local_path is not None:
            self._check_size(self.local_path.stat().st_size)
            return self.local_path
        if self.fetched_path is not None:
            self._check_size(self.fetched_path.stat().st_size)
            return self.fetched_path
        if self.data is not None:
            if self._tmpdir is None:
                self._tmpdir = tempfile.TemporaryDirectory(prefix="ezmd-")
                # Only the suffix of the user-supplied name is used, and only if it is a plain extension.
                suffix = Path(self.display).suffix[:16]
                if not suffix[1:].isalnum():
                    suffix = ""
                p = Path(self._tmpdir.name) / f"input{suffix}"
                p.write_bytes(self.data)
                self.local_path = p
            assert self.local_path is not None
            return self.local_path
        if self.url is None:
            raise ValueError("InputRef has neither a body nor a URL")
        raise FetchRequired(self.url, residential=self.kind == "residential_fetch", reason="body not fetched")

    def read(self) -> bytes:
        if self.data is not None:
            return self.data
        p = self.path()
        return p.read_bytes()

    def head(self, n: int) -> bytes:
        """First `n` bytes of the body without reading the whole file."""
        if self.data is not None:
            return self.data[:n]
        with self.path().open("rb") as f:
            return f.read(n)

    def size(self) -> int:
        if self.data is not None:
            return len(self.data)
        return self.path().stat().st_size

    def sha256(self) -> str:
        if self.data is not None:
            return hashlib.sha256(self.data).hexdigest()
        h = hashlib.sha256()
        with self.path().open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def info(self) -> InputRefInfo:
        size = None
        sha = None
        if self.has_body:
            size = self.size()
            sha = self.sha256()
        return InputRefInfo(
            kind=self.kind,
            display=self.display,
            mime=self.detected.mime if self.detected else self.declared_mime,
            size_bytes=size,
            sha256=sha,
        )

    def cleanup(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None
            self.local_path = None
        if self.fetched_path is not None and self.fetched_path.exists() and self.kind in ("url", "residential_fetch"):
            shutil.rmtree(self.fetched_path.parent, ignore_errors=True)

    def _check_size(self, n: int) -> None:
        if n > self.max_bytes:
            raise InputTooLarge(f"{n} bytes exceeds cap {self.max_bytes}")


class Detector(Protocol):
    def detect(self, ref: InputRef) -> Detected: ...
