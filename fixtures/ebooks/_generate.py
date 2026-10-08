"""Generate the ebooks fixtures (self-authored text, CC0). Run: uv run python fixtures/ebooks/_generate.py

Writes input files only; goldens come from `uv run intomd-golden fixtures/ebooks/<name> --write`.
Output is deterministic (fixed zip timestamps) so re-running produces identical bytes.
"""

from __future__ import annotations

import json
import struct
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAMP = (2024, 1, 1, 0, 0, 0)
NL = chr(10)
ESC = chr(27)


def png(width: int = 2, height: int = 2, rgb: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def write_zip(path: Path, members: list[tuple[str, bytes]], *, stored_first: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for n, (name, data) in enumerate(members):
            info = zipfile.ZipInfo(name, date_time=STAMP)
            info.compress_type = zipfile.ZIP_STORED if (n == 0 and stored_first) else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)


def xhtml(title: str, body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        + NL
        + '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">'
        + NL
        + f'<head><title>{title}</title><link rel="stylesheet" href="style.css"/></head>'
        + NL
        + f"<body>{NL}{body}{NL}</body></html>{NL}"
    ).encode()


CONTAINER = (
    '<?xml version="1.0"?>'
    + NL
    + '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    + '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    + "</rootfiles></container>"
    + NL
).encode()


def epub3_novel() -> None:
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:5b2a7c1e-0000-4000-8000-000000000001</dc:identifier>
    <dc:title>The Lighthouse Keeper</dc:title>
    <dc:creator id="a1">Mara Quill</dc:creator>
    <dc:creator id="e1">Ivo Pent</dc:creator>
    <meta refines="#e1" property="role">edt</meta>
    <dc:language>en</dc:language>
    <dc:date>2024-03-15</dc:date>
    <dc:publisher>Fixture Press</dc:publisher>
    <dc:description>A short novel written for the intomd test corpus.</dc:description>
    <meta property="dcterms:modified">2024-03-15T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="style.css" media-type="text/css"/>
    <item id="cover" href="images/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="map" href="images/harbor-map.png" media-type="image/png"/>
    <item id="ch1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="text/chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch3" href="text/chapter3.xhtml" media-type="application/xhtml+xml"/>
    <item id="notes" href="text/notes.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
    <itemref idref="ch3"/>
    <itemref idref="notes" linear="no"/>
  </spine>
</package>
"""
    nav = xhtml(
        "Contents",
        """<nav epub:type="toc" id="toc"><h1>Contents</h1>
<ol>
  <li><a href="text/chapter1.xhtml">Chapter One: The Lamp</a></li>
  <li><a href="text/chapter2.xhtml">Chapter Two: The Harbor</a>
    <ol><li><a href="text/chapter2.xhtml#tides">Tide Tables</a></li></ol>
  </li>
  <li><a href="text/chapter3.xhtml">Chapter Three: The Storm</a></li>
</ol></nav>
<nav epub:type="page-list" hidden=""><ol>
  <li><a href="text/chapter1.xhtml#page1">1</a></li>
  <li><a href="text/chapter1.xhtml#page2">2</a></li>
  <li><a href="text/chapter2.xhtml#page3">3</a></li>
  <li><a href="text/chapter3.xhtml#page4">4</a></li>
</ol></nav>""",
    )
    ch1 = xhtml(
        "Chapter One",
        """<section epub:type="chapter" id="c1">
<span epub:type="pagebreak" id="page1" title="1"/>
<h1>Chapter One: The Lamp</h1>
<p>Every evening at dusk, <em>Elin</em> climbed the <strong>one hundred and twelve</strong> steps of the
tower to light the lamp.<a epub:type="noteref" href="#fn1">1</a> The wick had to be trimmed first.</p>
<figure id="fig-map"><img src="../images/harbor-map.png" alt="Hand-drawn map of the harbor"/>
<figcaption>The harbor as Elin drew it.</figcaption></figure>
<p>She kept a logbook of every ship<span style="display:none"> hidden tracking text</span> that passed.</p>
<span epub:type="pagebreak" id="page2" title="2"/>
<p>By midnight the beam swept the water every <code>12</code> seconds.</p>
<aside epub:type="footnote" id="fn1">
<p>The original tower had only ninety steps; the rest were added in 1871.</p></aside>
</section>""",
    )
    ch2 = xhtml(
        "Chapter Two",
        """<section epub:type="chapter" id="c2">
<p>The harbor woke before the keeper slept. Three things arrived each morning:</p>
<ul>
  <li>the fishing fleet,</li>
  <li>the mail boat, and
    <ol><li>its letters</li><li>its parcels</li></ol>
  </li>
  <li>the gulls.</li>
</ul>
<span epub:type="pagebreak" id="page3" title="3"/>
<h2 id="tides">Tide Tables</h2>
<table>
  <caption>High water, first week of March</caption>
  <thead><tr><th>Day</th><th>Morning</th><th>Evening</th></tr></thead>
  <tbody>
    <tr><td>Monday</td><td>05:12</td><td>17:40</td></tr>
    <tr><td>Tuesday</td><td colspan="2">no reading (fog)</td></tr>
  </tbody>
</table>
<blockquote><p>A keeper who forgets the tide forgets the sea.</p></blockquote>
</section>""",
    )
    ch3 = xhtml(
        "Chapter Three",
        """<section epub:type="chapter" id="c3">
<h1>Chapter Three: The Storm</h1>
<span epub:type="pagebreak" id="page4" title="4"/>
<p>The storm came from the west on the ninth night.<a epub:type="noteref" href="notes.xhtml#en1">2</a></p>
<p>Elin wrote the signal code on the wall:</p>
<pre><code class="language-text">LONG SHORT LONG
SHORT SHORT</code></pre>
<p>When morning came, the lamp was still burning.</p>
</section>""",
    )
    notes = xhtml(
        "Notes",
        """<section epub:type="endnotes"><h2>Notes</h2>
<aside epub:type="endnote" id="en1"><p>Storms from the west were recorded in the logbook with a red cross.</p></aside>
</section>""",
    )
    css = b"body { font-family: serif; }" + NL.encode()
    write_zip(
        HERE / "epub3-novel" / "input.epub",
        [
            ("mimetype", b"application/epub+zip"),
            ("META-INF/container.xml", CONTAINER),
            ("OEBPS/content.opf", opf.encode()),
            ("OEBPS/nav.xhtml", nav),
            ("OEBPS/style.css", css),
            ("OEBPS/images/cover.png", png(rgb=(20, 40, 160))),
            ("OEBPS/images/harbor-map.png", png(rgb=(30, 160, 60))),
            ("OEBPS/text/chapter1.xhtml", ch1),
            ("OEBPS/text/chapter2.xhtml", ch2),
            ("OEBPS/text/chapter3.xhtml", ch3),
            ("OEBPS/text/notes.xhtml", notes),
        ],
    )


def epub2_ncx() -> None:
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Field Notes on Moss</dc:title>
    <dc:creator opf:role="aut">Tove Linden</dc:creator>
    <dc:language>en-GB</dc:language>
    <dc:identifier id="bookid">urn:isbn:9780000000002</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="p1" href="part1.html" media-type="application/xhtml+xml"/>
    <item id="p1b" href="part1b.html" media-type="application/xhtml+xml"/>
    <item id="p2" href="part2.html" media-type="application/xhtml+xml"/>
    <item id="p2b" href="part2b.html" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="p1"/><itemref idref="p1b"/><itemref idref="p2"/><itemref idref="p2b"/>
  </spine>
</package>
"""
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:isbn:9780000000002"/></head>
  <docTitle><text>Field Notes on Moss</text></docTitle>
  <navMap>
    <navPoint id="n1" playOrder="1"><navLabel><text>Where Moss Grows</text></navLabel><content src="part1.html"/>
    </navPoint>
    <navPoint id="n2" playOrder="2"><navLabel><text>Collecting Samples</text></navLabel><content src="part2.html"/>
    </navPoint>
  </navMap>
</ncx>
"""
    p1 = xhtml("Part 1", "<p>Moss grows where the light is soft and the stone stays damp.</p>")
    p1b = xhtml(
        "Part 1b", "<p>North faces of walls are the most reliable places to look&#8212;but not the only ones.</p>"
    )
    p2 = xhtml("Part 2", "<h1>Collecting Samples</h1><p>Use a flat knife and a paper envelope, never plastic.</p>")
    p2b = xhtml("Part 2b", "<p>Label each envelope with the date, the place, and the surface.</p>")
    # EPUB2 file deliberately written without the `mimetype` entry (epub_mimetype_missing).
    write_zip(
        HERE / "epub2-ncx" / "input.epub",
        [
            ("META-INF/container.xml", CONTAINER),
            ("OEBPS/content.opf", opf.encode()),
            ("OEBPS/toc.ncx", ncx.encode()),
            ("OEBPS/part1.html", p1),
            ("OEBPS/part1b.html", p1b),
            ("OEBPS/part2.html", p2),
            ("OEBPS/part2b.html", p2b),
        ],
        stored_first=False,
    )


def lines(text: str) -> list[str]:
    parts = text.split(NL)
    return [p + NL for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def ipynb_analysis() -> None:
    # Code cells are deliberately NOT in formatter style (single quotes, odd spacing, extra blank lines) so
    # the golden proves code is copied verbatim; ruff excludes fixtures/**/expected.* (D-0021).
    import base64

    plot = base64.b64encode(png(4, 3, (10, 120, 200))).decode()
    att = base64.b64encode(png(2, 2, (250, 200, 0))).decode()
    table_html = (
        "<div><style scoped>.dataframe td { padding: 2px; }</style>"
        '<table border="1" class="dataframe"><thead><tr><th></th><th>species</th><th>count</th></tr></thead>'
        "<tbody><tr><th>0</th><td>heron</td><td>12</td></tr><tr><th>1</th><td>egret</td><td>7</td></tr>"
        "</tbody></table></div>"
    )
    tb = [
        ESC + "[0;31m---------------------------------------------------------------------------" + ESC + "[0m",
        ESC + "[0;31mZeroDivisionError" + ESC + "[0m                         Traceback (most recent call last)",
        "Cell " + ESC + "[0;32mIn[3], line 1" + ESC + "[0m",
        ESC + "[0;32m----> 1" + ESC + "[0m rate " + ESC + "[38;5;241m=" + ESC + "[39m total / days",
        ESC + "[0;31mZeroDivisionError" + ESC + "[0m: division by zero",
    ]
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python", "version": "3.12.0"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "id": "intro",
                "metadata": {},
                "source": lines(
                    "# Wading Bird Survey"
                    + NL
                    + NL
                    + "Counts from the **east marsh**, week 12.[^1] The rate is $r = n / d$."
                    + NL
                    + NL
                    + "- herons"
                    + NL
                    + "- egrets"
                    + NL
                    + NL
                    + "![Marsh sketch](attachment:sketch.png)"
                    + NL
                    + NL
                    + "[^1]: Counted at low tide."
                ),
                "attachments": {"sketch.png": {"image/png": att}},
            },
            {
                "cell_type": "code",
                "id": "load",
                "execution_count": 1,
                "metadata": {},
                "source": lines(
                    "import pandas as pd"
                    + NL
                    + "df=pd.read_csv( 'counts.csv' )"
                    + NL
                    + NL
                    + NL
                    + "print(len(df),'rows')   # count"
                ),
                "outputs": [{"output_type": "stream", "name": "stdout", "text": ["2 rows" + NL]}],
            },
            {
                "cell_type": "code",
                "id": "table",
                "execution_count": 2,
                "metadata": {},
                "source": ["df"],
                "outputs": [
                    {
                        "output_type": "execute_result",
                        "execution_count": 2,
                        "metadata": {},
                        "data": {
                            "text/html": [table_html],
                            "text/plain": ["  species  count" + NL, "0   heron     12" + NL, "1   egret      7"],
                        },
                    }
                ],
            },
            {
                "cell_type": "markdown",
                "id": "plot-md",
                "metadata": {},
                "source": ["## Plot" + NL, NL, "Counts by species, as a bar chart."],
            },
            {
                "cell_type": "code",
                "id": "plot",
                "execution_count": 3,
                "metadata": {},
                "source": ["df.plot.bar(x = 'species',y='count')"],
                "outputs": [
                    {
                        "output_type": "display_data",
                        "metadata": {},
                        "data": {"image/png": plot, "text/plain": ["<Figure size 400x300 with 1 Axes>"]},
                    }
                ],
            },
            {
                "cell_type": "code",
                "id": "rate",
                "execution_count": 4,
                "metadata": {},
                "source": ["total, days = 19, 0" + NL, "rate = total / days"],
                "outputs": [
                    {
                        "output_type": "error",
                        "ename": "ZeroDivisionError",
                        "evalue": "division by zero",
                        "traceback": tb,
                    }
                ],
            },
            {"cell_type": "raw", "id": "raw", "metadata": {"format": "text/x-rst"}, "source": [".. note:: raw rst"]},
        ],
    }
    out = HERE / "ipynb-analysis" / "input.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + NL, encoding="utf-8", newline=NL)


if __name__ == "__main__":
    epub3_novel()
    epub2_ncx()
    ipynb_analysis()
