"""Regressions from the P1-T04 golden review: fixed lines, line breaks in text attachments, header hygiene,
charset warnings, and detection of messages with HTML bodies."""

from __future__ import annotations

from email import policy

from intomd.detect import detect, looks_like_rfc822
from intomd.inputs import InputRef
from intomd.ir import Paragraph, Provenance, Quote, Table, WarningKind, spans_text
from intomd_converters.comms.body_text import logical_lines, text_blocks
from intomd_converters.comms.build import table_rows


def _texts(blocks) -> list[str]:
    return [spans_text(b.spans) for b in blocks if isinstance(b, Paragraph)]


def test_flowed_fixed_lines_stay_separate() -> None:
    text = "We saw fourteen birds on \nTuesday.\n\nThanks,\nAnn\n\n-- \nAnn Reed\nEast Marsh\n"
    blocks = text_blocks(text, Provenance(source="x"), flowed=True)
    assert _texts(blocks) == ["We saw fourteen birds on Tuesday.", "Thanks,\nAnn", "Ann Reed\nEast Marsh"]
    assert blocks[1].attrs == {"line_breaks": "hard"}
    assert blocks[-1].attrs == {"role": "signature", "line_breaks": "hard"}


def test_flowed_quote_lines_without_soft_break_stay_separate() -> None:
    text = "On Mon, 30 Sep 2024, Bob wrote:\n> First line.\n> Second line.\n> soft \n> continued.\n"
    quote = next(b for b in text_blocks(text, Provenance(source="x"), flowed=True) if isinstance(b, Quote))
    parts = [s.text for s in quote.spans if s.text != "\n\n"]
    assert parts == ["First line.", "Second line.", "soft continued."]


def test_unflowed_wrap_rule() -> None:
    assert logical_lines(["Boat: Heron II", "Seats: 6"], flowed=False) == ["Boat: Heron II", "Seats: 6"]
    assert logical_lines(["The count is", "done today."], flowed=False) == ["The count is done today."]
    long = "The heron count for the east marsh is finished and the tally is in the"
    assert logical_lines([long, "Field office folder."], flowed=False) == [f"{long} Field office folder."]


def test_text_attachment_keeps_line_breaks(convert, mk) -> None:
    m = mk("Booking", "See attached.\n")
    m.add_attachment(b"Boat: Heron II\nSeats: 6\n", maintype="text", subtype="plain", filename="booking.txt")
    child = convert(m.as_bytes()).document.children[0]
    assert _texts(child.blocks) == ["Boat: Heron II\nSeats: 6"]
    assert child.blocks[0].attrs["line_breaks"] == "hard"


def test_header_injection_nul_and_bidi_are_neutralized(convert) -> None:
    raw = (
        b"From: a@x.org\r\nTo: b@x.org\r\nDate: Wed, 02 Oct 2024 12:00:00 +0000\r\n"
        b"Subject: =?utf-8?q?Invoice_=00=E2=80=AEfdp.exe?=\r\n"
        b"Reply-To: =?utf-8?q?x=0D=0ABcc:_evil@example.org?= <r@x.org>\r\n\r\nBody.\r\n"
    )
    doc = convert(raw).document
    rows = dict(table_rows(next(b for b in doc.blocks if isinstance(b, Table))))
    assert rows["Subject"] == "Invoice fdp.exe"
    assert "Bcc" not in rows
    assert "\n" not in rows["Reply-To"] and "\r" not in rows["Reply-To"]
    assert all(chr(0) not in v and chr(0x202E) not in v for v in rows.values())
    hidden = next(w for w in doc.warnings if w.kind == WarningKind.REMOVED_HIDDEN_ELEMENTS)
    assert hidden.detail["where"] == "headers" and hidden.count == 3  # NUL, U+202E, and the CR/LF pair


def test_huge_real_to_and_cc_are_cut_consistently(convert) -> None:
    to = ", ".join(f"user{i}@example.org" for i in range(3000))
    cc = ", ".join(f"Copy {i} <c{i}@example.org>" for i in range(3000))
    raw = f"From: a@x.org\r\nTo: {to}\r\nCc: {cc}\r\nSubject: Big\r\n\r\nBody.\r\n".encode()
    result = convert(raw, max_header_chars=4000)
    doc = result.document
    rows = dict(table_rows(next(b for b in doc.blocks if isinstance(b, Table))))
    assert 0 < len(rows["To"]) <= 4000 and 0 < len(rows["Cc"]) <= 4000
    import re

    for key in ("To", "Cc"):
        kept, marker = rows[key].split(" … ")
        assert re.fullmatch(r"\(\d+ more recipients truncated\)", marker)
        last = kept.rsplit(", ", 1)[-1]
        assert re.fullmatch(r"(user\d+@example\.org|Copy (\d+) <c\2@example\.org>)", last), last
        total = 3000
        assert len(kept.split(", ")) + int(marker.split()[0][1:]) == total
    assert all(len(str(e["value"])) <= 4000 for e in doc.sidecar_extra["email_headers"])
    w = next(w for w in doc.warnings if w.kind == WarningKind.TRUNCATED)
    assert w.count == 2 and w.detail["max_chars"] == 4000


def test_mislabeled_body_and_unknown_word_charset_warn(convert) -> None:
    raw = (
        b"From: =?x-unknown-8bit?q?M=FCller?= <m@x.org>\r\nSubject: s\r\nDate: Wed, 02 Oct 2024 12:00:00 +0000\r\n"
        b'Content-Type: text/plain; charset="us-ascii"\r\nContent-Transfer-Encoding: 8bit\r\n\r\n'
        + "Déjà vu.".encode("cp1252")
    )
    doc = convert(raw).document
    reasons = {w.detail.get("reason") for w in doc.warnings if w.kind == WarningKind.ENCODING_UNCERTAIN}
    assert reasons == {"unknown_header_charset", "declared_charset_mismatch"}


def test_rfc822_with_html_body_is_detected_as_email(mk) -> None:
    m = mk("Report", "x\n")
    m.clear_content()
    m.set_content("<html><body><p>Hello</p><table><tr><td>1</td></tr></table></body></html>", subtype="html")
    data = m.as_bytes(policy=policy.SMTP)
    for name in ("r.eml", "r"):
        ref = InputRef.from_bytes(data, filename=name)
        assert detect(ref).mime == "message/rfc822"
    assert not looks_like_rfc822(b"From sender@x Mon Oct  7 09:00:00 2024\nFrom: a@x.org\n")
    assert not looks_like_rfc822(b"Title: notes\nAuthor: me\n\ntext")


NOTES_MD = b"Title: Field notes\nFrom: Ann Reed\nDate: 2024-10-01\n\n# Herons\n\nFourteen at the east marsh.\n"
HTTP_DUMP = (
    b"Date: Tue, 01 Oct 2024 10:00:00 GMT\nFrom: crawler@example.org\nServer: nginx\nContent-Type: text/html\n\n"
)
REAL = (
    b"Received: from mx.example.org by mail.example.org\r\nFrom: Ann <ann@example.org>\r\nTo: b@example.org\r\n"
    b"Subject: Hi\r\nMessage-ID: <x1@example.org>\r\nMIME-Version: 1.0\r\nContent-Type: text/html\r\n\r\n"
    b"<html><body><p>Hello</p></body></html>\r\n"
)


def test_markdown_notes_with_header_like_lines_stay_markdown(convert) -> None:
    ref = InputRef.from_bytes(NOTES_MD, filename="notes.md")
    assert detect(ref).mime != "message/rfc822"
    result = convert(NOTES_MD, name="notes.md")
    assert result.converter_id != "comms.eml"
    assert not any(w.kind == WarningKind.MISNAMED_FILE for w in result.all_warnings)


def test_http_header_dump_is_not_email() -> None:
    assert not looks_like_rfc822(HTTP_DUMP)
    assert detect(InputRef.from_bytes(HTTP_DUMP + b"<html><body>x</body></html>", filename="dump")).mime != (
        "message/rfc822"
    )


def test_leading_non_header_lines_are_not_email() -> None:
    assert not looks_like_rfc822(b"Meeting notes\nFrom: a@x.org\nMessage-ID: <1@x>\n\nbody")


def test_real_email_with_odd_extensions(convert) -> None:
    for name in ("saved.html", "message.txt", "export.dat", "noext"):
        assert detect(InputRef.from_bytes(REAL, filename=name)).mime == "message/rfc822", name
        assert convert(REAL, name=name).converter_id == "comms.eml", name
    weak = b"From: a@x.org\nMessage-ID: <1@x>\nSubject: s\n\nbody\n"
    assert looks_like_rfc822(weak) and not looks_like_rfc822(weak, ".md")
