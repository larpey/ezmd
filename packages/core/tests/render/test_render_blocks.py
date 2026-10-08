"""Every IR block type renders (no `intomd-unrendered`), deterministically, in every profile and format."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from render_builders import heading, make_result, para, prov, span

from intomd.ir import (
    CodeBlock,
    Comment,
    ConversionResult,
    Equation,
    Figure,
    Footnote,
    Image,
    InlineSpan,
    InlineStyle,
    InputRefInfo,
    Link,
    ListBlock,
    ListItem,
    PageBreak,
    Paragraph,
    Quote,
    Raw,
    SourceType,
    TrackedChange,
)
from intomd.render import render

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core_factories import every_block_document

PROFILES = ["full", "compact", "rag", "agent"]


def _every_block() -> ConversionResult:
    return ConversionResult(
        document=every_block_document(), converter_id="x", input_ref=InputRefInfo(kind="path", display="synthetic.txt")
    )


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("fmt", ["md", "json", "txt"])
def test_every_block_renders_without_fallback(profile: str, fmt: str) -> None:
    out = render(_every_block(), profile, format=fmt)
    assert "intomd-unrendered" not in out.markdown
    assert out.markdown.endswith("\n") and not out.markdown.endswith("\n\n")
    assert all(line == line.rstrip() for line in out.markdown.split("\n"))
    assert "\r" not in out.markdown


@pytest.mark.parametrize("profile", PROFILES)
def test_every_block_deterministic(profile: str) -> None:
    a = render(_every_block(), profile)
    b = render(_every_block(), profile)
    assert a.body == b.body
    assert [c.text for c in a.chunks] == [c.text for c in b.chunks]


def test_input_document_not_mutated() -> None:
    res = _every_block()
    before = res.model_dump()
    render(res, "full")
    assert res.model_dump() == before


def test_inline_styles_and_escaping() -> None:
    res = make_result(
        [
            Paragraph(
                spans=[
                    span("bold", InlineStyle.BOLD),
                    span(" and "),
                    span("it", InlineStyle.ITALIC),
                    span(" "),
                    span("x`y", InlineStyle.CODE),
                    span(" "),
                    span("gone", InlineStyle.STRIKE),
                ],
                provenance=prov(),
            ),
            para("# not a heading"),
            para("1. not a list"),
            para("- not a bullet"),
            para("snake_case stays, but *stars* get escaped"),
            para("Prices: $5 and $10 today"),
            para("Zero\u200bwidth\u00adchars removed"),
        ]
    )
    body = render(res, "full").body
    assert "**bold** and *it* ``x`y`` ~~gone~~" in body
    assert "\\# not a heading" in body
    assert "1\\. not a list" in body
    assert "\\- not a bullet" in body
    assert "snake_case stays, but \\*stars\\* get escaped" in body
    assert "\\$5 and \\$10" in body
    assert "Zerowidthchars removed" in body


def test_lists_nesting_tasks_and_compact_rules() -> None:
    items = [
        ListItem(spans=[span("first")], children=[ListItem(spans=[span("child")])]),
        ListItem(spans=[span("second")], checked=True),
        ListItem(spans=[span("third")], checked=False),
    ]
    res = make_result(
        [
            ListBlock(ordered=True, start=3, items=items, provenance=prov()),
            ListBlock(items=[ListItem(spans=[span("lonely")])], provenance=prov()),
        ]
    )
    full = render(res, "full").body
    assert "3. first\n    - child\n4. [x] second\n5. [ ] third" in full
    assert "- lonely" in full
    compact = render(res, "compact").body
    assert "1. first\n    - child\n1. [x] second\n1. [ ] third" in compact
    assert "\nlonely\n" in compact


def test_code_fence_longer_than_content_backticks() -> None:
    res = make_result([CodeBlock(code="x = '''\n````\n'''  \n", language="python", provenance=prov())])
    body = render(res, "full").body
    assert "`````python\nx = '''\n````\n'''\n`````" in body


def test_quote_depth_attribution_and_callout() -> None:
    res = make_result(
        [
            Quote(spans=[span("deep")], depth=2, attribution="Someone", provenance=prov()),
            Paragraph(spans=[span("careful")], attrs={"callout": "warning"}, provenance=prov()),
        ]
    )
    body = render(res, "full").body
    assert "> > deep\n> >\n> > Source: Someone" in body
    assert "> **Warning:** careful" in body


def test_raw_fenced_or_dropped_and_equation_forms() -> None:
    res = make_result(
        [
            Raw(format="latex", content="\\foo", provenance=prov()),
            Equation(latex="a^2+b^2", provenance=prov()),
            Equation(text="x squared", provenance=prov()),
        ]
    )
    full = render(res, "full").body
    assert "```latex\n\\foo\n```" in full
    assert "$$\na^2+b^2\n$$" in full
    assert "`x squared`\n<!-- intomd: equation not converted -->" in full
    dropped = render(res, "full", raw_blocks="drop").body
    assert "\\foo" not in dropped


def test_tracked_changes_and_comments_per_mode() -> None:
    target = Paragraph(id="p1", spans=[span("Base text.")], provenance=prov())
    res = make_result(
        [
            target,
            TrackedChange(change="insert", spans=[span("added")], anchor_block_id="p1", provenance=prov()),
            TrackedChange(change="delete", spans=[span("removed")], provenance=prov()),
            Comment(spans=[span("check this")], author="Ann", anchor_block_id="p1", provenance=prov()),
        ]
    )
    accepted = render(res, "full")
    assert "removed" not in accepted.body and "{++" not in accepted.body
    assert {"tracked_changes_present", "comments_present"} <= set(accepted.frontmatter["warnings"])  # type: ignore[arg-type]
    annotated = render(res, "full", tracked_changes="annotate", comments="inline").body
    assert "Base text. {++added++} {>>Ann: check this<<}" in annotated
    assert "{--removed--}" in annotated


def test_links_inline_numbered_text_only_and_tracking() -> None:
    res = make_result(
        [
            Paragraph(
                spans=[
                    span("See "),
                    span("the log", href="https://example.org/log?utm_source=x&id=3"),
                    span(" and "),
                    span("https://e.org", href="https://e.org"),
                    span(" and "),
                    span("mail", href="mailto:a@b.c"),
                    span(" and "),
                    span("again", href="https://example.org/log?id=3"),
                ],
                provenance=prov(),
            ),
            Link(href="/rel/page", text="Relative", provenance=prov()),
        ],
        source="https://site.test/a/b",
        source_type=SourceType.WEB,
    )
    full = render(res, "full").body
    assert "[the log](https://example.org/log?id=3)" in full
    assert "https://e.org and mail and" in full
    assert "- [Relative](https://site.test/rel/page)" in full
    compact = render(res, "compact").body
    assert "See the log and https://e.org and mail and again" in compact
    assert compact.endswith("## Links\n\n1. https://example.org/log?id=3\n2. https://site.test/rel/page\n")
    rag = render(res, "rag").body
    assert "See the log and" in rag and "- Relative: https://site.test/rel/page" in rag


def test_anchor_links_rewritten_to_derived_anchor() -> None:
    res = make_result([heading("Results", 1), Paragraph(spans=[span("jump", href="#results")], provenance=prov())])
    assert "[jump](#sec-1)" in render(res, "full").body
    assert render(res, "compact").body.endswith("## Results\n\njump\n")


def test_images_decorative_caption_forms_and_comment() -> None:
    from intomd.ir import BBox

    blocks = [Image(ref="logo.png", alt="Logo", provenance=prov(source_page=p)) for p in (1, 2, 3)] + [
        Image(ref="icon.png", alt="i", width=16, height=16, provenance=prov(source_page=1)),
        Image(ref="spacer.png", alt="", provenance=prov(source_page=1)),
        Image(
            ref="chart.png",
            alt="Chart",
            generated_caption="A bar chart",
            provenance=prov(source_page=2, bbox=BBox(x0=10, y0=20, x1=50, y1=80, page_width=100, page_height=100)),
        ),
        Image(ref="photo.png", alt="Photo", provenance=prov(source_page=3)),
    ]
    res = make_result(blocks, pages=3)
    out = render(res, "full")
    assert "logo.png" not in out.body and "icon.png" not in out.body and "spacer.png" not in out.body
    assert out.sidecar is not None and out.sidecar["counts"]["images_dropped_decorative"] == 5  # type: ignore[index]
    assert (
        "![Chart](chart.png)\nFigure 1 (page 2): A bar chart\n<!-- image: chart.png page=2 bbox=0.10,0.20,0.50,0.80 -->"
    ) in out.body
    assert "![Photo](photo.png)\n<!-- image: photo.png page=3 -->" in out.body
    compact = render(res, "compact").body
    assert "Figure 1 (page 2): A bar chart" in compact and "Figure 2: Photo" in compact and "![" not in compact
    agent = render(res, "agent").body
    assert "![Photo](photo.png)\nFigure 2\n<!-- image: photo.png page=3 -->" in agent


def test_figure_group_is_atomic_with_caption_and_page_marker_outside() -> None:
    res = make_result(
        [
            para("before"),
            PageBreak(page_number=2, provenance=prov()),
            Figure(id="f1", provenance=prov(source_page=2)),
            Image(ref="a.png", alt="A", parent_id="f1", provenance=prov(source_page=2)),
            Paragraph(spans=[span("The caption.")], role="caption", parent_id="f1", provenance=prov(source_page=2)),
        ]
    )
    body = render(res, "full").body
    assert "<!-- page 2 -->\n\n![A](a.png)\nFigure 1: The caption.\n<!-- image: a.png page=2 -->" in body
    assert body.count("The caption.") == 1


def test_furniture_dropped_and_counted() -> None:
    res = make_result(
        [
            Paragraph(spans=[span("ACME Report")], role="header", provenance=prov(source_page=1)),
            para("Body one"),
            Paragraph(spans=[span("ACME Report")], role="header", provenance=prov(source_page=2)),
            Paragraph(spans=[span("Page 2")], role="page_number", provenance=prov(source_page=2)),
            Paragraph(spans=[span("Only once")], role="footer", provenance=prov(source_page=2)),
        ],
        pages=2,
    )
    out = render(res, "full")
    assert "ACME Report" not in out.body and "Page 2" not in out.body
    assert "Only once" in out.body
    assert out.sidecar is not None and out.sidecar["counts"]["furniture_removed"] == 3  # type: ignore[index]
    assert "ACME Report" in render(res, "full", furniture="keep").body


def test_page_markers_per_profile() -> None:
    res = make_result(
        [
            Paragraph(spans=[span("one")], provenance=prov(source_page=1)),
            Paragraph(spans=[span("four")], provenance=prov(source_page=4, page_label="iv")),
        ]
    )
    full = render(res, "full").body
    assert '<!-- page 1 -->\n\none\n\n<!-- page 4 label="iv" -->\n\nfour' in full
    assert "<!-- page" not in render(res, "compact").body


def test_json_and_txt_formats() -> None:
    res = make_result(
        [
            heading("Section", 1),
            para("Hello **world**"),
            Footnote(id="fn", marker="*", spans=[span("Note.")], provenance=prov()),
        ]
    )
    payload = json.loads(render(res, "rag", format="json").markdown)
    assert set(payload) == {"markdown", "frontmatter", "sidecar", "chunks"}
    assert payload["chunks"] and payload["chunks"][0]["id"].endswith("#c0001")
    txt = render(res, "full", format="txt").markdown
    assert txt.startswith("Test document\n\n1 Section\n\nHello **world**")
    assert "---" not in txt and "<!--" not in txt
    assert render(res, "full", format="markdown").markdown == render(res, "full").markdown
    with pytest.raises(ValueError, match="unknown format"):
        render(res, "full", format="docx")


def test_unknown_object_uses_unrendered_fence_only_for_non_blocks() -> None:
    from intomd.render.context import RenderContext
    from intomd.render.units import _block_units

    res = make_result([para("x")])
    from intomd.profiles import FULL

    ctx = RenderContext(profile=FULL, result=res)
    units = _block_units(ctx, InlineSpan(text="not a block"), False)  # type: ignore[arg-type]
    assert units[0].text.startswith("```intomd-unrendered")
