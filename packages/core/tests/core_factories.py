from __future__ import annotations

from datetime import UTC, datetime

from ezmd.ir import (
    BBox,
    CodeBlock,
    Comment,
    Document,
    Equation,
    Figure,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    InlineStyle,
    Link,
    ListBlock,
    ListItem,
    Metadata,
    PageBreak,
    Paragraph,
    Provenance,
    Quote,
    Raw,
    Slide,
    SourceType,
    Table,
    TableCell,
    TrackedChange,
    TranscriptSegment,
)

SRC = "synthetic.txt"


def P(**kw: object) -> Provenance:
    return Provenance(source=SRC, **kw)  # type: ignore[arg-type]


def S(text: str, *styles: InlineStyle, href: str | None = None) -> InlineSpan:
    return InlineSpan(text=text, styles=list(styles), href=href)


def every_block_document() -> Document:
    """A Document containing one or more of every block type, with nesting via parent_id."""
    blocks = [
        Heading(level=1, spans=[S("Title")], provenance=P(source_page=1)),
        Paragraph(spans=[S("Intro "), S("bold", InlineStyle.BOLD), S(" link", href="https://e.org")], provenance=P()),
        Paragraph(spans=[S("Page 1")], role="page_number", provenance=P()),
        Table(
            cells=[
                TableCell(spans=[S("a")], row=0, col=0, is_header=True),
                TableCell(spans=[S("b")], row=0, col=1, is_header=True),
                TableCell(spans=[S("1")], row=1, col=0, col_span=2, formula="=SUM(A1)"),
            ],
            n_rows=2,
            n_cols=2,
            header_rows=1,
            provenance=P(bbox=BBox(x0=0, y0=0, x1=10, y1=10)),
        ),
        ListBlock(
            items=[ListItem(spans=[S("one")], children=[ListItem(spans=[S("one.a")])]), ListItem(spans=[S("two")])],
            provenance=P(),
        ),
        CodeBlock(code="print('hi')", language="python", provenance=P(line_start=1, line_end=1)),
        Figure(id="fig1", label="Figure 1", provenance=P()),
        Image(ref="images/a.png", alt="alt text", parent_id="fig1", provenance=P()),
        Footnote(marker="1", spans=[S("note")], provenance=P()),
        Equation(latex="E=mc^2", provenance=P()),
        PageBreak(page_number=2, provenance=P()),
        TranscriptSegment(start=0.0, end=1.5, text="hello there", speaker="SPEAKER_00", provenance=P(time_start=0.0)),
        Slide(id="s1", index=1, title="Slide one", provenance=P()),
        Comment(spans=[S("a comment")], author="r", created=datetime(2026, 1, 1, tzinfo=UTC), provenance=P()),
        TrackedChange(change="insert", spans=[S("inserted")], provenance=P()),
        Link(href="https://example.org", text="Example", provenance=P()),
        Quote(spans=[S("quoted")], depth=2, provenance=P()),
        Raw(format="html", content="<b>raw</b>", provenance=P()),
    ]
    return Document(metadata=Metadata(source=SRC, source_type=SourceType.TEXT), blocks=blocks)
