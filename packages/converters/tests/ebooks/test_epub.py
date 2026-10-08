from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import Document, Footnote, Heading, Image, PageBreak, Paragraph, WarningKind, spans_text
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.ebooks.epub import EpubConverter

ROOT = Path(__file__).resolve().parents[4]
NOVEL = ROOT / "fixtures" / "ebooks" / "epub3-novel" / "input.epub"

CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)


def page(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
        f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>t</title></head><body>{body}</body></html>'
    )


def opf(chapters: list[str], extra_manifest: str = "", title: str = "Book") -> str:
    item = '<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
    items = "".join(item.format(i=i) for i in range(len(chapters)))
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
    return (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title>'
        "<dc:language>fr</dc:language><dc:creator>A. Writer</dc:creator><dc:date>2001</dc:date></metadata>"
        f"<manifest>{items}{extra_manifest}</manifest><spine>{spine}</spine></package>"
    )


def epub(chapters: list[str], *, extra: dict[str, str] | None = None, mimetype: bool = True, **kw: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if mimetype:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf(chapters, **kw))
        for i, body in enumerate(chapters):
            zf.writestr(f"OEBPS/c{i}.xhtml", page(body))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def convert(data: bytes, name: str = "b.epub", options: ConvertOptions | None = None) -> Document:
    ref = InputRef.from_bytes(data, filename=name)
    detect(ref)
    try:
        return EpubConverter().convert(ref, options or ConvertOptions())
    finally:
        ref.cleanup()


def kinds(doc: Document) -> set[WarningKind]:
    return {w.kind for w in doc.warnings}


@pytest.fixture(scope="module")
def novel() -> Document:
    if not NOVEL.exists():
        pytest.skip("run fixtures/ebooks/_generate.py first")
    return convert(NOVEL.read_bytes(), "input.epub")


def test_novel_metadata(novel: Document) -> None:
    m = novel.metadata
    assert m.title == "The Lighthouse Keeper"
    assert m.authors == ["Mara Quill"], "the editor (role edt) is not an author"
    assert m.extra["editors"] == "Ivo Pent"
    assert m.pages == 4
    assert m.extra["cover_image"] == "images/cover.png"
    assert m.language == "en" and m.language_source == "declared"
    assert m.published is not None and m.published.year == 2024
    assert m.extra["has_print_pages"] is True


def test_novel_spine_order_and_toc_headings(novel: Document) -> None:
    heads = [(b.level, spans_text(b.spans)) for b in novel.blocks if isinstance(b, Heading)]
    assert heads == [
        (1, "Chapter One: The Lamp"),
        (1, "Chapter Two: The Harbor"),
        (2, "Tide Tables"),
        (1, "Chapter Three: The Storm"),
    ]  # the notes-only non-linear file adds its footnote but no hollow headings
    synthetic = [b for b in novel.blocks if isinstance(b, Heading) and b.attrs.get("origin") == "toc"]
    assert [spans_text(b.spans) for b in synthetic] == ["Chapter Two: The Harbor"]


def test_novel_footnotes_are_linked(novel: Document) -> None:
    notes = [b for b in novel.blocks if isinstance(b, Footnote)]
    assert len(notes) == 2
    refs = [s.footnote_ref for b in novel.blocks if isinstance(b, Paragraph) for s in b.spans if s.footnote_ref]
    assert refs == [n.id for n in notes]
    assert "ninety steps" in spans_text(notes[0].spans)
    assert notes[1].provenance.path == "OEBPS/text/notes.xhtml#en1"
    assert [n.marker for n in notes] == ["1", "2"], "markers are the visible noteref text"


def test_novel_images_cover_and_pages(novel: Document) -> None:
    images = [b for b in novel.blocks if isinstance(b, Image)]
    assert [i.ref for i in images] == ["images/harbor-map.png"], "the cover is metadata, not a numbered figure"
    fig = images[0]
    assert fig.alt == "Hand-drawn map of the harbor"
    assert fig.provenance.source_page == 1 and fig.provenance.path == "OEBPS/images/harbor-map.png"
    assert fig.caption and spans_text(fig.caption) == "The harbor as Elin drew it."
    assert [b.page_number for b in novel.blocks if isinstance(b, PageBreak)] == [1, 2, 3, 4]
    tail = next(b for b in novel.blocks if isinstance(b, Paragraph) and "midnight" in spans_text(b.spans))
    assert tail.provenance.source_page == 2


def test_novel_provenance_paths_and_hidden(novel: Document) -> None:
    assert all(b.provenance.path for b in novel.blocks)
    text = novel.plain_text()
    assert "hidden tracking text" not in text
    assert WarningKind.REMOVED_HIDDEN_ELEMENTS in kinds(novel)


def test_nonlinear_can_be_left_out() -> None:
    if not NOVEL.exists():
        pytest.skip("fixture missing")
    doc = convert(NOVEL.read_bytes(), options=ConvertOptions(extra={"text.epub_nonlinear": False}))
    assert "Non-linear content" not in doc.plain_text()
    assert "red cross" not in doc.plain_text()


def test_nonlinear_with_content_keeps_its_heading() -> None:
    chapters = ["<p>main</p>", "<h2>Answers</h2><p>42</p>"]
    package = opf(chapters).replace('<itemref idref="c1"/>', '<itemref idref="c1" linear="no"/>')
    with pytest.warns(UserWarning, match="Duplicate name"):
        data = epub(chapters, extra={"OEBPS/content.opf": package})
    doc = convert(data)
    heads = [spans_text(b.spans) for b in doc.blocks if isinstance(b, Heading)]
    assert heads == ["Non-linear content", "Answers"]


def test_mimetype_missing_is_warned_and_parsed() -> None:
    doc = convert(epub(["<h1>One</h1><p>text</p>"], mimetype=False))
    assert WarningKind.EPUB_MIMETYPE_MISSING in kinds(doc)
    assert "text" in doc.plain_text()


def test_drm_encrypted_chapters_yield_drm_protected() -> None:
    enc = (
        '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
        '<enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
        '<enc:CipherData><enc:CipherReference URI="OEBPS/c0.xhtml"/></enc:CipherData>'
        "</enc:EncryptedData></encryption>"
    )
    doc = convert(epub(["<p>secret</p>"], extra={"META-INF/encryption.xml": enc, "META-INF/rights.xml": "<r/>"}))
    assert WarningKind.DRM_PROTECTED in kinds(doc)
    assert "secret" not in doc.plain_text()
    assert doc.blocks, "a stub explains the result"


def test_font_obfuscation_is_not_drm() -> None:
    enc = (
        '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
        '<enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
        '<enc:CipherData><enc:CipherReference URI="OEBPS/font.otf"/></enc:CipherData>'
        "</enc:EncryptedData></encryption>"
    )
    doc = convert(epub(["<p>open text</p>"], extra={"META-INF/encryption.xml": enc}))
    assert WarningKind.DRM_PROTECTED not in kinds(doc)
    assert "open text" in doc.plain_text()


def test_xxe_and_entity_expansion_are_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    uri = secret.as_uri()
    body = (
        '<?xml version="1.0"?><!DOCTYPE html [<!ENTITY xxe SYSTEM "' + uri + '">'
        '<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>start &xxe; &b; end</p></body></html>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf(["x"]))
        zf.writestr("OEBPS/c0.xhtml", body)
    doc = convert(buf.getvalue())
    text = doc.plain_text()
    assert "TOPSECRET" not in text
    assert "aaaaaaaaaa" not in text
    assert "start" in text and "end" in text


def test_html_entities_fall_back_to_the_html_parser() -> None:
    doc = convert(epub(["<p>one&nbsp;two &mdash; three</p>"]))
    assert "one" in doc.plain_text() and "three" in doc.plain_text()
    assert "onetwo" not in doc.plain_text()


def test_zip_limits_apply_to_epub() -> None:
    big = epub(["<p>x</p>"], extra={"OEBPS/zeros.bin": "0" * (8 * 1024 * 1024)})
    doc = convert(big)
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in kinds(doc)


def test_missing_opf_raises() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    with pytest.raises(ConversionError):
        convert(buf.getvalue())


def test_epub2_without_toc_has_no_synthetic_headings() -> None:
    doc = convert(epub(["<p>alpha</p>", "<p>beta</p>"]))
    assert not [b for b in doc.blocks if isinstance(b, Heading)]
    assert [spans_text(b.spans) for b in doc.blocks if isinstance(b, Paragraph)] == ["alpha", "beta"]
    assert doc.metadata.language == "fr" and doc.metadata.author == "A. Writer"


def test_table_spans_and_lists() -> None:
    body = (
        "<table><tr><th>a</th><th>b</th><th>c</th></tr>"
        '<tr><td rowspan="2">x</td><td colspan="2">y</td></tr><tr><td>z</td><td>w</td></tr></table>'
        "<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul><pre>code  kept</pre>"
    )
    doc = convert(epub([body]))
    table = next(b for b in doc.blocks if b.type == "table")
    assert (table.n_rows, table.n_cols, table.header_rows) == (3, 3, 1)
    assert table.has_merged_cells
    lst = next(b for b in doc.blocks if b.type == "list")
    assert [spans_text(i.spans) for i in lst.items] == ["one", "two"]
    assert spans_text(lst.items[0].children[0].spans) == "nested"
    code = next(b for b in doc.blocks if b.type == "code")
    assert code.code == "code  kept"


def test_can_handle() -> None:
    ref = InputRef.from_bytes(epub(["<p>x</p>"]), filename="noext")
    detect(ref)
    assert EpubConverter().can_handle(ref) >= 0.95
