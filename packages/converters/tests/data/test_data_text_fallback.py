"""A text file that looks like a data format but does not parse falls back to plain text through the chain."""

from __future__ import annotations

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import WarningKind
from ezmd.registry import ConvertOptions, default_registry

# A geospatial metadata record in an indented "Key: value" layout: Magika calls it YAML, and it is not.
YAML_LIKE = b"""Identification_Information:
  Citation:
    Citation_Information:
      Originator: Example Field Station
      Publication_Date: 20031106
      Title: cell_towers_example
      Other_Citation_Details: Hard copy: see Figure 7.21, Chapter 7, p. 90, in Example et al. 2004: a report
  Description:
    Abstract: Communication tower locations: digitized from maps: 1:100,000 scale.
    Purpose: To show: where towers are.
"""

XML_LIKE = b"""<document>
<doctype type="OTHER">
<docheader><DISPOSITION></DISPOSITION></docheader>
<section>
<p style="HEADING1"><font>(ORDER LIST: 526 U.S.)<left></p>
<p style="Normal"><center><f f="Typewriter"><fs fs="10">CERTIORARI DENIED
</section>
</document>
"""


def _convert(data: bytes, name: str):  # type: ignore[no-untyped-def]
    reg = default_registry()  # builtins, entry points and the default chains, as the library builds it
    ref = InputRef.from_bytes(data, filename=name)
    detect(ref)
    try:
        return reg.convert(ref, ConvertOptions())
    finally:
        ref.cleanup()


@pytest.mark.parametrize(("data", "name"), [(YAML_LIKE, "metadata.txt"), (XML_LIKE, "opinion.txt")])
def test_unparsable_data_text_falls_back_to_plain_text(data: bytes, name: str) -> None:
    res = _convert(data, name)
    assert res.converter_id == "text.plain"
    assert WarningKind.ENGINE_FALLBACK in [w.kind for w in res.warnings]
    text = "".join(s.text for b in res.document.blocks for s in getattr(b, "spans", []))
    assert "tower" in text.lower() or "certiorari" in text.lower()
