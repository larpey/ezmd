"""Synthetic IR builders for renderer tests (Harbor Lane worked example and per-block fixtures)."""

from __future__ import annotations

from datetime import UTC, datetime

from ezmd.ir import (
    BBox,
    Block,
    ConversionResult,
    Document,
    Heading,
    Image,
    InlineSpan,
    InlineStyle,
    InputRefInfo,
    Metadata,
    Metrics,
    Paragraph,
    Provenance,
    SourceType,
    Table,
    TableCell,
    TranscriptSegment,
)

HARBOR_SRC = "https://example.org/depot-report"
CONVERTED_AT = datetime(2026, 10, 8, 15, 2, 13, tzinfo=UTC)


def prov(source: str = "synthetic.txt", **kw: object) -> Provenance:
    return Provenance(source=source, **kw)  # type: ignore[arg-type]


def span(text: str, *styles: InlineStyle, href: str | None = None, footnote: str | None = None) -> InlineSpan:
    return InlineSpan(text=text, styles=list(styles), href=href, footnote_ref=footnote)


def para(text: str, **kw: object) -> Paragraph:
    return Paragraph(spans=[span(text)], provenance=prov(), **kw)  # type: ignore[arg-type]


def heading(text: str, level: int, **kw: object) -> Heading:
    return Heading(level=level, spans=[span(text)], provenance=prov(**kw))


def table(rows: list[list[str]], header_rows: int = 1, caption: str | None = None, **kw: object) -> Table:
    cells = [
        TableCell(spans=[span(v)] if v else [], row=r, col=c, is_header=r < header_rows)
        for r, row in enumerate(rows)
        for c, v in enumerate(row)
    ]
    return Table(
        cells=cells,
        n_rows=len(rows),
        n_cols=len(rows[0]) if rows else 0,
        header_rows=header_rows,
        caption=[span(caption)] if caption else None,
        provenance=prov(),
        **kw,  # type: ignore[arg-type]
    )


def make_result(
    blocks: list[Block],
    *,
    title: str | None = "Test document",
    source: str = "synthetic.txt",
    source_type: SourceType = SourceType.TEXT,
    converter_id: str = "text.plain",
    **meta: object,
) -> ConversionResult:
    doc = Document(
        metadata=Metadata(
            title=title,
            source=source,
            source_type=source_type,
            fetched=datetime(2026, 10, 8, 15, 2, 11, tzinfo=UTC),
            **meta,
        ),  # type: ignore[arg-type]
        blocks=blocks,
    ).finalize()
    return ConversionResult(
        document=doc,
        converter_id=converter_id,
        metrics=Metrics(engine=f"{converter_id}@1.0.0"),
        input_ref=InputRefInfo(kind="path", display=source),
    )


def _seg(start: float, end: float, text: str, speaker: str | None, kind: str = "speech") -> TranscriptSegment:
    return TranscriptSegment(
        start=start,
        end=end,
        text=text,
        speaker=speaker,
        kind=kind,  # type: ignore[arg-type]
        provenance=Provenance(source=HARBOR_SRC, time_start=start, time_end=end),
    )


def harbor_lane() -> ConversionResult:
    p = Provenance(source=HARBOR_SRC)
    weeks = [
        ["Week", "Pallets", "Dock doors", "Overtime hours"],
        ["36", "980", "4", "12"],
        ["37", "1,105", "2", "41"],
        ["38", "1,060", "2", "38"],
        ["39", "1,065", "4", "9"],
    ]
    tbl = table(weeks, caption="Pallets handled per week, September 2026")
    tbl = tbl.model_copy(update={"provenance": p})
    blocks: list[Block] = [
        Paragraph(
            spans=[
                span(
                    "The Harbor Lane depot handled 4,210 pallets in September, up 6% on August. Two of the "
                    "four dock doors were out of service for a week, which the team covered with extended "
                    "evening shifts."
                )
            ],
            provenance=p,
        ),
        Heading(level=2, spans=[span("Throughput by week")], provenance=p),
        tbl,
        Image(
            ref="images/fig-01.jpg",
            alt="Dock door 3 during repair",
            caption=[span("Dock door 3 during the hydraulic repair in week 37.")],
            provenance=Provenance(source=HARBOR_SRC, bbox=BBox(x0=0.1, y0=0.55, x1=0.9, y1=0.95)),
        ),
        Heading(level=2, spans=[span("Interview with the shift lead")], provenance=p),
        _seg(
            3.2,
            9.6,
            "Sam, walk me through week 37. Two doors down and you still moved eleven hundred pallets.",
            "Dana Reyes",
        ),
        _seg(
            11.0,
            18.4,
            "We split the evening crew into two waves and ran the remaining doors continuously.",
            "Sam Okafor",
        ),
        _seg(
            18.6,
            27.9,
            "It cost us forty-one overtime hours, which is a lot, but the alternative was turning trucks away.",
            "Sam Okafor",
        ),
        _seg(29.1, 30.6, "And the repair itself?", "Dana Reyes"),
        _seg(
            31.0,
            37.8,
            "Hydraulics on door 3, a cracked cylinder. Door 4 was just preventive while the technician was on site.",
            "Sam Okafor",
        ),
        _seg(37.8, 39.9, "", None, kind="silence"),
        _seg(40.1, 45.3, "Both were back by the Monday of week 39.", "Sam Okafor"),
    ]
    doc = Document(
        metadata=Metadata(
            title="Harbor Lane depot report",
            source=HARBOR_SRC,
            source_type=SourceType.WEB,
            published=datetime(2026, 9, 12, tzinfo=UTC),
            fetched=datetime(2026, 10, 8, 15, 2, 11, tzinfo=UTC),
            author="Dana Reyes",
            language="en",
            speakers=["Dana Reyes", "Sam Okafor"],
            extra={
                "transcript_source": "asr",
                "asr_engine": "faster-whisper/large-v3-turbo",
                "diarization": "pyannote/speaker-diarization-community-1",
            },
        ),
        blocks=blocks,
    ).finalize()
    return ConversionResult(
        document=doc,
        converter_id="trafilatura",
        metrics=Metrics(engine="trafilatura@2.0.0"),
        input_ref=InputRefInfo(kind="url", display=HARBOR_SRC),
    )
