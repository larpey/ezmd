"""Generate the email fixtures (self-authored text, CC0). Run: uv run python fixtures/comms/_generate.py

Deterministic: fixed Message-IDs, dates, and MIME boundaries. The PDF and DOCX attachments reuse the
self-generated fixtures/pdf/simple-table and fixtures/office/docx-structure inputs; the PNG is built here.
"""

from __future__ import annotations

import struct
import zlib
from email import policy
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NL = "\n"
CRLF = "\r\n"


def png_1x1() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x10\x80\xc0" * 2 for _ in range(2))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def fix_boundaries(msg: EmailMessage, prefix: str) -> None:
    n = 0
    for part in msg.walk():
        if part.is_multipart():
            n += 1
            part.set_boundary(f"=_{prefix}_{n}")


def base(subject: str, mid: str, date: str, frm: str = "Ann Reed <ann@example.org>") -> EmailMessage:
    m = EmailMessage(policy=policy.SMTP)
    m["From"] = frm
    m["To"] = "Bob Stone <bob@example.org>"
    m["Date"] = date
    m["Subject"] = subject
    m["Message-ID"] = mid
    return m


def write(name: str, ext: str, data: bytes) -> None:
    d = HERE / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"input.{ext}").write_bytes(data)


# ---------------------------------------------------------------------------


PLAIN = NL.join(
    [
        "Hi Bob,",
        "",
        "The heron count for the east marsh is done. We saw fourteen birds on ",
        "Tuesday and none on Wednesday because of the fog.",
        "",
        "Next steps:",
        "- send the tally to the field office",
        "- book the boat for Friday",
        "",
        "Thanks,",
        "Ann",
        "",
        "-- ",
        "Ann Reed",
        "East Marsh Survey",
        "",
        "On Mon, 30 Sep 2024 at 09:12, Bob Stone <bob@example.org> wrote:",
        "> Could you send the count when it is ready?",
        "> We need it before the Friday meeting.",
        "",
    ]
)


def eml_plain() -> bytes:
    m = base("Heron count", "<plain-1@example.org>", "Tue, 01 Oct 2024 10:00:00 +0200")
    m["Cc"] = "Field Office <office@example.org>"
    m["In-Reply-To"] = "<ask-0@example.org>"
    m["References"] = "<ask-0@example.org>"
    m.set_content(PLAIN, subtype="plain", charset="utf-8", params={"format": "flowed"}, cte="7bit")
    return m.as_bytes()


HTML_ONLY = """<html><head><title>Weekly report</title></head><body>
<p>Hello team,</p>
<p>Here is the <b>weekly report</b> for the marsh survey.</p>
<ul><li>Herons: 14</li><li>Egrets: 3</li></ul>
<table><tr><th>Site</th><th>Count</th></tr><tr><td>East</td><td>14</td></tr><tr><td>West</td><td>3</td></tr></table>
<div class="gmail_signature"><p>Carol Diaz, Survey Lead</p></div>
<div class="gmail_quote"><div class="gmail_attr">
On Fri, Sep 27, 2024 at 4:00 PM Ann Reed &lt;ann@example.org&gt; wrote:<br></div>
<blockquote class="gmail_quote"><p>Please post the weekly report on Monday.</p></blockquote></div>
</body></html>
"""


def eml_html_only() -> bytes:
    m = base(
        "Weekly report", "<html-1@example.org>", "Mon, 30 Sep 2024 08:30:00 -0400", "Carol Diaz <carol@example.org>"
    )
    m["Reply-To"] = "survey@example.org"
    m["List-Id"] = "Marsh survey <survey.example.org>"
    m.set_content(HTML_ONLY, subtype="html", charset="utf-8", cte="quoted-printable")
    return m.as_bytes()


ALT_TEXT = "Café meeting moved to Thursday.\n\nSee the map below.\n"
ALT_HTML = """<html><body><p>Café meeting moved to <em>Thursday</em>.</p>
<p>See the map below.</p><p><img src="cid:map1@example.org" alt="map of the café"></p></body></html>
"""


def eml_alternative() -> bytes:
    m = base("=?utf-8?q?R=C3=A9union_au_caf=C3=A9?=", "<alt-1@example.org>", "Wed, 02 Oct 2024 12:00:00 +0000")
    del m["From"]
    m["From"] = "=?utf-8?b?Sm9zw6kgw4FsdmFyZXo=?= <jose@example.org>"
    m.set_content(ALT_TEXT, charset="utf-8")
    m.add_alternative(ALT_HTML, subtype="html", charset="utf-8")
    html_part = m.get_payload()[1]
    html_part.add_related(png_1x1(), maintype="image", subtype="png", cid="<map1@example.org>", filename="map.png")
    fix_boundaries(m, "alt")
    return m.as_bytes()


CSV = "site,count\neast,14\nwest,3\n"


def eml_attachments() -> bytes:
    m = base("Survey files", "<att-1@example.org>", "Thu, 03 Oct 2024 09:00:00 +0000")
    m.set_content("Attached are the survey files: the report, the tally, and the raw sheet.\n")
    pdf = (ROOT / "pdf" / "simple-table" / "input.pdf").read_bytes()
    docx = (ROOT / "office" / "docx-structure" / "input.docx").read_bytes()
    m.add_attachment(pdf, maintype="application", subtype="pdf", filename="report.pdf")
    m.add_attachment(
        docx,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="method.docx",
    )
    m.add_attachment(CSV.encode(), maintype="text", subtype="csv", filename="tally.csv")
    m.add_attachment(bytes(range(256)) * 4, maintype="application", subtype="octet-stream", filename="raw.bin")
    m.add_attachment(b"\x78\x9f\x3e\x22" + bytes(60), maintype="application", subtype="ms-tnef", filename="winmail.dat")
    fix_boundaries(m, "att")
    return m.as_bytes()


def eml_forwarded() -> bytes:
    inner = base(
        "Boat booking", "<boat-1@example.org>", "Tue, 01 Oct 2024 15:00:00 +0000", "Dock Office <dock@example.org>"
    )
    inner.set_content("The boat is booked for Friday at 7am.\n")
    inner.add_attachment(b"Boat: Heron II\nSeats: 6\n", maintype="text", subtype="plain", filename="booking.txt")
    fix_boundaries(inner, "inner")
    m = base("Fwd: Boat booking", "<fwd-1@example.org>", "Tue, 01 Oct 2024 16:00:00 +0000")
    m.set_content("Forwarding the booking confirmation.\n")
    m.add_attachment(inner)
    fix_boundaries(m, "fwd")
    return m.as_bytes()


def mbox_thread() -> bytes:
    msgs: list[tuple[str, EmailMessage]] = []
    a = base("Field trip", "<t1@example.org>", "Mon, 07 Oct 2024 09:00:00 +0000")
    a["X-Gmail-Labels"] = "Inbox,Survey"
    a.set_content("Shall we go on Friday?\n\nFrom the dock, we can reach the east marsh in an hour.\n")
    b = base("Re: Field trip", "<t2@example.org>", "Mon, 07 Oct 2024 10:00:00 +0000", "Bob Stone <bob@example.org>")
    b.replace_header("To", "Ann Reed <ann@example.org>")
    b["In-Reply-To"] = "<t1@example.org>"
    b["References"] = "<t1@example.org>"
    b.set_content("Friday works.\n\n> Shall we go on Friday?\n")
    c = base("Re: Field trip", "<t3@example.org>", "Mon, 07 Oct 2024 11:00:00 +0000")
    c["In-Reply-To"] = "<t2@example.org>"
    c["References"] = "<t1@example.org> <t2@example.org>"
    c.set_content("Great, see you at the dock.\n")
    d = base("Gear list", "<g1@example.org>", "Tue, 08 Oct 2024 09:00:00 +0000", "Carol Diaz <carol@example.org>")
    d.replace_header("To", "Ann Reed <ann@example.org>")
    d.set_content("Bring waders and the spotting scope.\n")
    e = base("Re: Gear list", "<g2@example.org>", "Tue, 08 Oct 2024 12:00:00 +0000")
    e.replace_header("To", "Carol Diaz <carol@example.org>")
    e.set_content("Will do. I lost the original thread headers, sorry.\n")
    msgs = [("ann@example.org", a), ("bob@example.org", b), ("ann@example.org", c), ("carol@example.org", d)]
    msgs.append(("ann@example.org", e))
    out: list[str] = []
    for sender, msg in msgs:
        body = msg.as_string(policy=policy.default.clone(linesep=NL))
        body = NL.join((">" + line) if line.startswith("From ") else line for line in body.split(NL))
        out.append(f"From {sender} Mon Oct  7 09:00:00 2024{NL}{body}{NL}")
    return "".join(out).encode("utf-8")


def eml_broken_charset() -> bytes:
    head = CRLF.join(
        [
            "From: =?x-unknown-8bit?q?M=FCller?= <muller@example.org>",
            "To: bob@example.org",
            "Subject: Résumé des comptages",
            "Date: Fri, 04 Oct 2024 08:00:00 +0200",
            "Message-ID: <broken-1@example.org>",
            "MIME-Version: 1.0",
            'Content-Type: text/plain; charset="us-ascii"',
            "Content-Transfer-Encoding: 8bit",
            "",
            "",
        ]
    ).encode("utf-8")
    body = "Les hérons sont revenus à l'étang. Déjà quatorze oiseaux comptés.\r\n".encode("cp1252")
    return head + body


def eml_hostile() -> bytes:
    to = ", ".join(f"user{i}@example.org" for i in range(2500))
    inner = base("Level 6", "<deep-6@example.org>", "Sat, 05 Oct 2024 00:00:00 +0000")
    inner.set_content("The innermost message.\n")
    for level in range(5, 0, -1):
        outer = base(f"Level {level}", f"<deep-{level}@example.org>", "Sat, 05 Oct 2024 00:00:00 +0000")
        outer.set_content(f"Message at level {level}.\n")
        outer.add_attachment(inner)
        fix_boundaries(outer, f"d{level}")
        inner = outer
    raw = inner.as_bytes()
    cc = ", ".join(f"Copy {i} <copy{i}@example.org>" for i in range(1500))
    hostile = (
        f"To: {to}\r\nCc: {cc}\r\nX-Huge: {'A' * 70000}\r\n"
        # CR/LF smuggled through an encoded word must not create a Bcc header; NUL and a bidi override
        # (U+202E) in the subject must be removed.
        "X-Note: =?utf-8?q?first_line=0D=0ABcc:_evil@example.org?=\r\n"
        "Subject: =?utf-8?q?Invoice_=00=E2=80=AEfdp.exe?=\r\n"
    ).encode()
    raw = raw.replace(b"To: Bob Stone <bob@example.org>\r\n", hostile, 1)
    return raw.replace(b"Subject: Level 1\r\n", b"", 1)


MSG_HTML = """<html><body><p>Hello Bob,</p><p>The <b>quarterly plan</b> is attached.</p>
<ul><li>Count herons in March</li><li>Count egrets in June</li></ul></body></html>"""


def _rtf_from_html(html: str) -> bytes:
    """Wrap HTML the way Outlook encapsulates it in RTF (MS-OXRTFEX): tags in htmltag groups, text outside."""
    import re

    out = [r"{\rtf1\ansi\ansicpg1252\fromhtml1 \deff0{\fonttbl{\f0\fswiss Arial;}}"]
    for token in re.split(r"(<[^>]+>)", html.replace(NL, "")):
        if not token:
            continue
        if token.startswith("<"):
            out.append(r"{\*\htmltag64 " + token + "}")
        else:
            out.append(r"\htmlrtf0 " + token + r" \htmlrtf")
    out.append("}")
    return "".join(out).encode("cp1252")


def msg_outlook() -> bytes:
    """An Outlook message: RTF-encapsulated HTML body (compressed RTF only), transport headers, recipients,
    two attachments, and one embedded message (docs/spec/part2.md 9f fixture 4)."""
    from _cfb import MsgAttachment, MsgSpec, compress_rtf, write_msg

    from intomd_converters.comms.rtf import PREBUF

    transport = CRLF.join(
        [
            "Received: from mx.example.org by mail.example.org; Tue, 01 Oct 2024 09:00:00 +0000",
            "Message-ID: <plan-1@example.org>",
            "Subject: Quarterly plan",
            "Date: Tue, 01 Oct 2024 09:00:00 +0000",
            "List-Id: Survey plans <plans.example.org>",
            "",
        ]
    )
    embedded = MsgSpec(
        strings={0x0037: "Boat schedule", 0x0C1A: "Dock Office", 0x5D01: "dock@example.org", 0x1000: "Boat at 7am."},
        times={0x0039: 1727712000},
        recipients=[("Ann Reed", "ann@example.org", 1)],
    )
    spec = MsgSpec(
        strings={
            0x0037: "Quarterly plan",
            0x0C1A: "Ann Reed",
            0x5D01: "ann@example.org",
            0x001A: "IPM.Note",
            0x007D: transport,
        },
        binary={0x1009: compress_rtf(_rtf_from_html(MSG_HTML), PREBUF)},
        times={0x0039: 1727773200},
        recipients=[("Bob Stone", "bob@example.org", 1), ("Field Office", "office@example.org", 2)],
        attachments=[
            MsgAttachment("plan.csv", CSV.encode(), "text/csv"),
            MsgAttachment("notes.txt", b"Bring waders.\nMeet at the dock.\n", "text/plain"),
            MsgAttachment("Boat schedule.msg", embedded=embedded),
        ],
    )
    return write_msg(spec)


def main() -> None:
    write("eml-plain-flowed", "eml", eml_plain())
    write("eml-html-only", "eml", eml_html_only())
    write("eml-alternative-cid", "eml", eml_alternative())
    write("eml-attachments", "eml", eml_attachments())
    write("eml-forwarded", "eml", eml_forwarded())
    write("mbox-threads", "mbox", mbox_thread())
    write("eml-broken-charset", "eml", eml_broken_charset())
    write("eml-hostile", "eml", eml_hostile())
    write("msg-outlook", "msg", msg_outlook())


if __name__ == "__main__":
    main()
