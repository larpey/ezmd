from __future__ import annotations

from email import policy

from ezmd.ir import Heading, Paragraph, WarningKind, spans_text
from ezmd_converters.comms.model import ParsedMessage
from ezmd_converters.comms.threads import build_threads, normalize_subject

NL = "\n"


def mbox(*messages, escape: bool = True) -> bytes:
    out = []
    for m in messages:
        text = m.as_string(policy=policy.default.clone(linesep=NL))
        if escape:
            text = NL.join((">" + x) if x.startswith("From ") else x for x in text.split(NL))
        out.append(f"From sender@example.org Mon Oct  7 09:00:00 2024{NL}{text}{NL}")
    return "".join(out).encode()


def _thread_mail(mk):
    a = mk("Trip", "Friday?\n", mid="<a@x>", date="Mon, 07 Oct 2024 09:00:00 +0000")
    b = mk("Re: Trip", "Yes.\n", mid="<b@x>", date="Mon, 07 Oct 2024 10:00:00 +0000", frm="Bob <bob@example.org>")
    b["In-Reply-To"] = "<a@x>"
    b["References"] = "<a@x>"
    c = mk("Gear", "Waders.\n", mid="<c@x>", date="Mon, 07 Oct 2024 09:30:00 +0000", frm="Carol <carol@example.org>")
    d = mk("RE: [survey] Gear", "Ok.\n", mid="<d@x>", date="Mon, 07 Oct 2024 12:00:00 +0000", to="carol@example.org")
    return a, b, c, d


def test_mbox_threads_and_message_sections(convert, mk) -> None:
    a, b, c, d = _thread_mail(mk)
    result = convert(mbox(a, c, b, d), name="mail.mbox")
    doc = result.document
    assert result.converter_id == "comms.mbox"
    h1 = [spans_text(h.spans) for h in doc.blocks if isinstance(h, Heading) and h.level == 1]
    assert h1 == ["Trip", "Gear"]
    h2 = [h for h in doc.blocks if isinstance(h, Heading) and h.level == 2]
    assert [spans_text(h.spans).split(" · ")[0] for h in h2] == [
        "Ann Reed <ann@example.org>",
        "Bob <bob@example.org>",
        "Carol <carol@example.org>",
        "Ann Reed <ann@example.org>",
    ]
    assert [h.attrs["depth"] for h in h2] == ["0", "1", "0", "1"]
    assert doc.metadata.extra["messages"] == 4 and doc.metadata.extra["threads"] == 2
    assert {b.provenance.path.split("/")[1] for b in doc.blocks if b.provenance.path and "/" in b.provenance.path} == {
        "1",
        "2",
        "3",
        "4",
    }


def test_mbox_detected_without_extension(convert, mk) -> None:
    a, b, *_ = _thread_mail(mk)
    assert convert(mbox(a, b), name="export").converter_id == "comms.mbox"
    assert convert(a.as_bytes(), name="export").converter_id == "comms.eml"


def test_escaped_from_lines_are_unescaped(convert, mk) -> None:
    m = mk("Dock", "We leave at 7.\nFrom the dock, it is an hour.\n")
    doc = convert(mbox(m), name="x.mbox").document
    text = " ".join(spans_text(p.spans) for p in doc.blocks if isinstance(p, Paragraph))
    assert "From the dock" in text and ">From" not in text


def test_unescaped_from_in_body_is_merged_back(convert, mk) -> None:
    m = mk("Dock", "We leave at 7.\n\nFrom the dock it is an hour.\n")
    data = mbox(m, mk("Other", "second\n", mid="<o@x>"), escape=False)
    doc = convert(data, name="x.mbox").document
    assert doc.metadata.extra["messages"] == 2
    assert doc.metadata.extra["merged_splits"] == 1
    text = " ".join(spans_text(p.spans) for p in doc.blocks if isinstance(p, Paragraph))
    assert "From the dock it is an hour." in text


def test_max_messages_truncates_with_warning(convert, mk) -> None:
    msgs = [mk(f"Note {i}", f"body {i}\n", mid=f"<n{i}@x>") for i in range(5)]
    result = convert(mbox(*msgs), name="x.mbox", max_messages=3)
    doc = result.document
    assert doc.metadata.extra["messages"] == 3
    w = next(w for w in doc.warnings if w.kind == WarningKind.TRUNCATED)
    assert w.detail["reason"] == "max_messages"
    assert result.truncated and doc.truncated


def test_gmail_labels(convert, mk) -> None:
    m = mk("Labelled", "x\n")
    m["X-Gmail-Labels"] = "Inbox,Important"
    doc = convert(mbox(m), name="takeout.mbox").document
    assert any("Inbox, Important" in spans_text(c.spans) for t in doc.blocks if hasattr(t, "cells") for c in t.cells)


def _pm(subject: str, mid: str, date: str | None = None, refs: str = "", frm: str = "a@x.org") -> ParsedMessage:
    from email.utils import parsedate_to_datetime

    pm = ParsedMessage(headers={"Subject": subject, "Message-ID": mid, "References": refs, "From": frm})
    pm.date = parsedate_to_datetime(date) if date else None
    return pm


def test_thread_builder_handles_cycles_and_missing_dates() -> None:
    a = _pm("Loop", "<a@x>", refs="<b@x>")
    b = _pm("Loop", "<b@x>", refs="<a@x>")
    c = _pm("Solo", "<c@x>", "Mon, 07 Oct 2024 09:00:00 +0000")
    threads = build_threads([a, b, c])
    assert sorted(i for t in threads for i, _ in t.members) == [0, 1, 2]


def test_subject_fallback_needs_shared_participant_and_window() -> None:
    a = _pm("Plan", "<a@x>", "Mon, 07 Oct 2024 09:00:00 +0000")
    b = _pm("Re: Plan", "<b@x>", "Tue, 08 Oct 2024 09:00:00 +0000")
    stranger = _pm("Re: Plan", "<c@x>", "Tue, 08 Oct 2024 09:00:00 +0000", frm="z@other.org")
    late = _pm("Re: Plan", "<d@x>", "Mon, 25 Nov 2024 09:00:00 +0000")
    threads = build_threads([a, b, stranger, late])
    assert [len(t.members) for t in threads] == [2, 1, 1]
    assert normalize_subject("RE: Fwd: [list] AW: Plan") == "plan"
