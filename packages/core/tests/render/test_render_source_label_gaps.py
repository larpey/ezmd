"""D-0083 gaps: documents that print their own section labels still get them replaced by derived numbers."""

from __future__ import annotations

from render_builders import heading, make_result, para

from ezmd.ir import Document, Metadata, SourceType
from ezmd.render import render


def test_a_bare_appendix_letter_counts_as_a_label() -> None:
    """part3 section 14 lists `Appendix B` as a label; the pattern demands punctuation after the letter."""
    doc = make_result(
        [
            heading("Doc", 1),
            heading("31. Our liability", 1),
            heading("31.1 Transfers", 2),
            heading("Appendix B Rates", 1),
        ],
        title=None,
    )
    body = render(doc, "full").body
    assert "## 31. Our liability {#sec-1}" in body, body
    assert "## Appendix B Rates {#sec-2}" in body, body


def test_a_heading_that_is_only_its_label_counts() -> None:
    """part3 section 14 lists `Section 4` as a label; the pattern demands more text after it."""
    doc = make_result(
        [
            heading("Doc", 1),
            heading("Section 4", 1),
            para("a"),
            heading("Section 5", 1),
            para("b"),
            heading("Section 6", 1),
        ],
        title=None,
    )
    body = render(doc, "full").body
    assert "## Section 4 {#sec-1}" in body, body


def test_embedded_documents_do_not_dilute_the_parents_own_numbering() -> None:
    """The parent numbers 3 of 3 headings; an attachment with 4 plain headings must not renumber the parent."""
    child = Document(
        metadata=Metadata(title="Notes", source="bundle.zip!notes.md", source_type=SourceType.MARKUP),
        blocks=[heading(t, 2) for t in ("Alpha", "Beta", "Gamma", "Delta")],
        converter_id="text.markdown",
    ).finalize()
    res = make_result(
        [heading("Doc", 1), heading("31. Liability", 1), heading("32. Notices", 1), heading("33. Law", 1)],
        title=None,
    )
    res = res.model_copy(update={"document": res.document.model_copy(update={"children": [child]})})
    body = render(res, "full").body
    assert "## 31. Liability {#sec-1}" in body, body
