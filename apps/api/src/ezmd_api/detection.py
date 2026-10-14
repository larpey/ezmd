"""ezmd_api.detection: type detection plus the up-front support check, shared by uploads (before a job
exists) and fetched bodies (in the conversion worker). docs/internal/spec/part1.md section 8.2.

An input is refused when its detected type is executable or when no registered converter would claim it
(available, experimental, or registered but missing its extra), so the caller gets 415
`unsupported_media_type` instead of a job that is accepted and then fails with `conversion_failed`.
"""

from __future__ import annotations

from pathlib import Path

EXECUTABLE = "executable"
NO_CONVERTER = "no_converter"


class Unsupported(Exception):
    def __init__(self, mime: str, reason: str, message: str) -> None:
        super().__init__(message)
        self.mime = mime
        self.reason = reason
        self.message = message


def detect_supported(path: Path, *, display: str, declared_mime: str | None) -> str:
    """The detected mime of the file at `path`. Raises Unsupported, or ezmd.inputs.InputTooLarge.

    The InputRef is capped at the file's own size: callers have already held the body to the caller's
    tier cap, and ezmd.inputs' 100 MiB library default is not that cap."""
    from ezmd import detect as detection
    from ezmd.inputs import InputRef
    from ezmd.registry import default_registry

    ref = InputRef(
        kind="bytes",
        display=display,
        local_path=path,
        declared_mime=declared_mime,
        max_bytes=max(1, path.stat().st_size),
    )
    mime = detection.detect(ref).mime
    if detection.is_executable(mime):
        raise Unsupported(mime, EXECUTABLE, "Executable files are not accepted.")
    registry = default_registry()
    if not registry.candidates(ref) and not registry.unavailable_for(ref):
        raise Unsupported(mime, NO_CONVERTER, f"No converter on this instance handles {mime} input.")
    return mime
