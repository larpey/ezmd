"""intomd_mcp.paths: local file access policy and inline data URLs.

`convert_file` reads only regular files under the configured allowed roots (default: the working
directory). The check runs on the fully resolved path (symlinks followed), so a link inside a root that
points outside it is refused. Paths must be absolute, may not contain `..`, and system trees such as
`/etc` and `/proc` are refused even when a root would contain them.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath

from intomd_mcp.errors import ToolFailure

__all__ = ["MAX_DATA_URL_BYTES", "AllowedRoots", "InlineFile", "decode_data_url", "filename_for_hint"]

MAX_DATA_URL_BYTES = 1024 * 1024
"""Inline `data_url` inputs are for small files only (docs/spec/part4.md 4.4.2)."""

_DENIED_POSIX = ("/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/var/run", "/run")
_DATA_URL = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+)?(?P<params>(?:;[\w-]+=[^;,]*)*)(?P<b64>;base64)?,", re.I)


def _denied(path: Path) -> bool:
    posix = path.as_posix()
    return any(posix == d or posix.startswith(d + "/") for d in _DENIED_POSIX)


@dataclass(frozen=True, slots=True)
class AllowedRoots:
    """Resolved directories the server may read from."""

    roots: tuple[Path, ...]

    @classmethod
    def from_strings(cls, values: Iterable[str], *, cwd: Path | None = None) -> AllowedRoots:
        base = cwd or Path.cwd()
        roots: list[Path] = []
        for raw in values:
            raw = raw.strip()
            if not raw:
                continue
            p = Path(os.path.expanduser(raw))
            p = (base / p) if not p.is_absolute() else p
            resolved: Path | None
            try:
                resolved = p.resolve(strict=True)
            except OSError:
                resolved = None  # a missing root grants nothing
            if resolved is not None and resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
        return cls(tuple(roots))

    def check(self, raw: str) -> Path:
        """Return the resolved file path, or raise ToolFailure(path_not_allowed | file_not_found)."""
        if not raw or chr(0) in raw:
            raise ToolFailure("invalid_request", "The path is empty or contains a NUL character.")
        pure = PurePath(raw)
        if ".." in pure.parts or ".." in Path(raw).parts:
            raise ToolFailure("path_not_allowed", "Paths containing '..' are refused.")
        candidate = Path(os.path.expanduser(raw))
        if not candidate.is_absolute():
            raise ToolFailure("path_not_allowed", "The path must be absolute.")
        if _denied(candidate):
            raise ToolFailure("path_not_allowed", "System directories are never readable through this server.")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            raise ToolFailure("file_not_found", "The file does not exist.") from None
        if _denied(resolved):
            raise ToolFailure("path_not_allowed", "System directories are never readable through this server.")
        if not any(resolved == root or resolved.is_relative_to(root) for root in self.roots):
            raise ToolFailure(
                "path_not_allowed",
                "The path is outside the server's allowed directories.",
                detail={"allowed_dirs": [str(r) for r in self.roots]},
            )
        if not resolved.is_file():
            raise ToolFailure("file_not_found", "The path is not a regular file.")
        return resolved


@dataclass(frozen=True, slots=True)
class InlineFile:
    data: bytes
    filename: str


def filename_for_hint(hint: str | None, default: str = "input.txt") -> str:
    """A synthetic file name from a MIME type or extension hint. Detection still runs on content; the name
    only breaks ties for formats that content sniffing cannot tell apart (CSV vs text, Markdown vs text)."""
    if not hint:
        return default
    hint = hint.strip().lower()
    if "/" in hint:
        ext = mimetypes.guess_extension(hint.split(";", 1)[0].strip(), strict=False)
        extra = {"text/markdown": ".md", "text/csv": ".csv", "application/json": ".json", "text/html": ".html"}
        ext = extra.get(hint.split(";", 1)[0].strip(), ext)
        return f"input{ext}" if ext else default
    ext = hint.lstrip(".")
    if not re.fullmatch(r"[a-z0-9]{1,10}", ext):
        return default
    return f"input.{ext}"


def decode_data_url(data_url: str) -> InlineFile:
    """Decode a `data:` URL of at most MAX_DATA_URL_BYTES."""
    m = _DATA_URL.match(data_url)
    if m is None:
        raise ToolFailure("invalid_request", "data_url must be a data: URL, e.g. data:application/pdf;base64,....")
    payload = data_url[m.end() :]
    if len(payload) > MAX_DATA_URL_BYTES * 4 // 3 + 8:
        raise ToolFailure("input_too_large", "data_url inputs are limited to 1 MB; pass a file path instead.")
    if m.group("b64"):
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            raise ToolFailure("invalid_request", "data_url is not valid base64.") from None
    else:
        from urllib.parse import unquote_to_bytes

        data = unquote_to_bytes(payload)
    if len(data) > MAX_DATA_URL_BYTES:
        raise ToolFailure("input_too_large", "data_url inputs are limited to 1 MB; pass a file path instead.")
    return InlineFile(data=data, filename=filename_for_hint(m.group("mime"), "input"))
