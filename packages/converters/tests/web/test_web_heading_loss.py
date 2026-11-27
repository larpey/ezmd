"""When a heading missing from the output is lost text (D-0089). Synthetic pages."""

from __future__ import annotations

import pytest

from ezmd.ir import Warning
from ezmd_converters.web.coverage import dropped_text
from ezmd_converters.web.dom import body_of, parse_html

QUESTION = "How does the keeper signal the tender in thick weather?"
LEAD = "The keeper trims the wick at dusk and writes the hour of lighting in the station book. " * 6
ANSWER = "In thick weather the bell strikes twice a minute until a ship answers or the fog lifts. " * 6
OTHER = "The tender calls at the light each spring with oil, coal and the post from the mainland. " * 6
LEAD, ANSWER, OTHER = LEAD.strip(), ANSWER.strip(), OTHER.strip()


def _warning(inner: str, extracted: str) -> Warning:
    w = dropped_text(body_of(parse_html(f"<html><body><main>{inner}</main></body></html>")), extracted)
    assert w is not None
    return w


def _figures(w: Warning) -> tuple[object, object]:
    return w.detail["page_chars"], w.detail["dropped_chars"]


@pytest.mark.parametrize(
    "faq",
    [
        f"<h3>{QUESTION}</h3><p>{ANSWER}</p>",
        f"<ul><li><h3>{QUESTION}</h3> {ANSWER}</li></ul>",
        f"<ul><li><h3>{QUESTION}</h3><p>{ANSWER}</p></li></ul>",
        f"<h2>{QUESTION}</h2><h3>Bell</h3><p>{ANSWER}</p>",
    ],
)
def test_a_missing_heading_whose_text_survived_is_lost(faq: str) -> None:
    w = _warning(f"<p>{LEAD}</p>{faq}<h2>Stores</h2><p>{OTHER}</p>", f"{LEAD} {ANSWER}")
    short = len("Stores") + (len("Bell") if "Bell" in faq else 0)
    page = len(LEAD) + len(QUESTION) + len(ANSWER) + len(OTHER) + short
    assert _figures(w) == (page, len(QUESTION) + len(OTHER))


@pytest.mark.parametrize(
    "faq",
    [
        f"<h3>{QUESTION}</h3><p>{ANSWER}</p>",
        f"<ul><li><h3>{QUESTION}</h3> {ANSWER}</li></ul>",
        f"<h3>{QUESTION}</h3>",
    ],
)
def test_a_heading_missing_with_its_section_adds_no_lost_characters(faq: str) -> None:
    w = _warning(f"<p>{LEAD}</p>{faq}<h2>Stores</h2><p>{OTHER}</p>", OTHER)
    answer = len(ANSWER) if ANSWER in faq else 0
    page = len(LEAD) + len(QUESTION) + answer + len(OTHER) + len("Stores")
    assert _figures(w) == (page, len(LEAD) + answer)


def test_a_section_mostly_gone_does_not_add_its_heading() -> None:
    inner = f"<h2>{QUESTION}</h2><p>{LEAD}</p><p>{ANSWER}</p><p>{OTHER}</p>"
    w = _warning(inner, LEAD)
    assert w.detail["dropped_chars"] == len(ANSWER) + len(OTHER)


def test_the_next_heading_of_the_same_level_ends_the_section() -> None:
    inner = f"<p>{LEAD}</p><h2>{QUESTION}</h2><h2>Stores</h2><p>{ANSWER}</p><p>{OTHER}</p>"
    w = _warning(inner, f"{LEAD} {ANSWER}")
    assert w.detail["dropped_chars"] == len(OTHER)
