"""Generate the PDF golden-fixture inputs (self-generated, CC0-1.0).

Run from the repository root:  uv run python fixtures/pdf/_generate.py

Every PDF is written with pikepdf (MPL-2.0, a default dependency) from hand-built content streams that use
the standard 14 fonts (Helvetica, Helvetica-Bold), so no font files and no reportlab are needed. Output is
deterministic (`deterministic_id=True`, no dates), so re-running the script reproduces the committed bytes.
"""

from __future__ import annotations

import textwrap
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, String

HERE = Path(__file__).resolve().parent
PAGE_W, PAGE_H = 612.0, 792.0
FONTS = {"F1": "Helvetica", "F2": "Helvetica-Bold"}


@dataclass
class Page:
    ops: list[tuple[list[object], str]] = field(default_factory=list)
    links: list[tuple[tuple[float, float, float, float], Dictionary]] = field(default_factory=list)
    images: dict[str, pikepdf.Stream] = field(default_factory=dict)

    def text(
        self, x: float, y: float, s: str, size: float = 10.0, bold: bool = False, mcid: tuple[str, int] | None = None
    ) -> None:
        if mcid is not None:
            self.ops.append(([Name("/" + mcid[0]), Dictionary(MCID=mcid[1])], "BDC"))
        self.ops.append(([], "BT"))
        self.ops.append(([Name("/F2" if bold else "/F1"), size], "Tf"))
        self.ops.append(([x, y], "Td"))
        self.ops.append(([String(s.encode("cp1252"))], "Tj"))
        self.ops.append(([], "ET"))
        if mcid is not None:
            self.ops.append(([], "EMC"))

    def para(
        self, x: float, y: float, body: str, width_chars: int = 95, size: float = 10.0, leading: float = 13.0
    ) -> float:
        """Write wrapped text; return the y below the last line."""
        for line in textwrap.wrap(body, width_chars):
            self.text(x, y, line, size)
            y -= leading
        return y - leading * 0.6


def _image_stream(pdf: pikepdf.Pdf, w: int, h: int) -> pikepdf.Stream:
    """A grayscale test pattern (stripes and a frame), Flate-compressed."""
    rows = bytearray()
    for yy in range(h):
        for xx in range(w):
            edge = xx < 4 or yy < 4 or xx >= w - 4 or yy >= h - 4
            rows.append(0 if edge else (40 if (xx // 16 + yy // 16) % 2 else 220))
    st = pikepdf.Stream(pdf, zlib.compress(bytes(rows), 9))
    st.Type = Name.XObject
    st.Subtype = Name.Image
    st.Width = w
    st.Height = h
    st.ColorSpace = Name.DeviceGray
    st.BitsPerComponent = 8
    st.Filter = Name.FlateDecode
    return st


def build(pages: Sequence[Page], title: str, *, tagged: bool = False) -> pikepdf.Pdf:
    pdf = pikepdf.new()
    fonts = Dictionary()
    for key, base in FONTS.items():
        fonts[Name("/" + key)] = pdf.make_indirect(
            Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name("/" + base), Encoding=Name.WinAnsiEncoding)
        )
    for pg in pages:
        resources = Dictionary(Font=fonts)
        if pg.images:
            resources.XObject = Dictionary({Name("/" + k): v for k, v in pg.images.items()})
        content = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(pg.ops))
        page = pikepdf.Page(
            Dictionary(
                Type=Name.Page,
                MediaBox=Array([0, 0, PAGE_W, PAGE_H]),
                Resources=resources,
                Contents=pdf.make_indirect(content),
            )
        )
        pdf.pages.append(page)
        if pg.links:
            annots = Array()
            for rect, action in pg.links:
                annots.append(
                    pdf.make_indirect(
                        Dictionary(
                            Type=Name.Annot,
                            Subtype=Name.Link,
                            Rect=Array(list(rect)),
                            Border=Array([0, 0, 0]),
                            A=action,
                        )
                    )
                )
            pdf.pages[-1].obj.Annots = annots
    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        meta["dc:title"] = title
    pdf.docinfo = pdf.make_indirect(Dictionary(Title=String(title), Author=String("intomd fixtures")))
    if tagged:
        pdf.Root.MarkInfo = Dictionary(Marked=True)
        pdf.Root.Lang = String("en-US")
    return pdf


def save(pdf: pikepdf.Pdf, name: str, **kw: object) -> None:
    out = HERE / name / "input.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    if "encryption" in kw:
        # qpdf cannot derive a deterministic id for encrypted output; AES salts are random anyway, so the
        # encrypted fixture's bytes change on every run (its content does not).
        pdf.save(out, static_id=True, **kw)  # type: ignore[arg-type]
    else:
        pdf.save(out, deterministic_id=True, **kw)  # type: ignore[arg-type]
    print(f"wrote {out.relative_to(HERE.parent.parent)} ({out.stat().st_size} bytes)")


LOREM = (
    "The harbor authority reviewed every berth on the east quay during the spring survey. Inspectors measured "
    "the fender wear, logged the bollard loads, and compared the readings with the previous season. Most berths "
    "were within tolerance, and the two that were not were scheduled for repair before the summer peak."
)


def running(pg: Page, n: int, total: int) -> None:
    pg.text(72, 760, "Harbor Lane Annual Report 2025", 8)
    pg.text(500, 760, "Confidential", 8)
    pg.text(280, 30, f"Page {n} of {total}", 8)


def born_digital_report() -> None:
    total = 4
    pages = [Page() for _ in range(total)]
    p1, p2, p3, p4 = pages
    for i, pg in enumerate(pages, start=1):
        running(pg, i, total)
    y = 700.0
    p1.text(72, y, "Harbor Lane Annual Report", 24, bold=True)
    y -= 40
    p1.text(72, y, "1. Overview", 16, bold=True)
    y -= 24
    y = p1.para(72, y, LOREM)
    y = p1.para(
        72,
        y,
        "This report collects the information the board asked for in January. It covers berth condition, "
        "cargo volumes, staffing, and the capital plan for the next two years.",
    )
    p1.text(72, y, "1.1 Scope", 13, bold=True)
    y -= 20
    y = p1.para(72, y, "The survey covered the following areas of the port:")
    for item in (
        "East quay berths one to six",
        "The container yard and its lighting",
        "Rail sidings and the gate complex",
    ):
        p1.text(84, y, chr(0x2022) + " " + item)
        y -= 14
    y -= 8
    y = p1.para(72, y, "Each area was inspected twice, once at low tide and once at high tide.")

    y = 700.0
    p2.text(72, y, "2. Berth condition", 16, bold=True)
    y -= 24
    # A hyphenated line break whose joined word ("information") appears elsewhere in the document.
    p2.text(72, y, "Fender wear was the most common finding. The inspection team recorded infor-")
    y -= 13
    p2.text(72, y, "mation about each fender on a tablet and uploaded it to the asset register the same day.")
    y -= 21
    y = p2.para(72, y, LOREM)
    p2.text(72, y, "2.1 Repairs scheduled", 13, bold=True)
    y -= 20
    for n, item in enumerate(
        ("Replace fenders on berth three", "Re-anchor bollard 14", "Resurface the berth five apron"), 1
    ):
        p2.text(84, y, f"{n}. {item}")
        y -= 14
    y -= 8
    y = p2.para(72, y, "Repairs are funded from the maintenance reserve and do not need board approval.")

    y = 700.0
    p3.text(72, y, "3. Cargo volumes", 16, bold=True)
    y -= 24
    y = p3.para(
        72, y, "Volumes rose in every quarter except the third, when the rail sidings were closed for two weeks."
    )
    p3.text(72, y, "Further detail is published on the port website.")
    p3.links.append(
        ((72, y - 3, 300, y + 10), Dictionary(S=Name.URI, URI=String("https://example.org/harbor-lane/volumes")))
    )
    y -= 26
    p3.text(72, y, "3.1 Staffing", 13, bold=True)
    y -= 20
    y = p3.para(
        72, y, "Staffing stayed flat at 212 full-time employees. Seasonal hiring added 31 people for the summer peak."
    )

    y = 700.0
    p4.text(72, y, "4. Capital plan", 16, bold=True)
    y -= 24
    y = p4.para(72, y, "The capital plan funds a new gate complex in 2026 and quay lighting in 2027.")
    y = p4.para(72, y, "The board will review the plan again in the autumn once the tender results are known.")
    save(build(pages, "Harbor Lane Annual Report"), "born-digital-report")


def simple_table() -> None:
    pg = Page()
    y = 700.0
    pg.text(72, y, "Quarterly cargo throughput", 16, bold=True)
    y -= 26
    y = pg.para(72, y, "The table lists cargo handled per quarter, in thousand tonnes, by terminal.")
    cols = (72, 200, 300, 400)
    rows = [
        ("Terminal", "Q1", "Q2", "Q3"),
        ("East quay", "120", "135", "98"),
        ("West quay", "88", "91", "77"),
        ("Container yard", "301", "322", "290"),
        ("Bulk berth", "45", "52", "49"),
    ]
    for r, row in enumerate(rows):
        for x, cell in zip(cols, row, strict=True):
            pg.text(x, y, cell, 10, bold=(r == 0))
        y -= 16
    y -= 12
    pg.para(72, y, "Totals are reported separately in the annual statement.")
    save(build([pg], "Quarterly cargo throughput"), "simple-table")


def two_column_page() -> None:
    pg = Page()
    pg.text(72, 720, "Tidal Patterns in a Small Harbor", 18, bold=True)
    left = (
        "Tides in the inner harbor follow a semidiurnal pattern with two highs and two lows each lunar day. "
        "The range at the north wall averages two point one meters, and spring tides add roughly forty "
        "centimeters to that figure. Gauges were read every ten minutes for a full year."
    )
    right = (
        "Wind set-up matters more than expected. A steady southerly wind above twenty knots raised the "
        "observed level by up to thirty centimeters for several hours. Pilots now consult the wind forecast "
        "together with the tide table before scheduling deep-draft arrivals."
    )
    lw = textwrap.wrap(left, 44)
    rw = textwrap.wrap(right, 44)
    y = 690.0
    # Interleave the two columns in the content stream (left line, right line, ...) so a naive
    # content-order extraction would mix them; the converter must restore column order.
    for i in range(max(len(lw), len(rw))):
        if i < len(lw):
            pg.text(72, y, lw[i])
        if i < len(rw):
            pg.text(326, y, rw[i])
        y -= 13
    pg.text(72, y - 20, "Both columns together describe one year of observations.")
    save(build([pg], "Tidal Patterns in a Small Harbor"), "two-column-page")


def image_only_page() -> None:
    p1 = Page()
    p1.text(72, 700, "Inspection photographs", 16, bold=True)
    p1.para(72, 674, "The next page is a scanned photograph of the berth three fenders. It has no text layer.")
    p2 = Page()
    pages = [p1, p2]
    pdf = build(pages, "Inspection photographs")
    img = _image_stream(pdf, 256, 192)
    page2 = pdf.pages[1]
    page2.obj.Resources.XObject = Dictionary(Im1=img)
    page2.obj.Contents = pdf.make_indirect(
        pikepdf.Stream(
            pdf,
            pikepdf.unparse_content_stream(
                [([], "q"), ([540, 0, 0, 720, 36, 36], "cm"), ([Name("/Im1")], "Do"), ([], "Q")]
            ),
        )
    )
    save(pdf, "image-only-page")


def encrypted_user_password() -> None:
    pg = Page()
    pg.text(72, 700, "Board minutes", 16, bold=True)
    pg.para(72, 674, "These minutes are restricted to board members.")
    save(
        build([pg], "Board minutes"),
        "encrypted-user-password",
        encryption=pikepdf.Encryption(user="fixture", owner="fixture-owner", R=6),
    )


def javascript_attachment() -> None:
    pg = Page()
    pg.text(72, 700, "Berth booking form", 16, bold=True)
    y = pg.para(72, 674, "Open the attached spreadsheet to see the booking calendar for the next quarter.")
    pg.text(72, y, "Click here to validate your booking.")
    pg.links.append(((72, y - 3, 260, y + 10), Dictionary(S=Name.JavaScript, JS=String("app.alert('validated');"))))
    pdf = build([pg], "Berth booking form")
    pdf.Root.OpenAction = Dictionary(S=Name.JavaScript, JS=String("app.alert('hello');"))
    pdf.pages[0].obj.AA = Dictionary(O=Dictionary(S=Name.Launch, F=String("calc.exe")))
    js_tree = Dictionary(
        Names=Array([String("init"), pdf.make_indirect(Dictionary(S=Name.JavaScript, JS=String("var x = 1;")))])
    )
    pdf.Root.Names = Dictionary(JavaScript=js_tree)
    spec = pikepdf.AttachedFileSpec(pdf, b"berth,date\n3,2025-07-01\n", mime_type="text/csv", filename="bookings.csv")
    pdf.attachments["bookings.csv"] = spec
    save(pdf, "javascript-attachment")


def tagged_structure_tree() -> None:
    """Tagged PDF whose structure tree says H1/H2 while the visual sizes are inverted (H2 drawn larger)."""
    pg = Page()
    pg.text(72, 700, "Port safety handbook", 14, bold=True, mcid=("H1", 0))
    pg.text(72, 676, "This handbook applies to every person working on the quay.", 10, mcid=("P", 1))
    pg.text(72, 646, "Personal protective equipment", 20, bold=True, mcid=("H2", 2))
    pg.text(72, 620, "Hard hats and high-visibility vests are required at all times.", 10, mcid=("P", 3))
    pg.text(72, 590, "Night work", 20, bold=True, mcid=("H2", 4))
    pg.text(72, 564, "Night shifts need a second person within sight at all times.", 10, mcid=("P", 5))
    pdf = build([pg], "Port safety handbook", tagged=True)
    page = pdf.pages[0].obj
    page.StructParents = 0
    root = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot))
    doc_el = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name.Document, P=root))
    kids = Array()
    parent_nums = Array()
    for mcid, tag in enumerate(("H1", "P", "H2", "P", "H2", "P")):
        el = pdf.make_indirect(Dictionary(Type=Name.StructElem, S=Name("/" + tag), P=doc_el, Pg=page, K=mcid))
        kids.append(el)
        parent_nums.append(el)
    doc_el.K = kids
    root.K = doc_el
    root.ParentTree = pdf.make_indirect(Dictionary(Nums=Array([0, parent_nums])))
    pdf.Root.StructTreeRoot = root
    save(pdf, "tagged-structure-tree")


def main() -> None:
    born_digital_report()
    simple_table()
    two_column_page()
    image_only_page()
    encrypted_user_password()
    javascript_attachment()
    tagged_structure_tree()


if __name__ == "__main__":
    main()
