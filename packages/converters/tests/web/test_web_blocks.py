from __future__ import annotations

from ezmd.ir import (
    CodeBlock,
    Equation,
    Figure,
    Footnote,
    Heading,
    Image,
    InlineStyle,
    Link,
    ListBlock,
    Paragraph,
    Quote,
    Table,
    spans_text,
)
from ezmd_converters.web.build import Builder
from ezmd_converters.web.dom import body_of, parse_html
from ezmd_converters.web.html_blocks import convert_children, register_footnotes
from ezmd_converters.web.hygiene import pre_clean

BASE = "https://site.test/a/b/page.html"


def _blocks(body: str, base: str | None = BASE) -> tuple[list[object], Builder]:
    root = parse_html(f"<html><body>{body}</body></html>")
    pre_clean(root)
    b = Builder(source="https://site.test/a/b/page.html", base=base, engine="web.rules")
    register_footnotes(body_of(root), b)
    convert_children(body_of(root), b)
    return list(b.blocks), b


def test_headings_paragraph_inline_styles_and_links() -> None:
    blocks, b = _blocks(
        '<h2>Title</h2><p>Some <b>bold</b>, <em>it</em>, <code>c()</code>, <a href="../x">rel</a>, '
        '<a href="javascript:void(0)">js</a> and <a href="mailto:a@b.test">mail</a>.</p>'
    )
    h, p = blocks
    assert isinstance(h, Heading) and h.level == 2 and spans_text(h.spans) == "Title"
    assert isinstance(p, Paragraph)
    assert spans_text(p.spans) == "Some bold, it, c(), rel, js and mail."
    styles = {s.text: s.styles for s in p.spans}
    assert styles["bold"] == [InlineStyle.BOLD] and styles["c()"] == [InlineStyle.CODE]
    hrefs = {s.text: s.href for s in p.spans}
    assert hrefs["rel"] == "https://site.test/a/x"
    assert hrefs["mail"] == "mailto:a@b.test"
    assert not any((s.href or "").startswith("javascript") for s in p.spans)
    assert p.provenance.path == "body > p" and h.provenance.path == "body > h2"
    assert b.link_hrefs == ["https://site.test/a/x", "mailto:a@b.test"]


def test_relative_links_stay_relative_without_base() -> None:
    blocks, _ = _blocks('<p><a href="/docs">docs</a></p>', base=None)
    p = blocks[0]
    assert isinstance(p, Paragraph) and p.spans[0].href == "/docs"


def test_nested_lists_keep_order_and_start() -> None:
    blocks, _ = _blocks(
        "<ol start='3'><li>three<ul><li>a</li><li>b<ol><li>deep</li></ol></li></ul></li><li>four</li></ol>"
    )
    (lst,) = blocks
    assert isinstance(lst, ListBlock) and lst.ordered and lst.start == 3
    first = lst.items[0]
    assert spans_text(first.spans) == "three" and not first.children_ordered
    assert [spans_text(c.spans) for c in first.children] == ["a", "b"]
    assert first.children[1].children_ordered and spans_text(first.children[1].children[0].spans) == "deep"


def test_code_language_sources_and_line_numbers() -> None:
    blocks, _ = _blocks(
        '<pre><code class="language-rust">fn main() {}</code></pre>'
        '<pre data-lang="Go">package main</pre>'
        '<div class="highlight-toml"><pre>a = 1</pre></div>'
        '<pre><code class="hljs yaml">k: v</code></pre>'
        '<pre><span class="lineno">1 </span>x = 1\n<span class="lineno">2 </span>y = 2</pre>'
    )
    codes = [b for b in blocks if isinstance(b, CodeBlock)]
    assert [c.language for c in codes] == ["rust", "go", "toml", "yaml", None]
    assert codes[-1].code == "x = 1\ny = 2"


def test_table_spans_header_rows_caption() -> None:
    blocks, _ = _blocks(
        "<table><caption>Fees</caption><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>"
        "<tbody><tr><td rowspan='2'>x</td><td colspan='2'>wide</td></tr><tr><td>1</td><td>2</td></tr></tbody></table>"
    )
    (t,) = blocks
    assert isinstance(t, Table)
    assert (t.n_rows, t.n_cols, t.header_rows) == (3, 3, 1)
    assert t.caption is not None and spans_text(t.caption) == "Fees"
    cells = {(c.row, c.col): c for c in t.cells}
    assert cells[(1, 0)].row_span == 2 and cells[(1, 1)].col_span == 2
    assert spans_text(cells[(2, 1)].spans) == "1" and t.has_merged_cells
    assert cells[(0, 0)].is_header and not cells[(1, 0)].is_header


def test_layout_table_unwrapped() -> None:
    blocks, _ = _blocks(
        "<table><tr><td><p>Left column text.</p></td><td><div><h3>Side</h3><p>Right.</p></div></td></tr></table>"
        "<table><tr><td>only one column</td></tr><tr><td>second row</td></tr></table>"
    )
    assert not any(isinstance(b, Table) for b in blocks)
    assert [spans_text(b.spans) for b in blocks if isinstance(b, Paragraph | Heading)] == [
        "Left column text.",
        "Side",
        "Right.",
        "only one column",
        "second row",
    ]


def test_figure_caption_picture_lazy_and_alt() -> None:
    blocks, b = _blocks(
        '<figure><img src="img/a.png"><figcaption>Cap <b>one</b></figcaption></figure>'
        '<p><img src="data:image/gif;base64,AA" data-src="lazy.jpg" alt="Lazy"></p>'
        '<picture><source srcset="s-1.webp 1x, s-2.webp 2x"><img src="s.jpg" alt="Pic"></picture>'
        '<p>text <img src="/inline.png"> more</p>'
    )
    fig = blocks[0]
    assert isinstance(fig, Figure)
    img, cap = blocks[1], blocks[2]
    assert isinstance(img, Image) and img.parent_id == fig.id and img.ref == "https://site.test/a/b/img/a.png"
    assert img.alt is None
    assert isinstance(cap, Paragraph) and cap.role == "caption" and cap.parent_id == fig.id
    refs = [x.ref for x in blocks if isinstance(x, Image)]
    assert "https://site.test/a/b/lazy.jpg" in refs and "https://site.test/a/b/s-2.webp" in refs
    inline = next(x for x in blocks if isinstance(x, Image) and x.ref.endswith("inline.png"))
    assert inline.alt == "image"
    assert b.images_without_alt == 1 and b.lazy_images == 1


def test_definition_list_details_quote() -> None:
    blocks, _ = _blocks(
        "<h2>Terms</h2><dl><dt>Berth</dt><dd>A place.</dd><dd>Numbered.</dd><dt>Slack</dt><dd>No stream.</dd></dl>"
        "<details><summary>More</summary><p>Hidden by default but visible on click.</p></details>"
        "<blockquote><p>First.</p><p>Second.</p><footer>Someone</footer></blockquote>"
    )
    dl = blocks[1]
    assert isinstance(dl, ListBlock) and dl.attrs["kind"] == "definition"
    assert [spans_text(i.spans) for i in dl.items] == ["Berth", "Slack"]
    assert [spans_text(c.spans) for c in dl.items[0].children] == ["A place.", "Numbered."]
    summary = blocks[2]
    assert isinstance(summary, Heading) and summary.level == 3 and spans_text(summary.spans) == "More"
    q = blocks[4]
    assert isinstance(q, Quote) and spans_text(q.spans) == "First.\n\nSecond." and q.attribution == "Someone"


def test_math_and_footnotes() -> None:
    blocks, _ = _blocks(
        '<p>Inline <span class="katex"><span class="katex-mathml"><math><semantics><mi>x</mi>'
        '<annotation encoding="application/x-tex">x^2</annotation></semantics></math></span>'
        '<span class="katex-html" aria-hidden="true">x2</span></span> and a note<sup>'
        '<a href="#fn-a" role="doc-noteref">1</a></sup>.</p>'
        '<div class="math" data-latex="E=mc^2">E=mc2</div>'
        '<section class="footnotes" role="doc-endnotes"><ol><li id="fn-a">The note. '
        '<a href="#r" role="doc-backlink">back</a></li></ol></section>'
    )
    p = blocks[0]
    assert isinstance(p, Paragraph)
    math = [s for s in p.spans if s.math]
    assert math and math[0].math == "x^2"
    ref = next(s for s in p.spans if s.footnote_ref)
    eq = blocks[1]
    assert isinstance(eq, Equation) and eq.latex == "E=mc^2"
    fn = blocks[2]
    assert isinstance(fn, Footnote) and fn.id == ref.footnote_ref and spans_text(fn.spans) == "The note."


def test_video_iframe_becomes_link() -> None:
    blocks, _ = _blocks('<p>Watch:</p><iframe src="https://player.vimeo.com/video/1" title="Demo"></iframe>')
    link = blocks[1]
    assert isinstance(link, Link) and link.href == "https://player.vimeo.com/video/1" and link.text == "Demo"


def test_deep_nesting_does_not_crash() -> None:
    body = "<div>" * 240 + "<p>deep text</p>" + "</div>" * 240 + "<ul>" + "<li>x<ul>" * 60 + "</ul></li>" * 60 + "</ul>"
    blocks, _ = _blocks(body)
    assert any(isinstance(b, Paragraph) and "deep text" in spans_text(b.spans) for b in blocks)


def test_single_row_table_is_layout() -> None:
    """5e item 11: a one-row table without header cells is page layout (logo next to a tagline)."""
    blocks, _ = _blocks('<table><tr><td><img src="/logo.gif" alt="Logo"></td><td>Est. 1898</td></tr></table>')
    assert not any(isinstance(b, Table) for b in blocks)
    assert any(isinstance(b, Image) for b in blocks)
    assert [spans_text(b.spans) for b in blocks if isinstance(b, Paragraph)] == ["Est. 1898"]


def test_mathjax_v2_preview_is_dropped() -> None:
    blocks, _ = _blocks(
        '<p>Time <span class="MathJax_Preview">t</span><script type="math/tex">t</script> is</p>'
        '<span class="MathJax_Preview">E=mc2</span><script type="math/tex; mode=display">E=mc^2</script>'
    )
    p = blocks[0]
    assert isinstance(p, Paragraph) and spans_text(p.spans) == "Time t is"
    assert [s.math for s in p.spans if s.math] == ["t"]
    eqs = [b for b in blocks if isinstance(b, Equation)]
    assert [e.latex for e in eqs] == ["E=mc^2"]
    assert not any(isinstance(b, Paragraph) and "mc2" in spans_text(b.spans) for b in blocks)


def test_one_row_data_table_is_kept() -> None:
    """A one-row table of plain values (no header cells, no images or block content) is data, not layout."""
    blocks, _ = _blocks("<table><tr><td>Total</td><td>12</td><td>3:02.4</td></tr></table>")
    tables = [b for b in blocks if isinstance(b, Table)]
    assert len(tables) == 1 and tables[0].n_rows == 1 and tables[0].n_cols == 3


def test_sparse_data_table_is_kept() -> None:
    blocks, _ = _blocks(
        "<table><tr><td>Mon</td><td></td><td></td></tr><tr><td></td><td>Tue</td><td></td></tr>"
        "<tr><td></td><td></td><td>Wed</td></tr></table>"
    )
    assert any(isinstance(b, Table) for b in blocks)
