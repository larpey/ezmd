"""Notes and prose inside page chrome (D-0081). Synthetic pages; the prose is the lighthouse of the other web tests."""

from __future__ import annotations

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import Document, Footnote, WarningKind
from ezmd.registry import ConvertOptions
from ezmd_converters.web.engines import FullBodyConverter, RulesConverter, TrafilaturaConverter

PROSE = "The keeper trims the wick at dusk and writes the hour of lighting in the station book. " * 6
FOG = "In thick weather the bell strikes twice a minute until a ship answers or the fog lifts. " * 6
NOTE_ONE = "The tender sails only when the harbor master signs the weather slip for the crossing."
NOTE_TWO = "Lamp oil is issued by the gallon and every gallon is entered in the store ledger."
LONG_CHROME = (
    "The harbor office keeps the records of every station on this coast and answers letters about them within a "
    "month, except in winter, when the post comes once a fortnight and the office closes at noon on Saturdays and "
    "on the feast days of the harbor."
)
ENGINES = [TrafilaturaConverter(), RulesConverter(), FullBodyConverter()]


def _convert(html: str, conv: object) -> Document:
    ref = InputRef.from_bytes(html.encode("utf-8"), filename="page.html")
    detect(ref)
    return conv.convert(ref, ConvertOptions())  # type: ignore[attr-defined]


def _page(main: str, chrome: str) -> str:
    return f"""<html lang="en"><head><title>The Station</title></head><body>
    <nav><a href="/">Home</a> <a href="/stations">Stations</a></nav>
    <main><article><h1>The Station</h1>{main}</article></main>{chrome}</body></html>"""


def _notes(doc: Document) -> dict[str, str]:
    return {b.marker: "".join(s.text for s in b.spans) for b in doc.blocks if isinstance(b, Footnote)}


def _kinds(doc: Document) -> list[str]:
    return [str(w.kind) for w in doc.warnings]


@pytest.mark.parametrize("conv", ENGINES)
def test_footer_notes_the_body_points_at_are_footnotes(conv: object) -> None:
    main = f"<p>{PROSE} The tender calls in spring.<sup>1</sup></p><p>{FOG} Oil comes by sea.<sup>2</sup></p>"
    chrome = f'<footer><div class="disclosures"><p><sup>1</sup> {NOTE_ONE}</p><p>2. {NOTE_TWO}</p></div></footer>'
    doc = _convert(_page(main, chrome), conv)
    notes = _notes(doc)
    assert notes.get("1", "").strip() == NOTE_ONE
    assert notes.get("2", "").strip() == NOTE_TWO


def test_a_superscript_character_is_a_reference() -> None:
    main = f"<p>{PROSE} Calls are logged hourly²</p>"
    chrome = f'<div role="complementary"><p>² {NOTE_TWO}</p></div>'
    doc = _convert(_page(main, chrome), TrafilaturaConverter())
    assert _notes(doc).get("2", "").strip() == NOTE_TWO


def test_a_numbered_footer_line_nothing_points_at_is_not_a_note() -> None:
    main = f"<p>{PROSE}</p><p>{FOG}</p>"
    chrome = f"<footer><p>1. {NOTE_ONE}</p></footer>"
    doc = _convert(_page(main, chrome), TrafilaturaConverter())
    assert _notes(doc) == {}


@pytest.mark.parametrize("conv", ENGINES)
def test_long_prose_removed_from_inside_the_article_is_reported(conv: object) -> None:
    main = f"<p>{PROSE}</p><aside><p>{LONG_CHROME}</p></aside><p>{FOG}</p>"
    doc = _convert(_page(main, ""), conv)
    assert LONG_CHROME[:40] not in doc.plain_text()
    w = next(x for x in doc.warnings if x.kind == WarningKind.BOILERPLATE_PROSE_REMOVED)
    assert w.count == 1 and LONG_CHROME[:60] in str(w.detail["samples"])


def test_the_site_footer_is_quiet() -> None:
    """A site's legal footer repeats on every page; a warning about it would fire everywhere."""
    doc = _convert(_page(f"<p>{PROSE}</p><p>{FOG}</p>", f"<footer><p>{LONG_CHROME}</p></footer>"), RulesConverter())
    assert str(WarningKind.BOILERPLATE_PROSE_REMOVED) not in _kinds(doc)


@pytest.mark.parametrize(
    "chrome",
    [
        f'<div class="cookie-banner"><p>{LONG_CHROME}</p></div>',
        f'<div role="dialog"><p>{LONG_CHROME}</p></div>',
        f'<aside><div class="modal"><p>{LONG_CHROME}</p></div></aside>',
        f"<footer><form><p>{LONG_CHROME}</p></form></footer>",
        "<footer><p>"
        + " ".join(f'<a href="/s{i}">Station number {i} on the coast</a>' for i in range(12))
        + "</p></footer>",
        "<footer><p>Printed at the harbor office.</p></footer>",
    ],
)
def test_banners_dialogs_forms_link_lists_and_short_lines_are_quiet(chrome: str) -> None:
    """Inside the article, where removed prose does warn, these are still chrome."""
    chrome = chrome.replace("<footer>", "<aside>").replace("</footer>", "</aside>")
    doc = _convert(_page(f"<p>{PROSE}</p>{chrome}<p>{FOG}</p>", ""), TrafilaturaConverter())
    assert str(WarningKind.BOILERPLATE_PROSE_REMOVED) not in _kinds(doc)


def test_a_note_already_in_the_article_is_not_repeated() -> None:
    main = f"<p>{PROSE} The tender calls in spring.<sup>1</sup></p><ol><li>{NOTE_ONE}</li></ol>"
    chrome = f"<footer><p>1. {NOTE_ONE}</p></footer>"
    doc = _convert(_page(main, chrome), RulesConverter())
    assert _notes(doc) == {}
    assert doc.plain_text().count(NOTE_ONE) == 1


def test_notes_numbered_by_the_list_itself_are_footnotes() -> None:
    main = f"<p>{PROSE} The tender calls in spring.<sup>1</sup></p><p>{FOG} Oil comes by sea.<sup>2</sup></p>"
    chrome = (
        f'<footer><section id="disclaimer"><ol><li><p>{NOTE_ONE}</p></li><li><p>{NOTE_TWO}</p></li></ol>'
        "</section></footer>"
    )
    doc = _convert(_page(main, chrome), TrafilaturaConverter())
    assert _notes(doc) == {"1": NOTE_ONE, "2": NOTE_TWO}


def test_a_reference_in_a_banner_hero_still_counts() -> None:
    """A page whose title block is a role=banner region carries its references there."""
    html = f"""<html><head><title>Station</title></head><body>
    <div role="banner"><h2>Calls by tender<sup><a href="#legal">[1,2]</a></sup></h2></div>
    <main><p>{PROSE}</p><p>{FOG}</p></main>
    <div role="contentinfo"><ol id="legal"><li>{NOTE_ONE}</li><li>{NOTE_TWO}</li></ol></div></body></html>"""
    assert _notes(_convert(html, RulesConverter())) == {"1": NOTE_ONE, "2": NOTE_TWO}


def test_a_site_footer_inside_main_is_quiet() -> None:
    main = f"<p>{PROSE}</p><p>{FOG}</p><footer><p>{LONG_CHROME}</p></footer>"
    doc = _convert(_page(main, ""), TrafilaturaConverter())
    assert str(WarningKind.BOILERPLATE_PROSE_REMOVED) not in _kinds(doc)
