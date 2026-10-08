"""documents.epub: EPUB 2 and 3 to the IR (docs/spec/part2.md section 4c steps 1-8).

Spine order, TOC headings (nav or NCX) without duplicating a chapter's own title, EPUB3 footnotes
(`epub:type` noteref/footnote), images as Image blocks with alt text, the cover, page-list page breaks,
and Dublin Core metadata. The zip is read under the archive limits; XHTML is parsed without entities or
network access. DRM (encryption.xml with a real cipher, or rights.xml) yields `drm_protected` and a stub.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Any

from ezmd.context import Limits
from ezmd.core.textclean import CleanStats
from ezmd.inputs import InputRef
from ezmd.ir import (
    Document,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    Metadata,
    PageBreak,
    Paragraph,
    Provenance,
    SourceType,
    Warning,
)
from ezmd.ir import WarningKind as W
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.archives.backends import ArchiveOpenError
from ezmd_converters.archives.guard import DEFAULT_MAX_ENTRIES, DEFAULT_MAX_TOTAL, ArchiveLimits, BombError, Budget
from ezmd_converters.ebooks.epub_package import (
    EPUB_MIME,
    XHTML_TYPES,
    EpubContainer,
    ManifestItem,
    Package,
    TocEntry,
    encrypted_resources,
    find_opf,
    parse_nav,
    parse_package,
    resolve,
)
from ezmd_converters.ebooks.xhtml import (
    WalkContext,
    Walker,
    find_body,
    is_footnote_el,
    is_noteref_el,
    local,
    parse_document,
)

ZIP_MIMES = ("application/zip", "application/x-zip-compressed", "application/octet-stream")
_SLUG = re.compile(r"[^A-Za-z0-9_-]+")
_NORM = re.compile(r"[\W_]+", re.UNICODE)


def _epub_head(head: bytes) -> bool:
    """The first zip member is the uncompressed `mimetype` entry holding application/epub+zip."""
    return (
        len(head) >= 58
        and head.startswith(b"PK\x03\x04")
        and head[26:28] == b"\x08\x00"
        and (head[30:38] == b"mimetype" and EPUB_MIME.encode() in head[38:90])
    )


def _norm(text: str) -> str:
    return _NORM.sub(" ", text.casefold()).strip()


def _slug(text: str) -> str:
    return _SLUG.sub("_", text)[:60]


class _Notes:
    """Footnote bodies found in a pre-scan of the spine, and the marker text of their references."""

    def __init__(self) -> None:
        self.ids: dict[tuple[str, str], str] = {}
        self.markers: dict[str, str] = {}

    def scan_bodies(self, path: str, root: Any) -> None:
        for el in root.iter():
            if not local(el):
                continue
            if is_footnote_el(el) and el.get("id"):
                self.ids[(path, el.get("id"))] = f"fn-{_slug(posixpath.basename(path))}-{_slug(el.get('id'))}"

    def scan_refs(self, path: str, root: Any) -> None:
        """Marker = the visible noteref text. Runs after every file's bodies are known, so a reference to an
        endnote in a later file gets its visible marker too."""
        for el in root.iter():
            if local(el) == "a" and is_noteref_el(el):
                target = resolve(path, el.get("href") or "")
                fid = self.ids.get((target[0], target[1] or ""))
                text = " ".join("".join(el.itertext()).split()).strip("[]()")
                if fid and fid not in self.markers:
                    self.markers[fid] = text or str(len(self.markers) + 1)


class EpubConverter:
    id = "documents.epub"
    family = "documents"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = (EPUB_MIME,)
    limits = Limits(max_bytes=DEFAULT_MAX_TOTAL, max_entries=DEFAULT_MAX_ENTRIES, timeout_s=120.0)

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if mime == EPUB_MIME:
            return 1.0
        if mime in ZIP_MIMES:
            if ref.display.lower().endswith(".epub"):
                return 0.95
            if ref.has_body and _epub_head(ref.head(64)):
                return 0.95
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        meta = Metadata(source=ref.display, source_type=SourceType.EPUB, mime=EPUB_MIME)
        doc = Document(metadata=meta)
        budget = Budget(ArchiveLimits.from_options(options))
        with ref.path().open("rb") as fp:
            try:
                book = EpubContainer(fp, budget)
            except ArchiveOpenError as e:
                raise ConversionError(f"{ref.display}: {e}", user_message="The EPUB file is corrupt.") from e
            except BombError as e:
                return _refused(doc, e)
            try:
                return _Builder(book, doc, ref.display, options).run()
            except BombError as e:
                return _refused(doc, e)
            finally:
                book.close()


def _refused(doc: Document, e: BombError) -> Document:
    doc.blocks = [
        Paragraph(
            spans=[InlineSpan(text="This EPUB expands beyond the safe archive limits and was not converted.")],
            provenance=Provenance(source=doc.metadata.source),
        )
    ]
    doc.warnings.append(
        Warning(kind=W.ARCHIVE_BOMB_SUSPECTED, message=f"The EPUB was refused: {e}.", detail={"reason": e.reason})
    )
    return doc.finalize()


class _Builder:
    def __init__(self, book: EpubContainer, doc: Document, source: str, options: ConvertOptions) -> None:
        self.book = book
        self.doc = doc
        self.source = source
        self.options = options
        self.stats = CleanStats()
        self.hidden = 0
        self.notes = _Notes()
        self.cover_path: str | None = None
        self.image_names: dict[str, str] = {}
        self.media: dict[str, ManifestItem] = {}
        self.image_dir = Path(options.image_dir) if options.image_dir and options.extract_images else None

    def run(self) -> Document:
        doc, book = self.doc, self.book
        if not book.mimetype_ok():
            doc.warnings.append(
                Warning(kind=W.EPUB_MIMETYPE_MISSING, message="The EPUB lacks a valid leading mimetype entry.")
            )
        opf = find_opf(book)
        pkg = parse_package(book, opf) if opf else None
        if pkg is None:
            raise ConversionError(f"{self.source}: no OPF package", user_message="The EPUB has no readable package.")
        self._metadata(pkg)
        self.media = pkg.by_path()
        encrypted, rights = encrypted_resources(book)
        toc, pages = parse_nav(book, pkg)
        chapters = [(item, linear) for item, linear in pkg.spine if item.media_type in XHTML_TYPES]
        locked = [item.path for item, _ in chapters if item.path in encrypted]
        if locked or (rights and encrypted):
            doc.warnings.append(
                Warning(
                    kind=W.DRM_PROTECTED,
                    message=_drm_message(locked),
                    count=len(locked),
                    detail={"files": ", ".join(locked[:_MAX_LISTED_FILES]), "encrypted_resources": len(encrypted)},
                )
            )
        parsed = self._parse_chapters([(i, lin) for i, lin in chapters if i.path not in encrypted])
        if pages:
            doc.metadata.extra["has_print_pages"] = True
            labels = {label for per_file in pages.values() for label in per_file.values() if label}
            doc.metadata.pages = len(labels)
        self._cover(pkg)
        titles = _first_titles(toc)
        linear = [(i, root) for i, lin, root in parsed if lin]
        nonlinear = [(i, root) for i, lin, root in parsed if not lin]
        for n, (item, root) in enumerate(linear):
            self.options.ctx.check_deadline()
            self.options.ctx.progress("epub", (n + 1) / max(len(linear), 1), item.path)
            self._chapter(item, root, titles.get(item.path), pages.get(item.path, {}))
            self.options.ctx.publish_partial(doc)
        if nonlinear and _flag(self.options, "text.epub_nonlinear", True):
            self._nonlinear(nonlinear, titles, pages)
        self._finish(bool(locked) and not parsed)
        return doc.finalize()

    def _nonlinear(
        self, items: list[tuple[ManifestItem, Any]], titles: dict[str, TocEntry], pages: dict[str, dict[str, str]]
    ) -> None:
        """Non-linear items (endnotes, answer keys) after the main text. When they hold nothing but footnote
        bodies (the notes already render where they are referenced) the section headings are dropped, so no
        hollow "Non-linear content" / "Notes" headings remain."""
        start = len(self.doc.blocks)
        for item, root in items:
            self._chapter(item, root, titles.get(item.path), pages.get(item.path, {}))
        added = self.doc.blocks[start:]
        if all(isinstance(b, Heading | Footnote | PageBreak) for b in added):
            self.doc.blocks[start:] = [b for b in added if not isinstance(b, Heading)]
            return
        self.doc.blocks.insert(
            start,
            Heading(
                level=1,
                spans=[InlineSpan(text="Non-linear content")],
                provenance=Provenance(source=self.source, path=items[0][0].path),
            ),
        )

    def _metadata(self, pkg: Package) -> None:
        m = self.doc.metadata
        m.title = pkg.title
        m.authors = pkg.creators
        m.author = pkg.creators[0] if pkg.creators else None
        if pkg.language:
            m.language = pkg.language
            m.language_source = "declared"
        m.published = pkg.date
        m.description = pkg.description
        m.extra.update({"epub_version": pkg.version or None, "identifier": pkg.identifier, "publisher": pkg.publisher})
        editors = [name for name, role in pkg.contributors if role == "edt"]
        others = [f"{name} ({role})" for name, role in pkg.contributors if role != "edt"]
        if editors:
            m.extra["editors"] = "; ".join(editors)
        if others:
            m.extra["contributors"] = "; ".join(others)

    def _parse_chapters(self, chapters: list[tuple[ManifestItem, bool]]) -> list[tuple[ManifestItem, bool, Any]]:
        out = []
        for item, linear in chapters:
            self.options.ctx.check_deadline()
            data = self.book.read(item.path)
            root = parse_document(data, html_mode=item.media_type == "text/html") if data else None
            if root is None:
                self.doc.warnings.append(
                    Warning(kind=W.MISSING_RESOURCE, message=f"Chapter {item.path} is missing or unreadable.")
                )
                continue
            self.notes.scan_bodies(item.path, root)
            out.append((item, linear, root))
        for item, _linear, root in out:
            self.notes.scan_refs(item.path, root)
        return out

    def _cover(self, pkg: Package) -> None:
        cover = pkg.cover()
        if cover is None or not cover.media_type.startswith("image/"):
            return
        # The cover is recorded in metadata, not as an Image block, so it is not counted as a numbered figure
        # in the body (the renderers number every Image). The bytes are still written when image_dir is set.
        self.cover_path = cover.path
        img = self._image_for(cover.path, cover.media_type, "Cover")
        if img is not None:
            self.doc.metadata.extra["cover_image"] = img.ref

    def _chapter(self, item: ManifestItem, root: Any, title: TocEntry | None, page_ids: dict[str, str]) -> None:
        ctx = WalkContext(
            source=self.source,
            path=item.path,
            stats=self.stats,
            resolve_image=lambda src, alt: self._resolve_image(item.path, src, alt),
            resolve_noteref=lambda href: self._noteref(item.path, href),
            footnote_id=lambda el_id: self.notes.ids.get((item.path, el_id)),
            footnote_marker=lambda fid: self.notes.markers.get(fid, fid.rsplit("-", 1)[-1]),
            page_ids=page_ids,
        )
        blocks = Walker(ctx).blocks(find_body(root))
        self.hidden += ctx.hidden_removed
        if title is not None:
            first = next((b for b in blocks if not isinstance(b, Image | PageBreak)), None)
            dup = isinstance(first, Heading) and _norm("".join(s.text for s in first.spans)) == _norm(title.title)
            if not dup:
                blocks.insert(
                    0,
                    Heading(
                        level=min(title.depth, 6),
                        spans=[InlineSpan(text=title.title)],
                        provenance=Provenance(source=self.source, path=item.path),
                        attrs={"origin": "toc"},
                    ),
                )
        self.doc.blocks.extend(blocks)

    def _noteref(self, base: str, href: str) -> str | None:
        path, frag = resolve(base, href)
        return self.notes.ids.get((path, frag or ""))

    def _resolve_image(self, base: str, src: str, alt: str | None) -> Image | None:
        if not src or src.startswith("data:"):
            return None
        path, _frag = resolve(base, src)
        if not path:
            return Image(ref=src, alt=alt, provenance=Provenance(source=self.source))
        if path == self.cover_path:
            return None
        item = self.media.get(path)
        return self._image_for(path, item.media_type if item else None, alt)

    def _image_for(self, path: str, media: str | None, alt: str | None) -> Image | None:
        name = self.image_names.get(path)
        if name is None:
            base = _slug(posixpath.splitext(posixpath.basename(path))[0]) or "image"
            ext = posixpath.splitext(path)[1].lower()[:8]
            name = f"{base}{ext}"
            used = set(self.image_names.values())
            k = 2
            while name in used:
                name = f"{base}-{k}{ext}"
                k += 1
            self.image_names[path] = name
            if self.image_dir is not None:
                data = self.book.read(path)
                if data is not None:
                    target = self.image_dir / "images" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
        return Image(ref=f"images/{name}", alt=alt, mime=media, provenance=Provenance(source=self.source, path=path))

    def _finish(self, all_locked: bool) -> None:
        doc = self.doc
        if all_locked:
            doc.blocks.append(
                Paragraph(
                    spans=[InlineSpan(text="This ebook is DRM-protected; its text cannot be extracted.")],
                    provenance=Provenance(source=self.source),
                )
            )
        removed = self.hidden + self.stats.total
        if removed:
            doc.warnings.append(
                Warning(
                    kind=W.REMOVED_HIDDEN_ELEMENTS,
                    severity="info",
                    message=f"Removed {removed} hidden elements or invisible characters.",
                    count=removed,
                    detail={
                        "hidden_elements": self.hidden,
                        "invisible_chars": self.stats.total,
                        "control": self.stats.control,
                        "invisible": self.stats.invisible,
                        "surrogates": self.stats.surrogates,
                    },
                )
            )
        if not any(not isinstance(b, Image) for b in doc.blocks):
            doc.warnings.append(Warning(kind=W.EXTRACTION_EMPTY, message="The EPUB contains no readable text."))


def _first_titles(toc: list[TocEntry]) -> dict[str, TocEntry]:
    out: dict[str, TocEntry] = {}
    for entry in toc:
        if entry.path and entry.path not in out:
            out[entry.path] = entry
    return out


def _flag(options: ConvertOptions, key: str, default: bool) -> bool:
    value = options.extra.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off")
    return bool(value)


_MAX_LISTED_FILES = 20


def _drm_message(locked: list[str]) -> str:
    """Name the skipped chapter files (the first few) so the reader knows which parts are missing."""
    if not locked:
        return "The EPUB carries DRM rights metadata and encrypted resources; no chapter was skipped."
    shown = ", ".join(locked[:5]) + (f" and {len(locked) - 5} more" if len(locked) > 5 else "")
    return f"{len(locked)} chapter(s) are DRM-encrypted and were skipped: {shown}."
