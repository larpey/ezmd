"""intomd_api.uploads: streaming multipart parsing with a hard byte cap (docs/spec/part1.md 8.2).

The body is read from `request.stream()` and counted; the request is aborted as soon as a file part
reaches `max_file_bytes + 1`, before the rest of the body is read. `Content-Length` is advisory only.
Files are spooled to a temp directory under names we choose; the client filename is sanitized and
kept for display only.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from fastapi import Request
from python_multipart.multipart import MultipartParser, parse_options_header

from intomd_api.errors import ApiError
from intomd_api.util import sanitize_filename

MAX_FIELD_BYTES = 64 * 1024
FORM_OVERHEAD_BYTES = 1024 * 1024
MAX_PARTS = 16


@dataclass(slots=True)
class UploadedFile:
    path: Path
    filename: str
    content_type: str | None
    size: int
    sha256: str


@dataclass(slots=True)
class MultipartForm:
    tmpdir: Path
    files: dict[str, UploadedFile] = field(default_factory=dict)
    fields: dict[str, str] = field(default_factory=dict)

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class _Abort(Exception):
    def __init__(self, error: ApiError) -> None:
        super().__init__(error.message)
        self.error = error


def too_large(limit: int, received: int) -> ApiError:
    mb = limit / (1024 * 1024)
    return ApiError(
        "input_too_large",
        f"Upload exceeds the {mb:g} MB limit.",
        detail={"limit_bytes": limit, "received_bytes": received},
    )


class _Collector:
    def __init__(self, form: MultipartForm, max_file_bytes: int, file_fields: tuple[str, ...]) -> None:
        self.form = form
        self.max_file_bytes = max_file_bytes
        self.file_fields = file_fields
        self.parts = 0
        self._header_field = b""
        self._header_value = b""
        self._headers: dict[bytes, bytes] = {}
        self._name = ""
        self._filename: str | None = None
        self._fh: IO[bytes] | None = None
        self._hash: Any = None
        self._size = 0
        self._buf = bytearray()

    def callbacks(self) -> dict[str, Any]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
        }

    def on_part_begin(self) -> None:
        self.parts += 1
        if self.parts > MAX_PARTS:
            raise _Abort(ApiError("invalid_request", "Too many form parts."))
        self._headers, self._header_field, self._header_value = {}, b"", b""
        self._name, self._filename, self._fh, self._size, self._buf = "", None, None, 0, bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        self._headers[self._header_field.lower()] = self._header_value
        self._header_field, self._header_value = b"", b""

    def on_headers_finished(self) -> None:
        _, opts = parse_options_header(self._headers.get(b"content-disposition", b""))
        self._name = opts.get(b"name", b"").decode("utf-8", "replace")
        raw_filename = opts.get(b"filename")
        if self._name in self.file_fields and raw_filename is not None:
            if self._name in self.form.files:
                raise _Abort(ApiError("invalid_request", "Only one file per request is accepted."))
            self._filename = sanitize_filename(raw_filename.decode("utf-8", "replace"))
            self._fh = (self.form.tmpdir / f"part-{self.parts}").open("wb")
            self._hash = hashlib.sha256()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        self._size += len(chunk)
        if self._fh is not None:
            if self._size > self.max_file_bytes:
                raise _Abort(too_large(self.max_file_bytes, self._size))
            self._fh.write(chunk)
            self._hash.update(chunk)
        elif self._name:
            if self._size > MAX_FIELD_BYTES:
                raise _Abort(ApiError("invalid_request", f"Form field {self._name!r} is too large."))
            self._buf.extend(chunk)

    def on_part_end(self) -> None:
        if self._fh is not None:
            self._fh.close()
            ctype = self._headers.get(b"content-type")
            self.form.files[self._name] = UploadedFile(
                path=Path(self._fh.name),
                filename=self._filename or "upload",
                content_type=ctype.decode("latin-1").strip()[:255] if ctype else None,
                size=self._size,
                sha256=self._hash.hexdigest(),
            )
            self._fh = None
        elif self._name:
            self.form.fields[self._name] = self._buf.decode("utf-8", "replace")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


async def parse_multipart(
    request: Request, *, max_file_bytes: int, file_fields: tuple[str, ...] = ("file",)
) -> MultipartForm:
    """Parse a multipart body under the cap. Raises ApiError; the caller owns `form.cleanup()`."""
    ctype, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary")
    if ctype != b"multipart/form-data" or not boundary:
        raise ApiError("invalid_request", "Expected multipart/form-data with a boundary.")
    total_cap = max_file_bytes + FORM_OVERHEAD_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > total_cap:
        raise too_large(max_file_bytes, int(declared))
    form = MultipartForm(tmpdir=Path(tempfile.mkdtemp(prefix="intomd-upload-")))
    collector = _Collector(form, max_file_bytes, file_fields)
    parser = MultipartParser(boundary, collector.callbacks())  # type: ignore[arg-type]
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > total_cap:
                raise _Abort(too_large(max_file_bytes, received))
            parser.write(chunk)
        parser.finalize()
    except _Abort as e:
        collector.close()
        form.cleanup()
        raise e.error from None
    except ApiError:
        collector.close()
        form.cleanup()
        raise
    except Exception as e:
        collector.close()
        form.cleanup()
        raise ApiError("invalid_request", "Malformed multipart body.") from e
    return form
