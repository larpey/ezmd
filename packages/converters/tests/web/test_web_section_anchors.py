"""Sections whose id is the slug of their own heading (docs/converters/web.md, "Section anchors").

A page that anchors its outline generates ids from its headings, so a word that means "widget" in a class name
turns up in an id on a section of ordinary prose. These pages are synthetic; the prose is the harbors and
lighthouses of ezmd's other web tests.
"""

from __future__ import annotations

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import Document, WarningKind
from ezmd.registry import ConvertOptions
from ezmd_converters.web.boilerplate import section_anchors, strip_boilerplate
from ezmd_converters.web.coverage import dropped_text
from ezmd_converters.web.dom import body_of, parse_html, text_of
from ezmd_converters.web.engines import FullBodyConverter, RulesConverter, TrafilaturaConverter

PROSE = "The keeper trims the wick at dusk and writes the hour of lighting in the station book. " * 6
TENDER = "The tender calls at the light each spring with oil, coal and the post from the mainland. " * 6
FOG = "In thick weather the bell strikes twice a minute until a ship answers or the fog lifts. " * 6


def _section(slug: str, heading: str, marker: str) -> str:
    return f'<section id="{slug}"><h2>{heading}</h2><p>{marker} {PROSE}</p><p>{PROSE}</p></section>'


OUTLINE = "".join(
    [
        _section("reading-the-tide-tables", "1. Reading the Tide Tables", "Ebbmark"),
        _section("how-keepers-share-the-harbor-log", "2. How Keepers Share the Harbor Log", "Sharemark"),
        _section("social-hours-at-the-light", "3. Social Hours at the Light", "Socialmark"),
        _section("cookies-and-ship-biscuit", "4. Cookies and Ship Biscuit", "Biscuitmark"),
        _section("authorized-related-duties", "5. Authorized Related Duties", "Dutymark"),
        _section("keeping-the-lamp", "6. Keeping the Lamp", "Lampmark"),
        _section("the-winter-stores", "7. The Winter Stores", "Storemark"),
        _section("relief-of-the-watch", "8. Relief of the Watch", "Watchmark"),
        _section("repairs-to-the-tower", "9. Repairs to the Tower", "Towermark"),
    ]
)
PAGE = f"""<html lang="en"><head><title>The Keeper's Manual</title></head><body>
<nav><a href="#reading-the-tide-tables">Reading</a></nav>
<main><article><h1>The Keeper's Manual</h1>{OUTLINE}</article></main>
<footer><p>Printed at the harbor office.</p></footer></body></html>"""


def _convert(html: str, conv: object) -> Document:
    ref = InputRef.from_bytes(html.encode("utf-8"), filename="page.html")
    detect(ref)
    return conv.convert(ref, ConvertOptions())  # type: ignore[attr-defined]


def _kinds(doc: Document) -> list[str]:
    return [str(w.kind) for w in doc.warnings]


@pytest.mark.parametrize("conv", [TrafilaturaConverter(), RulesConverter(), FullBodyConverter()])
@pytest.mark.parametrize("marker", ["Ebbmark", "Sharemark", "Socialmark", "Biscuitmark", "Dutymark", "Lampmark"])
def test_heading_slug_ids_do_not_read_as_widgets(conv: object, marker: str) -> None:
    assert marker in _convert(PAGE, conv).plain_text()


def test_flat_headings_keep_their_slug_ids() -> None:
    flat = "".join(
        f'<h2 id="{slug}">{heading}</h2><p>{PROSE}</p>'
        for slug, heading in [
            ("share-of-the-catch", "Share of the Catch"),
            ("social-hours", "Social Hours"),
            ("tide-tables", "Tide Tables"),
            ("the-winter-stores", "The Winter Stores"),
            ("relief-of-the-watch", "Relief of the Watch"),
            ("repairs-to-the-tower", "Repairs to the Tower"),
        ]
    )
    html = f"<html><body><main><h1>Manual</h1>{flat}</main></body></html>"
    assert "Share of the Catch" in _convert(html, RulesConverter()).plain_text()


def _anchored(*sections: str) -> set[str]:
    html = f"<html><body><main>{''.join(sections)}</main></body></html>"
    return {str(el.get("id")) for el in section_anchors(body_of(parse_html(html)))}


def test_a_lone_chrome_section_is_not_an_anchor() -> None:
    assert _anchored(_section("comments", "Comments", "Thread")) == set()


def test_two_sections_are_not_an_outline() -> None:
    assert _anchored(_section("alpha-notes", "Alpha notes", "A"), _section("beta-notes", "Beta notes", "B")) == set()


def test_stacked_widgets_are_not_an_outline() -> None:
    chrome = [("share-this", "Share this"), ("related-posts", "Related posts"), ("comments", "Comments")]
    assert _anchored(*(_section(slug, heading, "Prose") for slug, heading in chrome)) == set()
    plain = [("alpha-notes", "Alpha notes"), ("beta-notes", "Beta notes")]
    assert _anchored(*(_section(slug, heading, "Prose") for slug, heading in chrome + plain)) == set()


def test_an_id_that_does_not_name_the_heading_is_not_an_anchor() -> None:
    sections = [_section(f"share-{n}", f"Part {n + 1}", "Prose") for n in range(4)]
    assert _anchored(*sections) == set()


def test_a_list_of_links_is_not_an_anchor() -> None:
    links = "".join(f'<a href="/p/{n}">Another story about the harbor at night</a> ' for n in range(9))
    sections = [f'<section id="{s}"><h2>{s}</h2><p>{links}</p></section>' for s in ("related", "share", "more")]
    assert _anchored(*sections) == set()


def test_ordinary_widgets_are_still_removed() -> None:
    html = f"""<html><body><main><h1>Manual</h1><p>{PROSE}</p>
    <div id="share-this-article"><h3>Share this article</h3><p>Send it to a friend today.</p></div>
    <div id="related-posts" class="related"><h3>Related posts</h3><p>More from the harbor desk.</p></div>
    <section id="comments"><h2>Comments</h2><p>First!</p></section>
    </main></body></html>"""
    body = body_of(parse_html(html))
    strip_boilerplate(body)
    kept = text_of(body)
    assert "Send it to a friend" not in kept and "More from the harbor desk" not in kept and "First!" not in kept


def test_a_widget_class_still_counts_on_an_anchored_section() -> None:
    sections = [_section(s, s.replace("-", " "), "Prose") for s in ("alpha-notes", "beta-notes", "delta-notes")]
    widget = '<section id="gamma-notes" class="related-posts"><h2>Gamma notes</h2><p>Teaser</p></section>'
    html = f"<html><body><main>{''.join(sections)}{widget}</main></body></html>"
    body = body_of(parse_html(html))
    strip_boilerplate(body)
    assert "Teaser" not in text_of(body)


def test_dropped_section_is_named_with_its_size() -> None:
    html = f"""<html><body><main><h2>Lamp</h2><p>{PROSE}</p><h2>2. How Keepers Share</h2><p>{TENDER}</p>
    <h2>Bell</h2><p>{FOG}</p></main></body></html>"""
    body = body_of(parse_html(html))
    w = dropped_text(body, PROSE + FOG)
    assert w is not None and w.kind == WarningKind.EXTRACTION_DROPPED_TEXT
    assert w.detail["sections"] == "2. How Keepers Share"
    assert isinstance(w.detail["dropped_chars"], int) and w.detail["dropped_chars"] > 500
    assert str(w.detail["dropped_chars"]) in w.message


def test_full_coverage_is_quiet() -> None:
    body = body_of(parse_html(PAGE))
    assert dropped_text(body, text_of(body)) is None


def test_material_unheaded_loss_warns_with_the_amount() -> None:
    body = body_of(parse_html(f"<html><body><main><p>{PROSE}</p><p>{FOG}</p><p>{TENDER}</p></main></body></html>"))
    w = dropped_text(body, PROSE + FOG)
    assert w is not None and w.detail["sections"] == ""
    assert isinstance(w.detail["dropped_chars"], int) and w.detail["dropped_chars"] > 0


def test_boilerplate_is_not_counted_as_page_text() -> None:
    html = f"<html><body><main><p>{PROSE}</p></main><nav><p>Tide index and notes. {FOG}</p></nav></body></html>"
    body = body_of(parse_html(html))
    assert dropped_text(body, PROSE) is None


def test_engine_warns_when_it_loses_a_section_it_could_not_keep() -> None:
    """A lone section takes no outline exemption, so the rules engine still drops it; the loss must say so."""
    html = f"""<html><head><title>Manual</title></head><body><main><p>{PROSE}</p><p>{FOG}</p>
    <div id="share-of-the-catch"><h2>Share of the Catch</h2><p>{TENDER}</p></div>
    </main></body></html>"""
    doc = _convert(html, RulesConverter())
    assert "Share of the Catch" not in doc.plain_text()
    w = next(x for x in doc.warnings if x.kind == WarningKind.EXTRACTION_DROPPED_TEXT)
    assert w.detail["sections"] == "Share of the Catch"


def test_ordinary_article_raises_no_dropped_text_warning() -> None:
    html = f"""<html><head><title>Manual</title></head><body><main><article><h1>Manual</h1><p>{PROSE}</p>
    <h2>Details</h2><p>{PROSE}</p></article><aside class="related-posts"><p>Other stories.</p></aside></main>
    </body></html>"""
    for conv in (TrafilaturaConverter(), RulesConverter()):
        assert str(WarningKind.EXTRACTION_DROPPED_TEXT) not in _kinds(_convert(html, conv))


def test_a_short_server_rendered_page_is_not_a_js_shell() -> None:
    links = " ".join(f"Harbor notice number {n} for the coming season." for n in range(12))
    html = f"""<html><head><title>Notices</title></head><body><div id="__next"><main><h1>Notices</h1>
    <p>The light is closed for repairs.</p></main><footer><p>{links}</p></footer></div></body></html>"""
    doc = _convert(html, TrafilaturaConverter())
    assert str(WarningKind.EMPTY_BODY_JS_REQUIRED) not in _kinds(doc)
    assert "closed for repairs" in doc.plain_text()


def test_an_empty_app_root_is_still_a_js_shell() -> None:
    html = '<html><head><title>App</title></head><body><div id="__next"></div><script>go()</script></body></html>'
    assert str(WarningKind.EMPTY_BODY_JS_REQUIRED) in _kinds(_convert(html, TrafilaturaConverter()))


def test_full_body_engine_does_not_measure_itself() -> None:
    assert str(WarningKind.EXTRACTION_DROPPED_TEXT) not in _kinds(_convert(PAGE, FullBodyConverter()))
