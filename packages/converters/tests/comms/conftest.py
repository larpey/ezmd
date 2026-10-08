from __future__ import annotations

from collections.abc import Callable
from email import policy
from email.message import EmailMessage

import pytest

from ezmd.inputs import InputRef
from ezmd.ir import ConversionResult
from ezmd.pipeline import convert_ref
from ezmd.registry import ConvertOptions


def make_message(
    subject: str = "Hello",
    body: str = "Hi there.\n",
    *,
    mid: str = "<m1@example.org>",
    frm: str = "Ann Reed <ann@example.org>",
    to: str = "Bob Stone <bob@example.org>",
    date: str = "Tue, 01 Oct 2024 10:00:00 +0000",
) -> EmailMessage:
    m = EmailMessage(policy=policy.SMTP)
    m["From"] = frm
    m["To"] = to
    m["Date"] = date
    m["Subject"] = subject
    m["Message-ID"] = mid
    m.set_content(body)
    return m


Convert = Callable[..., ConversionResult]
MakeMessage = Callable[..., EmailMessage]


@pytest.fixture
def mk() -> MakeMessage:
    return make_message


@pytest.fixture
def convert() -> Convert:
    def run(
        data: bytes, name: str = "message.eml", options: ConvertOptions | None = None, **extra: object
    ) -> ConversionResult:
        opts = options or ConvertOptions()
        opts.extra.update({f"comms.{k}": v for k, v in extra.items()})  # type: ignore[misc]
        ref = InputRef.from_bytes(data, filename=name)
        try:
            return convert_ref(ref, opts)
        finally:
            ref.cleanup()

    return run
