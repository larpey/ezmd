"""Exit codes (docs/spec/part4.md 4.2.2) and the mapping from exceptions and API error codes to them.

0 success; 1 generic failure; 2 bad arguments or missing dependency (a missing file, or an optional extra
the input needs: `extra_required`, whether the converter is unavailable or returned a stub that says so);
3 partial success (a usable result with an error-severity warning, or a batch with failures under
--continue-on-error; D-0017 item 7); 4 fetch blocked by platform; 5 input too large or duration cap;
6 unsupported type (`unsupported_media_type`); 130 interrupted. Library errors are classified by their
stable `ConversionError.code`, never by message text (D-0054).
"""

from __future__ import annotations

from dataclasses import dataclass

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_ARGS = 2
EXIT_PARTIAL = 3
EXIT_BLOCKED = 4
EXIT_TOO_LARGE = 5
EXIT_UNSUPPORTED = 6
EXIT_INTERRUPTED = 130

API_EXIT_CODES: dict[str, int] = {
    "invalid_request": EXIT_ARGS,
    "unauthorized": EXIT_ARGS,
    "forbidden": EXIT_ARGS,
    "not_implemented": EXIT_ARGS,
    "turnstile_required": EXIT_ARGS,
    "turnstile_failed": EXIT_ARGS,
    "platform_disabled": EXIT_BLOCKED,
    "fetch_blocked_by_platform": EXIT_BLOCKED,
    "needs_user_action": EXIT_BLOCKED,
    "input_too_large": EXIT_TOO_LARGE,
    "result_too_large": EXIT_TOO_LARGE,
    "duration_cap": EXIT_TOO_LARGE,
    "unsupported_media_type": EXIT_UNSUPPORTED,
    "experimental_disabled": EXIT_UNSUPPORTED,
    "extra_required": EXIT_ARGS,
    "sandbox_unavailable": EXIT_ARGS,
}
"""REST error codes (docs/errors.md) to CLI exit codes; anything else is a generic failure (1)."""


@dataclass(frozen=True, slots=True)
class Failure:
    """A classified failure: exit code, stable machine code, and a message that is safe to print."""

    exit_code: int
    code: str
    message: str
    warning_kind: str = "converter_failed"


class RemoteError(Exception):
    """An error reported by a remote ezmd instance (the Part 1 7.5 error schema) or the transport."""

    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def classify(e: BaseException) -> Failure:
    """Map an exception raised by the library, the fetcher, or the remote client to a Failure."""
    from ezmd.core.netguard import NetguardError, PlatformDisabled, ResidentialOnly, ResponseTooLarge, SchemeNotAllowed
    from ezmd.inputs import FetchRequired, InputTooLarge
    from ezmd.pipeline import UnsupportedMediaType
    from ezmd.registry import (
        EXPERIMENTAL_DISABLED,
        EXTRA_REQUIRED,
        SANDBOX_UNAVAILABLE,
        UNSUPPORTED_MEDIA_TYPE,
        ConversionError,
    )

    if isinstance(e, RemoteError):
        code = API_EXIT_CODES.get(e.code, EXIT_FAIL)
        kind = "size_cap" if code == EXIT_TOO_LARGE else "converter_failed"
        return Failure(code, e.code, e.message, kind)
    if isinstance(e, UnsupportedMediaType):
        return Failure(EXIT_UNSUPPORTED, "unsupported_media_type", e.user_message)
    if isinstance(e, ConversionError):
        if e.code in (UNSUPPORTED_MEDIA_TYPE, EXPERIMENTAL_DISABLED):
            return Failure(EXIT_UNSUPPORTED, e.code, e.user_message)
        if e.code == EXTRA_REQUIRED:
            return Failure(EXIT_ARGS, e.code, e.user_message, "extra_required")
        if e.code == SANDBOX_UNAVAILABLE:  # a missing dependency of this deployment
            return Failure(EXIT_ARGS, e.code, e.user_message, "other")
        return Failure(EXIT_FAIL, e.code, e.user_message)
    if isinstance(e, (InputTooLarge, ResponseTooLarge)):
        return Failure(EXIT_TOO_LARGE, "input_too_large", str(e) or "Input too large.", "size_cap")
    if isinstance(e, (ResidentialOnly, PlatformDisabled)):
        return Failure(EXIT_BLOCKED, e.code, str(e), "other")
    if isinstance(e, FetchRequired):
        return Failure(EXIT_BLOCKED, "fetch_blocked_by_platform", "The input needs a fetch this CLI cannot do.")
    if isinstance(e, SchemeNotAllowed):
        return Failure(EXIT_ARGS, e.code, str(e), "other")
    if isinstance(e, NetguardError):
        return Failure(EXIT_FAIL, e.code, str(e), "other")
    if isinstance(e, FileNotFoundError):
        return Failure(EXIT_ARGS, "not_found", f"no such file: {e.args[0] if e.args else e}", "other")
    if isinstance(e, (ValueError, TypeError)):
        return Failure(EXIT_ARGS, "invalid_request", _short(str(e)), "other")
    if isinstance(e, OSError):
        return Failure(EXIT_FAIL, "io_error", _short(str(e)), "other")
    return Failure(EXIT_FAIL, "conversion_failed", "Conversion failed.")


def _short(text: str, limit: int = 300) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "invalid input"
    return first if len(first) <= limit else first[: limit - 3] + "..."
