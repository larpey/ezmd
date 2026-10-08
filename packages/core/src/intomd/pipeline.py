"""intomd.pipeline: the one conversion path every interface uses (detect -> validate -> route -> convert).

The CLI, the API worker, the MCP server, and the library all call `convert_ref`; none of them may
contain conversion logic of their own (docs/spec/part4.md section 4.0 rule 1).
"""

from __future__ import annotations

from intomd.detect import EMPTY_MIME, detect, is_executable, is_textual, normalize_mime
from intomd.inputs import InputRef
from intomd.ir import ConversionResult, Warning, WarningKind
from intomd.registry import ConversionError, ConverterRegistry, ConvertOptions, default_registry


class UnsupportedMediaType(ConversionError):
    """The detected type is refused outright (executables). Maps to HTTP 415 / CLI exit code 6."""

    def __init__(self, mime: str) -> None:
        super().__init__(
            f"refusing executable input ({mime})",
            user_message="Executable files are not accepted.",
            retryable_with_fallback=False,
        )
        self.mime = mime


def convert_ref(
    ref: InputRef,
    options: ConvertOptions | None = None,
    *,
    converter_id: str | None = None,
    registry: ConverterRegistry | None = None,
    mime_override: str | None = None,
) -> ConversionResult:
    """Detect `ref` (unless already detected), refuse executables, and run the registry's chain.

    Raises ConversionError (including UnsupportedMediaType) or FetchRequired.
    """
    opts = options or ConvertOptions()
    reg = registry or default_registry()
    if ref.detected is None:
        detect(ref)
    assert ref.detected is not None
    if mime_override:
        ref.detected.mime = normalize_mime(mime_override) or ref.detected.mime
    if is_executable(ref.detected.mime):
        raise UnsupportedMediaType(ref.detected.mime)
    extra: list[Warning] = []
    declared = normalize_mime(ref.declared_mime)
    detected = ref.detected.mime
    if (
        declared
        and declared not in ("application/octet-stream", detected)
        and detected not in (EMPTY_MIME, "text/x-uri")
        and not (is_textual(declared) and is_textual(detected))
    ):
        extra.append(
            Warning(
                kind=WarningKind.CONTENT_TYPE_MISMATCH,
                message=f"Declared type {declared} did not match detected type {detected}; used the detected type.",
                detail={"declared": declared, "detected": detected},
            )
        )
    ext_mime = ref.detected.extension_mime
    if (
        ext_mime
        and ext_mime != detected
        and detected not in (EMPTY_MIME,)
        and not (is_textual(ext_mime) and is_textual(detected))
    ):
        extra.append(
            Warning(
                kind=WarningKind.MISNAMED_FILE,
                message=f"The file extension suggests {ext_mime} but the content is {detected}.",
                detail={"extension_mime": ext_mime, "detected": detected},
            )
        )
    result = reg.convert(ref, opts, converter_id=converter_id)
    if extra:
        result.warnings = [*extra, *result.warnings]
    return result
