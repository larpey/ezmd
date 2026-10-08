"""Outlook .msg converters (docs/spec/part2.md 9b step 2, 9c step 7).

- `comms.msg`: the default, a native reader on olefile (BSD-2-Clause) in `comms.msg_native`.
- `comms.msg_extract`: extract-msg (GPL-3.0) from the `nonfree` extra, second in the chain; it runs only when
  the native reader fails. Registered as `Unavailable` when the extra is missing.
"""

from __future__ import annotations

import importlib.util

from ezmd.context import Limits
from ezmd.inputs import InputRef
from ezmd.ir import Document, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.comms.build import MessageSpec, build_message
from ezmd_converters.comms.eml import SIDECAR_KEY, message_metadata
from ezmd_converters.comms.model import ParsedMessage
from ezmd_converters.comms.options import CommsOptions, read_options

MSG_MIMES = ("application/vnd.ms-outlook", "application/x-msg")
OLE_MIMES = (*MSG_MIMES, "application/cdfv2", "application/x-ole-storage", "application/octet-stream")
OLE_MAGIC = bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])
SUBSTG = "__substg1.0_".encode("utf-16-le")
DEFAULT_MAX_BYTES = 200 * 1024 * 1024
LIMITS = Limits(max_bytes=DEFAULT_MAX_BYTES, max_depth=3, timeout_s=300.0)


def extract_msg_available() -> bool:
    try:
        return importlib.util.find_spec("extract_msg") is not None
    except (ImportError, ValueError):
        return False


def looks_like_msg(ref: InputRef) -> bool:
    head = ref.head(256 * 1024)
    return head.startswith(OLE_MAGIC) and SUBSTG in head


def _score(ref: InputRef) -> float:
    mime = ref.detected.mime if ref.detected else None
    if not ref.has_body or mime not in OLE_MIMES:
        return 0.0
    if looks_like_msg(ref):
        return 1.0
    if mime in MSG_MIMES:
        return 0.9
    return 0.0


def _check_size(ref: InputRef, options: ConvertOptions) -> None:
    cap = options.ctx.limits.max_bytes or DEFAULT_MAX_BYTES
    if ref.size() > cap:
        raise ConversionError(
            f"{ref.display} exceeds the {cap} byte cap",
            user_message="This email is larger than the size limit.",
            retryable_with_fallback=False,
        )


def _document(
    parsed: ParsedMessage, ref: InputRef, options: ConvertOptions, opts: CommsOptions, engine: str
) -> Document:
    built = build_message(parsed, MessageSpec(source=ref.display), options, opts)
    doc = Document(
        metadata=message_metadata(parsed, built, ref.display, ref.detected.mime if ref.detected else None),
        blocks=built.blocks,
        warnings=built.warnings,
        children=built.children,
        truncated=parsed.truncated,
    )
    doc.metadata.extra["engine"] = engine
    if built.headers_sidecar:
        doc.sidecar_extra[SIDECAR_KEY] = built.headers_sidecar
    return doc.finalize()


class MsgConverter:
    id = "comms.msg"
    family = "comms"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = MSG_MIMES
    limits = LIMITS

    def can_handle(self, ref: InputRef) -> float:
        return _score(ref)

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        from ezmd_converters.comms import msg_native

        _check_size(ref, options)
        opts = read_options(options)
        try:
            parsed = msg_native.read_msg(ref.read(), opts)
        except msg_native.MsgReadError as e:
            raise ConversionError(f"{ref.display}: {e}", user_message="This Outlook message could not be read.") from e
        if not parsed.headers.get("Subject") and not parsed.text and not parsed.html and not parsed.attachments:
            parsed.warnings.append(
                Warning(
                    kind=WarningKind.MSG_PARTIAL, message="The Outlook message has no subject, body, or attachments."
                )
            )
        return _document(parsed, ref, options, opts, msg_native.ENGINE_VERSION)


class ExtractMsgConverter:
    id = "comms.msg_extract"
    family = "comms"
    priority = 5
    experimental = False
    requires_extras: tuple[str, ...] = ("nonfree",)
    mimes: tuple[str, ...] = MSG_MIMES
    limits = LIMITS

    def can_handle(self, ref: InputRef) -> float:
        return _score(ref) * 0.9

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        from ezmd_converters.comms import msg_engine

        _check_size(ref, options)
        opts = read_options(options)
        try:
            m = msg_engine.open_msg(str(ref.path()))
        except Exception as e:  # extract-msg raises many unrelated types on corrupt CFB input
            raise ConversionError(
                f"extract-msg could not open {ref.display}: {type(e).__name__}",
                user_message="This Outlook message could not be read.",
            ) from e
        try:
            parsed = msg_engine.to_parsed(m, opts)
        finally:
            close = getattr(m, "close", None)
            if callable(close):
                close()
        return _document(parsed, ref, options, opts, f"extract-msg {msg_engine.ENGINE_VERSION}")
