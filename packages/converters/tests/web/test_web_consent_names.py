"""Consent banners are recognised by name, not by the words a privacy notice is about (D-0082)."""

from __future__ import annotations

import pytest

from ezmd_converters.web.boilerplate import strip_boilerplate
from ezmd_converters.web.dom import body_of, parse_html, text_of

PROSE = "The keeper trims the wick at dusk and writes the hour of lighting in the station book. " * 4


def _kept(inner: str) -> str:
    body = body_of(parse_html(f"<html><body><main><p>{PROSE}</p>{inner}</main></body></html>"))
    strip_boilerplate(body, aggressive=False)
    return text_of(body)


@pytest.mark.parametrize(
    "inner",
    [
        '<div class="cmp-container"><div class="cmp-text"><p>Keepmark: the station book is kept.</p></div></div>',
        '<section id="ccpa-rights"><h2>Your rights</h2><p>Keepmark: you may ask what we hold.</p></section>',
        '<div class="gdpr-notice-body"><p>Keepmark: the lawful basis for each record.</p></div>',
        '<form-section class="consent-terms"><p>Keepmark: the terms of the photo check.</p></form-section>',
    ],
)
def test_component_and_subject_names_are_not_banners(inner: str) -> None:
    assert "Keepmark" in _kept(inner)


@pytest.mark.parametrize(
    "inner",
    [
        '<div id="cookie-banner"><p>Dropmark: we use cookies.</p></div>',
        '<div class="consent-banner"><p>Dropmark: accept all?</p></div>',
        '<div id="onetrust-consent-sdk"><p>Dropmark: manage preferences.</p></div>',
        '<div class="qc-cmp2-container"><p>Dropmark: we value your privacy.</p></div>',
        '<div class="privacy-banner"><p>Dropmark: this site uses trackers.</p></div>',
        '<div class="gdpr-popup"><p>Dropmark: consent to tracking.</p></div>',
    ],
)
def test_consent_banners_are_still_removed(inner: str) -> None:
    assert "Dropmark" not in _kept(inner)
