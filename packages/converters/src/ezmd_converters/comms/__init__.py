"""Communication family, email part (docs/spec/part2.md section 9): EML, MBOX, and Outlook MSG.

- `comms.eml`: one RFC 5322 message (stdlib `email`, `policy.default`).
- `comms.mbox`: a Unix mailbox (stdlib `mailbox`), threaded, capped at `comms.max_messages`.
- `comms.msg`: Outlook .msg through a native olefile (BSD-2-Clause) reader.
- `comms.msg_extract`: extract-msg (GPL-3.0) fallback, only with the `nonfree` extra; `Unavailable` otherwise.

Attachments (and forwarded messages) are converted recursively through `options.ctx.convert_child`.
Chat exports, ICS, and VCF (also section 9) are separate tasks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ezmd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    "message/rfc822": ["comms.mbox", "comms.eml"],
    "message/global": ["comms.eml"],
    "application/mbox": ["comms.mbox"],
    "application/vnd.ms-outlook": ["comms.msg", "comms.msg_extract"],
}
"""Detection labels a mailbox `message/rfc822` (its first message looks like an EML), so the mailbox converter
is tried first and declines anything that does not start with a `From ` line."""


def converters() -> list[Converter | Unavailable]:
    from ezmd.registry import Unavailable
    from ezmd_converters.comms import msg
    from ezmd_converters.comms.eml import EmlConverter
    from ezmd_converters.comms.mbox import MboxConverter

    out: list[Converter | Unavailable] = [EmlConverter(), MboxConverter(), msg.MsgConverter()]
    if msg.extract_msg_available():
        out.append(msg.ExtractMsgConverter())
    else:
        out.append(
            Unavailable(
                id="comms.msg_extract",
                family="comms",
                reason="the extract-msg fallback for Outlook .msg (GPL-3.0) is installed by the optional nonfree extra",
                requires_extras=("nonfree",),
            )
        )
    return out
