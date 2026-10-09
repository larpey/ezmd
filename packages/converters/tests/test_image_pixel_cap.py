"""Pillow's decompression-bomb cap is 50 megapixels (docs/spec/part1.md 8.2), set once when
ezmd_converters is imported, before any converter can open an image."""

from __future__ import annotations

import io

import pytest

PIL_Image = pytest.importorskip("PIL.Image")


def test_max_image_pixels_is_50_megapixels() -> None:
    import ezmd_converters

    assert ezmd_converters.MAX_IMAGE_PIXELS == 50_000_000
    assert PIL_Image.MAX_IMAGE_PIXELS == 50_000_000


def test_a_child_process_import_sets_the_cap() -> None:
    """The conversion child imports converters fresh; the cap must not depend on a test fixture."""
    import subprocess
    import sys

    code = "import ezmd_converters, PIL.Image; print(PIL.Image.MAX_IMAGE_PIXELS)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "50000000"


def test_oversized_image_header_is_refused() -> None:
    """A 12000 x 10000 PNG (120 MP) is refused at open: over 2x the 50 MP cap, though under 2x
    Pillow's 89 MP default, so this fails without the cap."""
    import ezmd_converters  # noqa: F401 - applies the cap

    buf = io.BytesIO()
    PIL_Image.new("1", (12000, 10000)).save(buf, format="PNG")
    with pytest.raises(PIL_Image.DecompressionBombError):
        PIL_Image.open(io.BytesIO(buf.getvalue()))
