"""ezmd_mcp.errors: hard failures as (code, user message, suggestion), never stack traces.

Tools raise `ToolFailure`; the server turns it into an `isError: true` result whose text carries the code
and the suggested action. Suggestions come from the shared warning-code registry in `ezmd.warnings`
(the same strings the web UI shows) when the code is a warning code, else from the small map below for
API and argument errors.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ezmd.mcp")

_SUGGESTIONS: dict[str, str] = {
    "invalid_request": "Check the tool arguments and try again.",
    "path_not_allowed": "Pass an absolute path inside one of the server's allowed directories (--allowed-dirs).",
    "file_not_found": "Check the path exists and is a regular file.",
    "input_too_large": "Send a smaller file, or self-host ezmd with higher limits.",
    "unsupported_media_type": "This file type is not supported. Convert it to PDF, DOCX, HTML or text first.",
    "url_blocked": "Use a public http(s) URL, or upload the file directly.",
    "platform_disabled": "This site is disabled on this instance. Upload the file directly.",
    "fetch_failed": "Check the URL is reachable, or upload the file directly.",
    "fetch_blocked_by_platform": (
        "This platform blocked the server. Upload the file directly, or install the browser extension to fetch "
        "from your own connection."
    ),
    "conversion_failed": "The file may be damaged or in an unsupported variant. Try another copy or format.",
    "experimental_disabled": "Only an experimental converter handles this input; enable experimental converters.",
    "timeout": "The conversion took too long. Try a smaller input or raise max_seconds.",
    "not_found": "The job is unknown or expired. Convert the source again.",
    "job_not_found": "The job is unknown or expired. Convert the source again.",
    "cursor_invalid": "Pass the next_cursor value from the previous result unchanged, with the same profile.",
    "unauthorized": "Set EZMD_API_KEY to a valid key for the remote instance.",
    "forbidden": "This API key may not perform this action.",
    "rate_limited": "Wait a moment and try again.",
    "queue_unavailable": "The remote instance is busy. Try again shortly.",
    "remote_unavailable": "The remote ezmd instance could not be reached. Check --remote and your network.",
    "job_failed": "The conversion failed on the remote instance.",
    "not_implemented": "This feature is not available yet.",
    "internal_error": "An unexpected error occurred. Try again, or report it with the input type.",
}


def suggestion_for(code: str) -> str:
    """The user-facing suggested action for an error or warning code."""
    try:
        from ezmd.warnings import spec_for

        return spec_for(code).suggestion
    except (KeyError, ImportError):
        return _SUGGESTIONS.get(code, _SUGGESTIONS["internal_error"])


class ToolFailure(Exception):
    """A hard failure reported to the model as `isError: true`."""

    def __init__(self, code: str, message: str, *, detail: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = dict(detail or {})

    @property
    def suggestion(self) -> str:
        return suggestion_for(self.code)

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"code": self.code, "message": self.message, "suggestion": self.suggestion}
        if self.detail:
            out["detail"] = self.detail
        return out

    def text(self) -> str:
        return f"Error {self.code}: {self.message} Suggested action: {self.suggestion}"


def _netguard_code(exc: Exception) -> str:
    """Map a netguard refusal to the Part 4 codes (`fetch_refused_scheme`, `fetch_refused_private_network`).

    Netguard raises `UrlBlocked` for several reasons with one class; the message names the reason."""
    code = str(getattr(exc, "code", "url_blocked"))
    if code != "url_blocked":
        return code
    msg = str(exc)
    if msg.startswith("scheme "):
        return "fetch_refused_scheme"
    if "blocked range" in msg or "blocked address" in msg or (msg.startswith("host ") and "not allowed" in msg):
        return "fetch_refused_private_network"
    return "url_blocked"


def from_exception(exc: BaseException) -> ToolFailure:
    """Translate a library exception into a ToolFailure with a safe message. Unknown exceptions are logged
    (to stderr, never to the client) and reported as `internal_error`."""
    if isinstance(exc, ToolFailure):
        return exc
    from ezmd.core.netguard import NetguardError
    from ezmd.inputs import InputTooLarge
    from ezmd.registry import ConversionError

    if isinstance(exc, NetguardError):
        code = _netguard_code(exc)
        messages = {
            "fetch_refused_private_network": "The URL resolves to a private or local network address and was refused.",
            "fetch_refused_scheme": "Only http and https URLs can be fetched.",
            "url_blocked": f"The URL was refused: {str(exc)[:200]}",
            "fetch_failed": "The URL could not be fetched.",
            "input_too_large": "The fetched body is over the size limit.",
            "platform_disabled": "This site is disabled by policy.",
            "fetch_blocked_by_platform": "This platform blocks server-side fetches.",
        }
        return ToolFailure(code, messages.get(code, "The URL was refused."))
    if isinstance(exc, ConversionError):
        return ToolFailure(exc.code, exc.user_message)
    if isinstance(exc, InputTooLarge):
        return ToolFailure("input_too_large", "The input is over the size limit.")
    if isinstance(exc, FileNotFoundError):
        return ToolFailure("file_not_found", "The file does not exist.")
    if isinstance(exc, IsADirectoryError | PermissionError):
        return ToolFailure("file_not_found", "The path is not a readable file.")
    log.error("unexpected error in tool: %s", type(exc).__name__, exc_info=exc)
    return ToolFailure("internal_error", "An unexpected error occurred while converting.")
