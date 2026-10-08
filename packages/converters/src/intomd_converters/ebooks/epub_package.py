"""ebooks.epub_package: read an EPUB container safely: zip limits, container.xml, the OPF package, the TOC
(EPUB3 nav or EPUB2 NCX), the page-list, and DRM markers in encryption.xml/rights.xml.

docs/spec/part2.md section 4c steps 1-3 and 7. All zip reads go through `archives.guard` (part1 8.2 applies to
EPUB containers too); all XML is parsed without entity resolution or network access.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import IO, Any
from urllib.parse import unquote, urlsplit

from lxml import etree  # type: ignore[import-untyped]

from intomd_converters.archives.backends import ArchiveOpenError, zip_declared_entries
from intomd_converters.archives.guard import (
    LISTING_HARD_CAP_FACTOR,
    BombError,
    Budget,
    EntryTooLarge,
    ratio_exceeded,
    read_member,
)
from intomd_converters.ebooks.xhtml import epub_types, local, parse_document

EPUB_MIME = "application/epub+zip"
FONT_OBFUSCATION = frozenset({"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"})
XHTML_TYPES = frozenset({"application/xhtml+xml", "text/html", "application/xml", "text/xml"})


def parse_xml(data: bytes) -> Any:
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, recover=True, remove_comments=True
    )
    try:
        return etree.fromstring(data, parser)
    except etree.XMLSyntaxError:
        return None


def resolve(base_file: str, href: str) -> tuple[str, str | None]:
    """Resolve `href` (relative to the zip path `base_file`) to (zip path, fragment)."""
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return "", None
    frag = unquote(parts.fragment) or None
    if not parts.path:
        return base_file, frag
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(base_file), unquote(parts.path)))
    return ("" if joined.startswith("..") else joined.lstrip("/")), frag


@dataclass(slots=True)
class ManifestItem:
    id: str
    path: str
    media_type: str
    properties: set[str]


@dataclass(slots=True)
class TocEntry:
    path: str
    fragment: str | None
    title: str
    depth: int


@dataclass(slots=True)
class Package:
    opf_path: str
    version: str
    title: str | None = None
    creators: list[str] = field(default_factory=list)
    contributors: list[tuple[str, str]] = field(default_factory=list)
    """(name, MARC relator role) for creators that are not authors (edt, ill, trl, ...)."""
    language: str | None = None
    identifier: str | None = None
    date: datetime | None = None
    publisher: str | None = None
    description: str | None = None
    manifest: dict[str, ManifestItem] = field(default_factory=dict)
    spine: list[tuple[ManifestItem, bool]] = field(default_factory=list)
    """(item, linear) in reading order."""
    ncx_id: str | None = None
    cover_id: str | None = None

    def by_path(self) -> dict[str, ManifestItem]:
        return {m.path: m for m in self.manifest.values()}

    def cover(self) -> ManifestItem | None:
        for m in self.manifest.values():
            if "cover-image" in m.properties:
                return m
        return self.manifest.get(self.cover_id or "")


class EpubContainer:
    """Guarded random-access reads from an EPUB zip."""

    def __init__(self, fp: IO[bytes], budget: Budget) -> None:
        limits = budget.limits
        declared = zip_declared_entries(fp)
        fp.seek(0)
        if declared is not None and declared > limits.max_entries * LISTING_HARD_CAP_FACTOR:
            raise BombError("max_entries", f"the EPUB declares {declared} entries")
        try:
            self.zf = zipfile.ZipFile(fp)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, EOFError) as e:
            raise ArchiveOpenError(str(e)) from e
        self.budget = budget
        self.infos = {i.filename: i for i in self.zf.infolist()}
        files = [i for i in self.infos.values() if not i.is_dir()]
        if len(files) > limits.max_entries:
            raise BombError("max_entries", f"the EPUB has {len(files)} entries")
        if sum(i.file_size for i in files) > limits.max_total:
            raise BombError("max_total", "the EPUB expands beyond the archive size limit")
        if any(ratio_exceeded(i.file_size, i.compress_size, limits.max_ratio) for i in files):
            raise BombError("ratio", f"an EPUB entry expands more than {limits.max_ratio}:1")
        self._cache: dict[str, bytes] = {}

    def names(self) -> list[str]:
        return list(self.infos)

    def has(self, name: str) -> bool:
        return name in self.infos

    def read(self, name: str) -> bytes | None:
        """Bytes of a member, or None when missing or unreadable. BombError propagates."""
        if name in self._cache:
            return self._cache[name]
        info = self.infos.get(name)
        if info is None or info.is_dir() or info.flag_bits & 0x1:
            return None
        try:
            with self.zf.open(info) as f:
                data = read_member(f, self.budget, compressed_size=info.compress_size, declared_size=info.file_size)
        except EntryTooLarge:
            return None
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error):
            return None
        self._cache[name] = data
        return data

    def mimetype_ok(self) -> bool:
        first = next(iter(self.infos), None)
        data = self.read("mimetype")
        return first == "mimetype" and data is not None and data.strip() == EPUB_MIME.encode()

    def close(self) -> None:
        self.zf.close()


def find_opf(book: EpubContainer) -> str | None:
    data = book.read("META-INF/container.xml")
    root = parse_xml(data) if data else None
    if root is not None:
        for el in root.iter():
            if local(el) == "rootfile":
                full = (el.get("full-path") or "").lstrip("/")
                media = el.get("media-type") or "application/oebps-package+xml"
                if full and media == "application/oebps-package+xml" and book.has(full):
                    return full
    return next((n for n in book.names() if n.lower().endswith(".opf")), None)


def encrypted_resources(book: EpubContainer) -> tuple[set[str], bool]:
    """Zip paths encrypted with a real cipher (font obfuscation excluded), and whether rights.xml exists."""
    out: set[str] = set()
    data = book.read("META-INF/encryption.xml")
    root = parse_xml(data) if data else None
    if root is not None:
        for enc in root.iter():
            if local(enc) != "EncryptedData".lower():
                continue
            algo = ""
            uri = ""
            for el in enc.iter():
                name = local(el)
                if name == "encryptionmethod":
                    algo = el.get("Algorithm") or ""
                elif name == "cipherreference":
                    uri = el.get("URI") or ""
            if uri and algo not in FONT_OBFUSCATION:
                out.add(resolve("", uri)[0])
    return out, book.has("META-INF/rights.xml")


def _text(el: Any) -> str:
    return " ".join("".join(el.itertext()).split())


_DATE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


def _date(raw: str) -> datetime | None:
    """dc:date as YYYY, YYYY-MM, or YYYY-MM-DD (anything after the date is ignored)."""
    m = _DATE.match(raw.strip())
    if m is None:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1), tzinfo=UTC)
    except ValueError:
        return None


def parse_package(book: EpubContainer, opf_path: str) -> Package | None:
    data = book.read(opf_path)
    root = parse_xml(data) if data else None
    if root is None:
        return None
    pkg = Package(opf_path=opf_path, version=root.get("version") or "")
    roles: dict[str, str] = {}
    for el in root.iter():
        if local(el) == "meta" and el.get("property") == "role" and (el.get("refines") or "").startswith("#"):
            roles[(el.get("refines") or "")[1:]] = _text(el)
    for el in root.iter():
        name = local(el)
        if name == "title" and pkg.title is None and _text(el):
            pkg.title = _text(el)
        elif name == "creator" and _text(el):
            role = (
                el.get("{http://www.idpf.org/2007/opf}role") or el.get("role") or roles.get(el.get("id") or "", "aut")
            )
            if role in ("aut", ""):
                pkg.creators.append(_text(el))
            else:
                pkg.contributors.append((_text(el), role))
        elif name == "language" and pkg.language is None and _text(el):
            pkg.language = _text(el)
        elif name == "identifier" and pkg.identifier is None and _text(el):
            pkg.identifier = _text(el)
        elif name == "date" and pkg.date is None:
            pkg.date = _date(_text(el))
        elif name == "publisher" and pkg.publisher is None and _text(el):
            pkg.publisher = _text(el)
        elif name == "description" and pkg.description is None and _text(el):
            pkg.description = _text(el)
        elif name == "meta" and el.get("name") == "cover":
            pkg.cover_id = el.get("content")
        elif name == "item":
            item_id, href = el.get("id") or "", el.get("href") or ""
            path, _frag = resolve(opf_path, href)
            if item_id and path:
                pkg.manifest[item_id] = ManifestItem(
                    id=item_id,
                    path=path,
                    media_type=(el.get("media-type") or "").lower(),
                    properties=set((el.get("properties") or "").split()),
                )
        elif name == "spine":
            pkg.ncx_id = el.get("toc")
    for el in root.iter():
        if local(el) == "itemref":
            item = pkg.manifest.get(el.get("idref") or "")
            if item is not None:
                pkg.spine.append((item, (el.get("linear") or "yes").lower() != "no"))
    return pkg


def parse_nav(book: EpubContainer, pkg: Package) -> tuple[list[TocEntry], dict[str, dict[str, str]]]:
    """TOC entries and page-list map {zip path: {fragment: page label}} from nav.xhtml, else the NCX."""
    nav = next((m for m in pkg.manifest.values() if "nav" in m.properties), None)
    if nav is not None:
        data = book.read(nav.path)
        root = parse_document(data) if data else None
        if root is not None:
            toc: list[TocEntry] = []
            pages: dict[str, dict[str, str]] = {}
            for el in root.iter():
                if local(el) != "nav":
                    continue
                kinds = epub_types(el) | set((el.get("role") or "").replace("doc-", "").split())
                if "toc" in kinds and not toc:
                    _nav_list(el, nav.path, 1, toc)
                elif "page-list" in kinds or "pagelist" in kinds:
                    for entry in _flat_links(el, nav.path):
                        if entry.fragment:
                            pages.setdefault(entry.path, {})[entry.fragment] = entry.title
            if toc:
                return toc, pages
    ncx = pkg.manifest.get(pkg.ncx_id or "") or next(
        (m for m in pkg.manifest.values() if m.media_type == "application/x-dtbncx+xml"), None
    )
    if ncx is None:
        return [], {}
    data = book.read(ncx.path)
    root = parse_xml(data) if data else None
    if root is None:
        return [], {}
    toc = []
    pages = {}
    for el in root:
        if local(el) == "navmap":
            _ncx_points(el, ncx.path, 1, toc)
        elif local(el) == "pagelist":
            for target in el.iter():
                if local(target) == "pagetarget":
                    label, src = _ncx_label_src(target)
                    path, frag = resolve(ncx.path, src)
                    if path and frag:
                        pages.setdefault(path, {})[frag] = label or target.get("value") or ""
    return toc, pages


def _nav_list(nav: Any, base: str, depth: int, out: list[TocEntry]) -> None:
    ol = next((c for c in nav.iter() if local(c) in ("ol", "ul")), None)
    if ol is None:
        return
    _nav_items(ol, base, depth, out)


def _nav_items(ol: Any, base: str, depth: int, out: list[TocEntry]) -> None:
    for li in ol:
        if local(li) != "li":
            continue
        link = next((c for c in li if local(c) in ("a", "span")), None)
        if link is not None:
            title = _text(link)
            path, frag = resolve(base, link.get("href") or "") if local(link) == "a" else ("", None)
            if title:
                out.append(TocEntry(path=path, fragment=frag, title=title, depth=depth))
        sub = next((c for c in li if local(c) in ("ol", "ul")), None)
        if sub is not None:
            _nav_items(sub, base, depth + 1, out)


def _flat_links(nav: Any, base: str) -> list[TocEntry]:
    out = []
    for a in nav.iter():
        if local(a) == "a" and a.get("href"):
            path, frag = resolve(base, a.get("href") or "")
            out.append(TocEntry(path=path, fragment=frag, title=_text(a), depth=1))
    return out


def _ncx_label_src(point: Any) -> tuple[str, str]:
    label = ""
    src = ""
    for c in point:
        if local(c) == "navlabel":
            label = _text(c)
        elif local(c) == "content":
            src = c.get("src") or ""
    return label, src


def _ncx_points(parent: Any, base: str, depth: int, out: list[TocEntry]) -> None:
    for point in parent:
        if local(point) != "navpoint":
            continue
        label, src = _ncx_label_src(point)
        path, frag = resolve(base, src)
        if label:
            out.append(TocEntry(path=path, fragment=frag, title=label, depth=depth))
        _ncx_points(point, base, depth + 1, out)
