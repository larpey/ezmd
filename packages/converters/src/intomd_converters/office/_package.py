"""Zip-container validation and sanitation for OOXML and ODF packages (docs/spec/part1.md 8.2).

Before any parser sees a package:

- archive limits: at most 10,000 entries, total uncompressed size under `INTOMD_ARCHIVE_MAX_BYTES`
  (default 500 MB), no entry above a 100:1 compression ratio (entries over 1 MB), no encrypted entries;
  members with absolute paths or `..` components are ignored (nothing is ever extracted to disk).
- active content is removed and recorded as `removed_script_or_macro`: `vbaProject.bin`, `vbaData.xml`,
  ActiveX parts, embedded OLE `.bin` objects, and external relationships of type oleObject, attachedTemplate,
  frame and subDocument, plus hyperlinks with a `file:` or UNC target. Relationships pointing at removed
  parts are dropped too so engines never chase a dangling part.
- XML is parsed with lxml with entity resolution, network access, DTD loading, and huge trees disabled;
  any part that declares a DOCTYPE is refused (OOXML and ODF never need one).
"""

from __future__ import annotations

import io
import os
import posixpath
import zipfile
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[import-untyped]

from intomd.ir import Warning, WarningKind
from intomd.registry import ConversionError

MAX_ENTRIES = 10_000
MAX_RATIO = 100
RATIO_MIN_BYTES = 1024 * 1024
DEFAULT_MAX_TOTAL = 500 * 1024 * 1024

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_DROP_EXTERNAL_TYPES = ("/oleobject", "/attachedtemplate", "/frame", "/subdocument")

_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    huge_tree=False,
    load_dtd=False,
    dtd_validation=False,
    remove_comments=True,
    remove_pis=True,
)
_DOCTYPE_MARKERS = (b"<!DOCTYPE", b"<!ENTITY", "<!DOCTYPE".encode("utf-16-le"), "<!DOCTYPE".encode("utf-16-be"))


def _max_total() -> int:
    raw = os.environ.get("INTOMD_ARCHIVE_MAX_BYTES", "")
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_MAX_TOTAL
    return n if n > 0 else DEFAULT_MAX_TOTAL


def parse_xml(data: bytes, name: str = "xml") -> etree._Element:
    """Parse untrusted XML safely. Raises ConversionError for DTDs or malformed XML."""
    if any(m in data for m in _DOCTYPE_MARKERS):
        raise ConversionError(
            f"{name} declares a DOCTYPE or entities",
            user_message="The file contains XML entity declarations, which are refused for safety.",
            retryable_with_fallback=False,
        )
    try:
        return etree.fromstring(data, parser=_PARSER)
    except etree.XMLSyntaxError as e:
        raise ConversionError(f"{name} is not well-formed XML: {e}", user_message="The file is damaged.") from e


@dataclass(frozen=True, slots=True)
class Rel:
    id: str
    type: str
    target: str
    """Resolved package part name for internal targets, or the raw URL for external ones."""
    external: bool

    @property
    def kind(self) -> str:
        return self.type.rsplit("/", 1)[-1].lower()


@dataclass(slots=True)
class Removed:
    macros: list[str] = field(default_factory=list)
    activex: list[str] = field(default_factory=list)
    ole: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.macros) + len(self.activex) + len(self.ole) + len(self.external)


def _is_unsafe_name(name: str) -> bool:
    if name.startswith(("/", "\\")) or ":" in name.split("/", 1)[0]:
        return True
    return any(p == ".." for p in name.replace("\\", "/").split("/"))


def _classify_removed(name: str) -> str | None:
    low = name.lower()
    base = posixpath.basename(low)
    if base in ("vbaproject.bin", "vbadata.xml") or base.startswith("vbaproject"):
        return "macros"
    if low.startswith(("basic/", "scripts/")):  # ODF Basic and script macros
        return "macros"
    if "/activex/" in low or low.startswith("activex/"):
        return "activex"
    if "/embeddings/" in low and low.endswith(".bin"):
        return "ole"
    return None


class OfficePackage:
    """A validated, sanitized view of a zip-based Office package. Members are read on demand, bounded by the
    sizes the central directory declares (zipfile stops decompressing at the declared size)."""

    def __init__(self, data: bytes, *, what: str = "Office") -> None:
        if data[:8] == bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]):
            raise ConversionError(
                f"{what} input is an OLE2 container (encrypted OOXML or legacy binary)",
                user_message="This file is password-protected or in a legacy binary format; save it as a "
                "regular .docx/.xlsx/.pptx without a password and convert again.",
                retryable_with_fallback=True,
            )
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, ValueError) as e:
            raise ConversionError(f"{what} input is not a zip package: {e}", user_message="The file is damaged.") from e
        self.what = what
        self.removed = Removed()
        self.members: dict[str, zipfile.ZipInfo] = {}
        self._removed_parts: set[str] = set()
        self._check_limits()
        self._rels_cache: dict[str, dict[str, Rel]] = {}
        self._scan_rels()

    def _scan_rels(self) -> None:
        """Parse every relationship part once so dropped external targets are counted even in parts no
        converter reads (settings.xml.rels holds attachedTemplate)."""
        for name in list(self.members):
            d, b = posixpath.split(name)
            if not b.endswith(".rels") or posixpath.basename(d) != "_rels":
                continue
            owner_dir = posixpath.dirname(d)
            part = posixpath.join(owner_dir, b[: -len(".rels")]) if b != ".rels" else ""
            self.rels(part)

    # -- validation -----------------------------------------------------------------------------------------

    def _bomb(self, why: str) -> ConversionError:
        return ConversionError(
            f"{self.what} package rejected: {why}",
            user_message=f"The file was rejected by the archive safety limits ({why}).",
            retryable_with_fallback=False,
        )

    def _check_limits(self) -> None:
        infos = self._zip.infolist()
        if len(infos) > MAX_ENTRIES:
            raise self._bomb(f"{len(infos)} entries exceed {MAX_ENTRIES}")
        total = 0
        limit = _max_total()
        for info in infos:
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise self._bomb(f"encrypted member {info.filename!r}")
            total += info.file_size
            if total > limit:
                raise self._bomb(f"uncompressed size exceeds {limit} bytes")
            if info.file_size > RATIO_MIN_BYTES and info.file_size > MAX_RATIO * max(info.compress_size, 1):
                raise self._bomb(f"member {info.filename!r} exceeds the {MAX_RATIO}:1 compression ratio")
            if _is_unsafe_name(info.filename):
                continue
            kind = _classify_removed(info.filename)
            if kind is not None:
                getattr(self.removed, kind).append(info.filename)
                self._removed_parts.add(info.filename)
                continue
            self.members[info.filename] = info

    # -- access ---------------------------------------------------------------------------------------------

    def has(self, name: str) -> bool:
        return name in self.members

    def names(self) -> list[str]:
        return list(self.members)

    def read(self, name: str) -> bytes:
        info = self.members.get(name)
        if info is None:
            raise KeyError(name)
        try:
            with self._zip.open(info) as f:
                data = f.read(info.file_size + 1)
        except (zipfile.BadZipFile, OSError, EOFError, ValueError) as e:  # CRC errors, truncated members
            raise ConversionError(f"cannot read {name}: {e}", user_message="The file is damaged.") from e
        if len(data) > info.file_size:
            raise self._bomb(f"member {name!r} is larger than declared")
        return data

    def xml(self, name: str) -> etree._Element | None:
        if name not in self.members:
            return None
        return parse_xml(self.read(name), name)

    def rels(self, part: str) -> dict[str, Rel]:
        """Relationships of `part` (`""` for the package root), with dangerous ones removed."""
        if part in self._rels_cache:
            return self._rels_cache[part]
        d, b = posixpath.split(part)
        rels_name = posixpath.join(d, "_rels", b + ".rels") if part else "_rels/.rels"
        out: dict[str, Rel] = {}
        root = self.xml(rels_name)
        if root is not None:
            for el in root.iter(f"{{{REL_NS}}}Relationship"):
                rel = self._rel(el, d)
                if rel is not None:
                    out[rel.id] = rel
        self._rels_cache[part] = out
        return out

    def _rel(self, el: etree._Element, base_dir: str) -> Rel | None:
        rid = el.get("Id") or ""
        rtype = el.get("Type") or ""
        target = el.get("Target") or ""
        external = (el.get("TargetMode") or "").lower() == "external"
        low_type = rtype.lower()
        if external:
            low_target = target.strip().lower()
            dangerous_type = low_type.endswith(_DROP_EXTERNAL_TYPES)
            local_link = low_type.endswith("/hyperlink") and (
                low_target.startswith("file:") or low_target.startswith("\\\\") or low_target.startswith("//")
            )
            if dangerous_type or local_link:
                key = f"{base_dir}/{rid}:{low_type.rsplit('/', 1)[-1]}"
                if key not in self.removed.external:
                    self.removed.external.append(key)
                return None
            return Rel(rid, rtype, target, True)
        resolved = (
            target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base_dir, target))
        )
        if low_type.endswith("/vbaproject") or resolved in self._removed_parts:
            return None
        return Rel(rid, rtype, resolved, False)

    # -- outputs --------------------------------------------------------------------------------------------

    def warnings(self) -> list[Warning]:
        r = self.removed
        if not r.total:
            return []
        parts = []
        if r.macros:
            parts.append("macros")
        if r.activex:
            parts.append("ActiveX controls")
        if r.ole:
            parts.append("embedded OLE objects")
        if r.external:
            parts.append("external relationships")
        return [
            Warning(
                kind=WarningKind.REMOVED_SCRIPT_OR_MACRO,
                message=f"Removed {', '.join(parts)} before parsing; nothing was executed.",
                count=r.total,
                detail={
                    "macros": len(r.macros),
                    "activex": len(r.activex),
                    "ole_objects": len(r.ole),
                    "external_relationships": len(r.external),
                },
            )
        ]

    def sanitized_bytes(self) -> bytes:
        """A rewritten zip without removed parts and with filtered .rels and [Content_Types].xml, for engines
        that open the package themselves (openpyxl). Every XML part is DOCTYPE-checked on the way."""
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name in self.members:
                data = self.read(name)
                low = name.lower()
                if low.endswith((".xml", ".rels", ".vml")) and any(m in data for m in _DOCTYPE_MARKERS):
                    parse_xml(data, name)  # raises
                if low.endswith(".rels"):
                    data = self._filtered_rels(name, data)
                elif name == "[Content_Types].xml":
                    data = self._filtered_content_types(data)
                z.writestr(name, data)
        return out.getvalue()

    def _filtered_rels(self, name: str, data: bytes) -> bytes:
        root = parse_xml(data, name)
        d = posixpath.dirname(posixpath.dirname(name))
        for el in list(root):
            if el.tag == f"{{{REL_NS}}}Relationship" and self._rel(el, d) is None:
                root.remove(el)
        return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))

    def _filtered_content_types(self, data: bytes) -> bytes:
        root = parse_xml(data, "[Content_Types].xml")
        for el in list(root):
            part = (el.get("PartName") or "").lstrip("/")
            if el.tag == f"{{{CT_NS}}}Override" and part in self._removed_parts:
                root.remove(el)
        return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))


def text_of(el: etree._Element | None) -> str:
    """All descendant text of an element, or "" for None."""
    if el is None:
        return ""
    return "".join(el.itertext())
