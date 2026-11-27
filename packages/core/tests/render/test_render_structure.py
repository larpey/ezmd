"""Headings (title, shift, clamp, numbering, anchors, truncation), footnotes, transcripts, head blocks."""

from __future__ import annotations

from render_builders import heading, make_result, para, prov, span

from ezmd.ir import Footnote, Paragraph, TranscriptSegment
from ezmd.render import render


def _headings_chaos():  # type: ignore[no-untyped-def]
    long = "Word " * 70
    return make_result(
        [
            heading("Doc Title", 1),
            para("Intro."),
            heading("1. Introduction:", 1),
            heading("Background", 2),
            heading("Deep jump", 5),
            heading("3.2 Pre-numbered", 2),
            heading(long.strip(), 2),
            heading("Second top", 1),
            heading("a", 2),
            heading("b", 3),
            heading("c", 4),
            heading("d", 5),
            heading("e", 6),
        ],
        title=None,
    )


def test_single_h1_title_shift_clamp_and_numbering() -> None:
    out = render(_headings_chaos(), "full")
    body = out.body
    assert body.count("\n# ") + body.startswith("# ") == 1
    assert "# Doc Title {#doc}" in body
    assert "## 1 Introduction {#sec-1}" in body
    assert "### 1.1 Background {#sec-1-1}" in body
    assert "#### 1.1.1 Deep jump {#sec-1-1-1}" in body
    assert "### 1.2 Pre-numbered {#sec-1-2}" in body
    assert "## 2 Second top {#sec-2}" in body
    assert "###### 2.1.1.1.1 d {#sec-2-1-1-1-1}" in body
    assert "\n**e**\n" in body
    assert out.frontmatter["title"] == "Doc Title"
    sections = out.sidecar["sections"]  # type: ignore[index]
    pre = next(s for s in sections if s["block_id"] == _headings_chaos().document.blocks[5].id)
    assert pre["original_title"] == "3.2 Pre-numbered" and pre["original_level"] == 2


def _agreement():  # type: ignore[no-untyped-def]
    return make_result(
        [
            heading("Deposit Agreement", 1),
            para("Intro."),
            heading("I. Definitions", 1),
            heading("A. Personal accounts", 2),
            heading("31. Our liability", 1),
            heading("31.1 Transfers we fail to complete", 2),
            heading("Schedule of fees", 1),
            heading("Appendix B Rates", 1),
        ],
        title=None,
    )


def test_a_document_that_numbers_its_own_sections_keeps_its_numbers() -> None:
    """Derived numbers would turn "31.1" into "2.1" and double-number letters ("1.1 A. Personal")."""
    body = render(_agreement(), "full").body
    assert "## I. Definitions {#sec-1}" in body
    assert "### A. Personal accounts {#sec-1-1}" in body
    assert "## 31. Our liability {#sec-2}" in body
    assert "### 31.1 Transfers we fail to complete {#sec-2-1}" in body
    assert "## Schedule of fees {#sec-3}" in body
    assert "## Appendix B Rates {#sec-4}" in body
    assert "1.1 A." not in body and "2.1 31.1" not in body


def test_two_numbered_headings_do_not_switch_numbering_off() -> None:
    doc = make_result([heading("Doc", 1), heading("1. Intro", 1), heading("Body", 1), heading("2. End", 1)], title=None)
    body = render(doc, "full").body
    assert "## 1 Intro {#sec-1}" in body and "## 2 Body {#sec-2}" in body and "## 3 End {#sec-3}" in body


def test_a_title_word_is_not_a_section_label() -> None:
    doc = make_result(
        [heading("Doc", 1), heading("A Guide to tides", 1), heading("I think so", 1), heading("Part of it", 1)],
        title=None,
    )
    body = render(doc, "full").body
    assert "## 1 A Guide to tides {#sec-1}" in body and "## 3 Part of it {#sec-3}" in body


def test_a_heading_longer_than_any_heading_is_a_paragraph_once() -> None:
    """Cut at 200 characters and repeated in full below it, a styled paragraph read twice (D-0087)."""
    out = render(_headings_chaos(), "full")
    body = out.body
    full_text = ("Word " * 70).strip()
    assert body.count(full_text) == 1 and f"\n\n{full_text}\n\n" in body
    assert not any(x.startswith("#") and "Word Word" in x for x in body.split("\n"))
    assert "### 1.3 " not in body and "## 2 Second top {#sec-2}" in body
    assert all("Word Word" not in s["title"] for s in out.sidecar["sections"])  # type: ignore[index]


def test_a_first_paragraph_that_repeats_the_title_is_consumed() -> None:
    doc = make_result(
        [para("Harbor Lane Survey."), para("The survey covers the outer berths.")], title="Harbor Lane Survey"
    )
    body = render(doc, "full").body
    assert "# Harbor Lane Survey {#doc}" in body
    assert body.count("Harbor Lane Survey") == 1 + body.count("Harbor Lane Survey]")
    assert "The survey covers the outer berths." in body


def test_a_first_paragraph_that_only_starts_with_the_title_stays() -> None:
    doc = make_result([para("Harbor Lane Survey of the outer berths, 2024.")], title="Harbor Lane Survey")
    assert "Harbor Lane Survey of the outer berths, 2024." in render(doc, "full").body


def test_compact_has_no_numbers_or_anchors() -> None:
    body = render(_headings_chaos(), "compact").body
    assert "## 1. Introduction" in body  # source numbering kept when numbering is off
    assert "{#" not in body
    assert "## Second top" in body


def test_contents_and_orientation_trigger() -> None:
    full = render(_headings_chaos(), "full").body
    assert full.startswith(
        "> Sections: 1 Introduction, 2 Second top.\n\n## Contents\n\n- [1 Introduction](#sec-1)\n"
        "    - [1.1 Background](#sec-1-1)\n"
    )
    assert full.index("## Contents") < full.index("# Doc Title")
    agent = render(_headings_chaos(), "agent").body
    assert "> Sections: 1 Introduction" in agent and "## Contents" not in agent
    rag = render(_headings_chaos(), "rag").body
    assert "> Sections" not in rag and "## Contents" not in rag


def test_summary_blockquote_from_abstract() -> None:
    res = make_result(
        [Paragraph(spans=[span("One. Two. Three. Four. Five.")], role="abstract", provenance=prov()), para("Body.")]
    )
    assert render(res, "full").body.startswith("> Summary: One. Two. Three. Four.\n\n# Test document")
    assert "> Summary" not in render(res, "rag").body and "One. Two." in render(res, "rag").body


def _footnote_doc():  # type: ignore[no-untyped-def]
    return make_result(
        [
            heading("A", 1),
            Paragraph(spans=[span("Alpha"), span("9", footnote="fz"), span(" text.")], provenance=prov()),
            heading("A child", 2),
            Paragraph(spans=[span("Child"), span("x", footnote="fa"), span(".")], provenance=prov()),
            heading("B", 1),
            Paragraph(
                spans=[span("Beta"), span("1", footnote="fb"), span(" and again"), span("9", footnote="fz")],
                provenance=prov(),
            ),
            Footnote(id="fz", marker="9", spans=[span("Zed note.")], provenance=prov()),
            Footnote(id="fa", marker="x", spans=[span("Ay note.")], provenance=prov()),
            Footnote(id="fb", marker="1", spans=[span("Bee note.")], provenance=prov()),
            Footnote(id="fu", marker="u", spans=[span("Unreferenced.")], provenance=prov()),
        ]
    )


def test_footnotes_renumbered_and_placed_at_section_end() -> None:
    out = render(_footnote_doc(), "full")
    body = out.body
    assert "Alpha[^1] text." in body and "Child[^2]." in body and "Beta[^3] and again[^1]" in body
    a_end = body.index("## 2 B")
    assert body.index("[^1]: Zed note.") < a_end and body.index("[^2]: Ay note.") < a_end
    assert body.index("[^2]: Ay note.") > body.index("Child[^2].")
    assert body.index("[^3]: Bee note.") > a_end
    assert body.rstrip().endswith("[^4]: Unreferenced.")
    assert body.count("[^1]:") == 1
    markers = {f["number"]: f["source_marker"] for f in out.sidecar["footnotes"]}  # type: ignore[index]
    assert markers == {1: "9", 2: "x", 3: "1", 4: "u"}


def test_footnotes_inline_in_rag_and_dropped_on_request() -> None:
    rag = render(_footnote_doc(), "rag").body
    assert "Alpha[^1] text.\n\n[^1]: Zed note." in rag
    dropped = render(_footnote_doc(), "full", footnotes="drop").body
    assert "[^" not in dropped


def _seg(
    start: float, end: float, text: str, speaker: str | None, kind: str = "speech", conf: float | None = None
) -> TranscriptSegment:
    return TranscriptSegment(
        start=start,
        end=end,
        text=text,
        speaker=speaker,
        kind=kind,  # type: ignore[arg-type]
        words=[(text.split()[0], start, start + 0.2)] if text else None,
        provenance=prov(time_start=start, confidence=conf),
    )


def test_transcript_paragraphs_labels_and_cues() -> None:
    res = make_result(
        [
            _seg(0.0, 2.0, "Hello there.", "Alice"),
            _seg(2.2, 4.0, "Still me.", "Alice"),
            _seg(9.0, 10.0, "After a gap.", "Alice"),
            _seg(10.5, 12.0, "Bob here.", "Bob"),
            _seg(12.0, 14.0, "", None, kind="music"),
            _seg(14.1, 15.0, "mumble", "SPEAKER_07", conf=0.2),
            _seg(3700.0, 3701.0, "Late.", "Bob"),
        ]
    )
    full = render(res, "full")
    lines = full.body.strip().split("\n\n")
    assert "**Alice** [00:00:00]: Hello there. Still me." in lines
    assert "**Alice** [00:00:09]: After a gap." in lines
    assert "**Bob** [00:00:10]: Bob here. *[music]*" in lines
    assert "**Speaker 3** [00:00:14]: [inaudible]" in lines
    assert "**Bob** [01:01:40]: Late." in lines
    assert "**Bob** [00:00:10]: Bob here. [music]" in render(res, "agent").body
    segs = full.sidecar["segments"]  # type: ignore[index]
    assert "words" in segs[0]
    agent_segs = render(res, "agent").sidecar["segments"]  # type: ignore[index]
    assert "words" not in agent_segs[0]
    agent_doc = render(res, "agent").sidecar["document"]["blocks"]  # type: ignore[index]
    assert all("words" not in b for b in agent_doc)


def test_single_unnamed_speaker_has_no_labels() -> None:
    res = make_result([_seg(4.0, 6.0, "Thanks everyone.", "SPEAKER_00"), _seg(6.1, 7.0, "Next.", "SPEAKER_00")])
    assert "[00:00:04] Thanks everyone. Next." in render(res, "full").body
    assert "Speaker" not in render(res, "full").body


def test_chapter_headings_carry_time_ranges() -> None:
    res = make_result([heading("Intro", 1, time_start=0.0, time_end=65.0), _seg(1.0, 2.0, "Hi.", "SPEAKER_00")])
    assert "## 1 Intro [00:00:00 - 00:01:05] {#sec-1}" in render(res, "full").body
    assert "## Intro [00:00:00]" in render(res, "compact").body


def test_slides_marker_heading_and_notes() -> None:
    from ezmd.ir import Slide

    res = make_result(
        [
            heading("Talk", 1),
            Slide(id="s4", index=4, title="Quarterly results", provenance=prov(time_start=330.0, time_end=492.0)),
            Paragraph(
                spans=[span("Speaker notes here")], attrs={"slide_part": "notes"}, parent_id="s4", provenance=prov()
            ),
        ]
    )
    full = render(res, "full").body
    assert "<!-- slide 4 -->\n### Slide 4: Quarterly results [00:05:30 - 00:08:12] {#slide-4}" in full
    assert "#### Notes\n\nSpeaker notes here" in full  # one level below the H3 slide
    assert "<!-- slide" not in render(res, "compact").body


def test_spreadsheet_sheet_markers() -> None:
    from ezmd.ir import Heading, SourceType

    res = make_result(
        [Heading(level=1, spans=[span("Budget")], provenance=prov(source_label="Budget")), para("cells")],
        source_type=SourceType.XLSX,
    )
    assert '<!-- sheet "Budget" -->\n## 1 Budget {#sec-1}' in render(res, "full").body
