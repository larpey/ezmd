"""XML dialects go to the XML converter; XHTML goes to the web converters."""

from __future__ import annotations

import pytest

from ezmd import detect as d
from ezmd.inputs import InputRef

XHTML = (
    b'<?xml version="1.0" encoding="utf-8"?>\n'
    b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
    b'"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n'
    b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Port safety</title></head>\n'
    b"<body><h1>Port safety</h1><p>Wear the vest on the quay.</p></body></html>\n"
)
RSS = (
    b'<?xml version="1.0"?>\n<rss version="2.0"><channel><title>News</title>'
    b"<item><title>A</title></item></channel></rss>\n"
)


def _fake(
    monkeypatch: pytest.MonkeyPatch, libmagic: str | None, label: str | None, mime: str | None, score: float
) -> None:
    # The real engines normalise their answers (that is where a +xml dialect becomes XML); so do the fakes.
    monkeypatch.setattr(d._Engines, "libmagic", classmethod(lambda cls, sample: d.normalize_mime(libmagic)))
    monkeypatch.setattr(d, "_magika_guess", lambda sample: (label, d.normalize_mime(mime), score))


def test_xml_dialects_normalize_to_xml() -> None:
    assert d.normalize_mime("application/rdf+xml") == "application/xml"
    assert d.normalize_mime("application/gpx+xml") == "application/xml"
    assert d.normalize_mime("application/vnd.google-earth.kml+xml") == "application/xml"
    assert d.normalize_mime("application/x-plist") == "application/xml"
    assert d.normalize_mime("application/xml-dtd") == "application/xml"
    # Types with their own converters or meaning keep their name.
    assert d.normalize_mime("application/xhtml+xml") == "application/xhtml+xml"
    assert d.normalize_mime("image/svg+xml") == "image/svg+xml"
    assert d.normalize_mime("application/x-ipynb+json") == "application/x-ipynb+json"


def test_rdf_file_is_detected_as_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, "application/rdf+xml", "rdf", "application/rdf+xml", 0.99)
    assert d.detect(InputRef.from_bytes(b"<rdf:RDF/>", filename="catalog.xml")).mime == "application/xml"


def test_xhtml_is_html_whatever_libmagic_says(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, "application/xml", "html", "text/html", 0.6)  # Magika's html below the threshold
    assert d.detect(InputRef.from_bytes(XHTML, filename="page.html")).mime == "application/xhtml+xml"
    assert d.detect(InputRef.from_bytes(XHTML, filename="page.xml")).mime == "application/xhtml+xml"
    assert d.detect(InputRef.from_bytes(XHTML, filename="page")).mime == "application/xhtml+xml"
    _fake(monkeypatch, "application/xml", "xml", "application/xml", 0.95)
    assert d.detect(InputRef.from_bytes(RSS, filename="feed.xml")).mime == "application/xml"


def test_real_engines_agree_on_the_samples() -> None:
    assert d.detect(InputRef.from_bytes(XHTML, filename="page.html")).mime in ("application/xhtml+xml", "text/html")
    assert d.detect(InputRef.from_bytes(RSS, filename="feed.xml")).mime == "application/xml"
