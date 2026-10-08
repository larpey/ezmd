"""archives.archive: zip, tar (plain, gz, bz2, xz), single-file gz/bz2/xz, and 7z (optional extra).

docs/spec/part2.md section 12 step 27-28 and docs/spec/part1.md 8.2. The parent Document lists every member
(a directory tree as a ListBlock and a summary Table); each convertible member is converted through the
registry with `options.ctx.convert_child` and attached to `Document.children` with provenance
`source = "<outer>!<inner path>"` and `path = <inner path>`. Archives nested inside the archive are opened
in-process against the same Budget, so a nested archive counts against its parent's limits, up to
`max_depth` levels. Nothing is extracted to disk.
"""

from __future__ import annotations

import io
import mimetypes
import posixpath
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from ezmd.context import Limits
from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef, InputTooLarge
from ezmd.ir import (
    Block,
    Document,
    InlineSpan,
    ListBlock,
    ListItem,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
)
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.archives import sevenzip
from ezmd_converters.archives.backends import (
    ArchiveOpenError,
    Compression,
    Entry,
    ZipBackend,
    decompress_single,
    is_tar_stream,
    sniff,
    tar_entries,
)
from ezmd_converters.archives.guard import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_ENTRIES,
    DEFAULT_MAX_TOTAL,
    ArchiveLimits,
    BombError,
    Budget,
    EntryTooLarge,
    safe_member_path,
)

ZIP_MIMES = ("application/zip", "application/x-zip-compressed")
ARCHIVE_MIMES = (
    *ZIP_MIMES,
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
    "application/x-bzip2",
    "application/x-xz",
    "application/x-7z-compressed",
    "application/x-compressed-tar",
)
ARCHIVE_EXTS = (".zip", ".tar", ".tgz", ".gz", ".tbz", ".tbz2", ".bz2", ".txz", ".xz", ".7z")
DOCUMENT_ZIP_EXTS = frozenset(
    {
        ".epub",
        ".docx",
        ".docm",
        ".xlsx",
        ".xlsm",
        ".pptx",
        ".pptm",
        ".odt",
        ".ods",
        ".odp",
        ".pages",
        ".numbers",
        ".key",
        ".mxl",
        ".kmz",
        ".ipynb",
    }
)
"""Zip-based formats that have their own converters: never opened as a generic archive."""
_DOC_FIRST_MEMBERS = frozenset({b"mimetype", b"[Content_Types].xml"})

UNCONVERTED_EXAMPLES = 5
COUNT_KINDS = ("file", "directory", "link", "other", "rejected")
_COUNT_WORDS = {
    "file": ("file", "files"),
    "directory": ("directory", "directories"),
    "link": ("link", "links"),
    "other": ("other entry", "other entries"),
    "rejected": ("rejected", "rejected"),
}


@dataclass(slots=True)
class _Row:
    path: str
    size: int | None
    modified: str
    type: str
    status: str


@dataclass(slots=True)
class _State:
    label: str
    depth: int
    budget: Budget
    options: ConvertOptions
    password: str | None
    rows: list[_Row] = field(default_factory=list)
    tree_paths: list[tuple[str, bool]] = field(default_factory=list)
    archive_nodes: set[str] = field(default_factory=set)
    """Tree paths that are nested archives (their members are listed beneath them)."""
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNT_KINDS, 0))
    children: list[Document] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    encrypted: list[str] = field(default_factory=list)
    unconverted: list[str] = field(default_factory=list)
    depth_limited: list[str] = field(default_factory=list)
    bomb: str | None = None
    entries_capped: bool = False
    converted: int = 0
    nested_warnings: list[Warning] = field(default_factory=list)
    stats: CleanStats = field(default_factory=CleanStats)
    """Control and invisible characters removed from member names."""


class ArchiveConverter:
    id = "archives.archive"
    family = "archives"
    priority = 0
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ARCHIVE_MIMES
    limits = Limits(
        max_bytes=DEFAULT_MAX_TOTAL, max_entries=DEFAULT_MAX_ENTRIES, max_depth=DEFAULT_MAX_DEPTH, timeout_s=600.0
    )

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if mime is None:
            return 0.0
        name = ref.display.lower()
        ext = Path(name).suffix
        if mime in ZIP_MIMES:
            return 0.2 if ext in DOCUMENT_ZIP_EXTS or _looks_like_document_zip(ref) else 1.0
        if mime == "application/epub+zip":
            return 0.1  # fallback when the EPUB converter rejects a zip that detection called EPUB
        if mime in ARCHIVE_MIMES:
            if mime == "application/x-7z-compressed" and not sevenzip.available():
                return 0.5
            return 1.0
        if mime == "application/octet-stream" and name.endswith(ARCHIVE_EXTS):
            return 0.9
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        limits = ArchiveLimits.from_options(options)
        budget = Budget(limits)
        password = options.extra.get("specialized.archive_password")
        path = ref.path()
        size = path.stat().st_size
        with path.open("rb") as f:
            head = f.read(512)
        kind = sniff(head)
        if kind is None and is_tar_stream(lambda: path.open("rb"), "none"):
            kind = "tar"
        if kind is None:
            raise ConversionError(
                f"{ref.display} is not a recognized archive", user_message="This file is not a supported archive."
            )
        state = _State(
            label=ref.display,
            depth=1,
            budget=budget,
            options=options,
            password=password if isinstance(password, str) and password else None,
        )
        doc = self._archive(state, kind, lambda: path.open("rb"), size, name=ref.display)
        doc.metadata.mime = ref.detected.mime if ref.detected else None
        return doc.finalize()

    # ------------------------------------------------------------------

    def _archive(
        self, state: _State, kind: str, open_raw: Callable[[], IO[bytes]], size: int, *, name: str
    ) -> Document:
        meta = Metadata(
            title=posixpath.basename(name.split("!")[-1]) or name, source=state.label, source_type=SourceType.ARCHIVE
        )
        doc = Document(metadata=meta)
        meta.extra["archive_format"] = kind
        try:
            if kind == "zip":
                self._zip(state, open_raw)
            elif kind == "7z":
                if not sevenzip.available():
                    return _extra_required(doc, state.label)
                self._sevenzip(state, open_raw, size)
            else:
                compression: Compression = "none" if kind == "tar" else kind  # type: ignore[assignment]
                if kind == "tar" or is_tar_stream(open_raw, compression):
                    meta.extra["archive_format"] = "tar" if kind == "tar" else f"tar.{kind}"
                    self._run(state, tar_entries(open_raw, compression, state.budget, size), stream=True)
                else:
                    self._single(state, open_raw, compression, size, name)
        except ArchiveOpenError as e:
            if not state.rows and not state.tree_paths:
                raise ConversionError(
                    f"{state.label}: {e}", user_message="The archive is corrupt or truncated and could not be read."
                ) from e
            doc.warnings.append(
                Warning(
                    kind=WarningKind.ARCHIVE_TRUNCATED,
                    message="The archive is corrupt after some entries; only the readable part was listed.",
                    detail={"reason": "corrupt"},
                )
            )
            doc.truncated = True
        except BombError as e:
            state.bomb = state.bomb or e.reason
        self._assemble(doc, state, size)
        return doc

    def _zip(self, state: _State, open_raw: Callable[[], IO[bytes]]) -> None:
        fp = open_raw()
        try:
            backend = ZipBackend(fp, state.budget, state.password)
        except BombError:
            fp.close()
            raise
        except ArchiveOpenError:
            fp.close()
            raise
        try:
            if backend.refused:
                state.bomb = backend.refused
            self._run(state, backend.entries(), stream=False)
        finally:
            backend.close()
            fp.close()

    def _sevenzip(self, state: _State, open_raw: Callable[[], IO[bytes]], size: int) -> None:
        fp = open_raw()
        try:
            entries, encrypted, bomb = sevenzip.sevenzip_entries(fp, state.budget, size, state.password)
        finally:
            fp.close()
        if bomb:
            state.bomb = bomb
        if encrypted and not entries:
            state.encrypted.append("(archive headers)")
        self._run(state, iter(entries), stream=False)

    def _single(
        self, state: _State, open_raw: Callable[[], IO[bytes]], compression: Compression, size: int, name: str
    ) -> None:
        inner = posixpath.basename(name.split("!")[-1])
        for suffix in (".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz"):
            if inner.lower().endswith(suffix):
                inner = inner[: -len(suffix)] + (".tar" if suffix.startswith(".t") and len(suffix) > 3 else "")
                break
        inner = inner or "content"

        def read() -> bytes:
            return decompress_single(open_raw, compression, state.budget, size)

        entry = Entry(name=inner, kind="file", size=None, compressed=size, modified=None, read=read)
        self._run(state, iter([entry]), stream=False)

    # ------------------------------------------------------------------

    def _run(self, state: _State, entries: Iterator[Entry], *, stream: bool) -> None:
        ctx = state.options.ctx
        for n, entry in enumerate(entries):
            ctx.check_deadline()
            if n % 50 == 0:
                ctx.progress("archive", None, f"{state.label}: entry {n + 1}")
            if not state.budget.take_entry():
                state.entries_capped = True
                break
            try:
                self._entry(state, entry)
            except BombError as e:
                state.bomb = state.bomb or e.reason
                if stream:
                    break

    def _entry(self, state: _State, entry: Entry) -> None:
        entry.name = clean_text(entry.name, state.stats)
        path, reason = safe_member_path(entry.name)
        shown = path or entry.name
        modified = entry.modified.strftime("%Y-%m-%d %H:%M") if entry.modified else ""
        if reason in ("absolute", "traversal"):
            state.counts["rejected"] += 1
            state.rejected.append(entry.name)
            state.rows.append(_Row(entry.name, entry.size, modified, entry.kind, f"rejected ({reason} path)"))
            return
        if path is None:
            return
        if entry.kind == "dir":
            state.counts["directory"] += 1
            state.tree_paths.append((path, True))
            return
        state.tree_paths.append((path, False))
        if entry.kind in ("symlink", "hardlink"):
            state.counts["link"] += 1
            state.skipped.append(path)
            target = clean_text(entry.link_target) if entry.link_target else "unknown target"
            status = f"skipped ({entry.kind} to {target}; links are never followed)"
            state.rows.append(_Row(path, entry.size, modified, entry.kind, status))
            return
        if entry.kind != "file":
            state.counts["other"] += 1
            state.skipped.append(path)
            state.rows.append(_Row(path, entry.size, modified, entry.kind, f"skipped ({entry.kind})"))
            return
        state.counts["file"] += 1
        row = _Row(shown, entry.size, modified, _guess_type(path), "listed only")
        state.rows.append(row)
        if entry.encrypted and not state.password:
            state.encrypted.append(path)
            row.status = "encrypted"
            return
        if state.bomb or state.budget.bombed or entry.read is None:
            row.status = "not extracted"
            return
        try:
            data = entry.read()
        except EntryTooLarge:
            state.skipped.append(path)
            row.status = "skipped (too large)"
            return
        except BombError:
            row.status = "not extracted"
            raise
        except ArchiveOpenError:
            state.unconverted.append(path)
            row.status = "failed (unreadable)"
            return
        row.size = len(data)
        self._member(state, path, data, row)

    def _member(self, state: _State, path: str, data: bytes, row: _Row) -> None:
        label = f"{state.label}!{path}"
        nested = _nested_kind(path, data)
        if nested is not None:
            row.type = "archive"
            if state.depth >= state.budget.limits.max_depth:
                state.depth_limited.append(path)
                row.status = "not opened (nesting limit)"
                return
            child_state = _State(
                label=label,
                depth=state.depth + 1,
                budget=state.budget,
                options=state.options,
                password=state.password,
            )
            try:
                child = self._archive(child_state, nested, lambda: io.BytesIO(data), len(data), name=path)
            except ConversionError:
                state.unconverted.append(path)
                row.status = "failed (corrupt archive)"
                return
            child.converter_id = self.id
            state.archive_nodes.add(path)
            state.archive_nodes.update(f"{path}/{p}" for p in child_state.archive_nodes)
            state.tree_paths.extend((f"{path}/{p}", is_dir) for p, is_dir in child_state.tree_paths)
            _set_child_provenance(child, label, path)
            child.finalize()
            state.children.append(child)
            state.nested_warnings.extend(
                w
                for w in child.warnings
                if str(w.kind).startswith("archive_") or w.kind == WarningKind.ATTACHMENT_UNCONVERTED
            )
            state.converted += 1
            row.status = "converted (archive)"
            if child_state.bomb:
                state.bomb = state.bomb or child_state.bomb
            return
        try:
            ref = InputRef.from_bytes(data, filename=label, max_bytes=max(len(data), 1))
        except InputTooLarge:
            state.skipped.append(path)
            row.status = "skipped (too large)"
            return
        try:
            result = state.options.ctx.convert_child(ref, label=label)
        except ConversionError:
            state.unconverted.append(path)
            row.status = "not converted"
            return
        finally:
            ref.cleanup()
        child = result.document
        if result.input_ref.mime:
            row.type = result.input_ref.mime
        if any(w.kind == WarningKind.ATTACHMENT_SKIPPED for w in child.warnings) and not child.blocks:
            row.status = "skipped (depth)"
            state.unconverted.append(path)
            return
        child.warnings = [*result.warnings, *child.warnings]
        child.converter_id = result.converter_id
        _set_child_provenance(child, label, path)
        child.finalize()
        state.children.append(child)
        state.converted += 1
        row.status = f"converted ({result.converter_id})" if result.converter_id else "converted"

    # ------------------------------------------------------------------

    def _assemble(self, doc: Document, state: _State, size: int) -> None:
        source = state.label
        counts = state.counts
        total = sum(counts.values())
        meta = doc.metadata
        meta.extra.update(
            {
                "archive_entries": total,
                "archive_files": counts["file"],
                "archive_directories": counts["directory"],
                "archive_links": counts["link"],
                "archive_other": counts["other"],
                "archive_rejected": counts["rejected"],
                "archive_converted": state.converted,
                "archive_bytes_extracted": state.budget.used_bytes,
                "archive_compressed_bytes": size,
            }
        )
        parts = ", ".join(_plural(counts[k], *_COUNT_WORDS[k]) for k in COUNT_KINDS)
        summary = f"Archive {meta.title}: {_plural(total, 'entry', 'entries')} ({parts}); {state.converted} converted."
        if counts["link"]:
            summary += " Links are listed but never followed, even when they point inside the archive."
        blocks: list[Block] = [Paragraph(spans=[InlineSpan(text=summary)], provenance=Provenance(source=source))]
        tree = _tree(state.tree_paths, state.archive_nodes)
        if tree:
            blocks.append(ListBlock(items=tree, provenance=Provenance(source=source)))
        if state.rows:
            blocks.append(_table(state.rows, source))
        doc.blocks.extend(blocks)
        doc.children.extend(state.children)
        if any(c.truncated for c in state.children if c.converter_id == self.id):
            doc.truncated = True
        self._warn(doc, state)

    def _warn(self, doc: Document, state: _State) -> None:
        w = doc.warnings
        if state.bomb:
            w.append(
                Warning(
                    kind=WarningKind.ARCHIVE_BOMB_SUSPECTED,
                    message=(
                        "The archive expands beyond the safe limits; extraction stopped and the remaining "
                        "entries are listed only."
                    ),
                    detail={
                        "reason": state.bomb,
                        "max_total": state.budget.limits.max_total,
                        "max_ratio": state.budget.limits.max_ratio,
                        "bytes_extracted": state.budget.used_bytes,
                    },
                )
            )
        if state.entries_capped:
            doc.truncated = True
            w.append(
                Warning(
                    kind=WarningKind.ARCHIVE_TRUNCATED,
                    message=f"Only the first {state.budget.limits.max_entries} archive entries were processed.",
                    detail={"reason": "max_entries", "max_entries": state.budget.limits.max_entries},
                )
            )
        if state.depth_limited:
            doc.truncated = True
            w.append(
                Warning(
                    kind=WarningKind.ARCHIVE_TRUNCATED,
                    message=(
                        f"{len(state.depth_limited)} nested archive(s) beyond depth "
                        f"{state.budget.limits.max_depth} were not opened."
                    ),
                    count=len(state.depth_limited),
                    detail={"reason": "max_depth", "examples": _examples(state.depth_limited)},
                )
            )
        _grouped(w, WarningKind.ARCHIVE_PATH_REJECTED, state.rejected, "entry with an unsafe path was rejected")
        _grouped(
            w,
            WarningKind.ARCHIVE_ENTRY_SKIPPED,
            state.skipped,
            "entry (link, device, or oversized) was skipped (links are never followed, even inside)",
        )
        _grouped(w, WarningKind.ARCHIVE_ENCRYPTED, state.encrypted, "encrypted entry was listed but not extracted")
        _grouped(w, WarningKind.ATTACHMENT_UNCONVERTED, state.unconverted, "entry could not be converted")
        if state.stats.total:
            w.append(
                Warning(
                    kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                    severity="info",
                    message=f"Removed {state.stats.total} control or invisible characters from member names.",
                    count=state.stats.total,
                    detail={
                        "invisible_chars": state.stats.total,
                        "control": state.stats.control,
                        "invisible": state.stats.invisible,
                        "surrogates": state.stats.surrogates,
                    },
                )
            )
        for nw in state.nested_warnings:
            if nw.kind == WarningKind.ARCHIVE_BOMB_SUSPECTED and state.bomb:
                continue
            w.append(nw.model_copy(update={"detail": {**nw.detail, "archive": nw.detail.get("archive", "nested")}}))


def _grouped(out: list[Warning], kind: WarningKind, names: list[str], what: str) -> None:
    if not names:
        return
    n = len(names)
    out.append(
        Warning(
            kind=kind,
            message=f"{n} {what if n == 1 else what.replace('entry', 'entries', 1).replace(' was ', ' were ')}: "
            f"{_examples(names)}.",
            count=n,
            detail={"examples": _examples(names)},
        )
    )


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _examples(names: list[str]) -> str:
    shown = ", ".join(names[:UNCONVERTED_EXAMPLES])
    return shown + (f", and {len(names) - UNCONVERTED_EXAMPLES} more" if len(names) > UNCONVERTED_EXAMPLES else "")


def _extra_required(doc: Document, source: str) -> Document:
    doc.blocks.append(
        Paragraph(
            spans=[
                InlineSpan(
                    text="This is a 7z archive. Reading 7z needs the optional `7z` extra "
                    "(pip install 'ezmd-converters[7z]'), which is not installed."
                )
            ],
            provenance=Provenance(source=source),
        )
    )
    doc.warnings.append(
        Warning(
            kind=WarningKind.EXTRA_REQUIRED,
            message="7z archives need the optional 7z extra (py7zr), which is not installed.",
            detail={"extra": "7z"},
        )
    )
    return doc


def first_member_name(head: bytes) -> bytes:
    """Name of the first zip member from its local file header (empty when `head` is not a zip)."""
    if len(head) < 30 or not head.startswith(b"PK\x03\x04"):
        return b""
    n = int.from_bytes(head[26:28], "little")
    return head[30 : 30 + n]


def _is_document_zip(head: bytes) -> bool:
    """EPUB stores `mimetype` first; OOXML writers put `[Content_Types].xml` first."""
    return first_member_name(head) in _DOC_FIRST_MEMBERS


def _looks_like_document_zip(ref: InputRef) -> bool:
    if not ref.has_body:
        return False
    try:
        head = ref.head(128)
    except (OSError, InputTooLarge):
        return False
    return _is_document_zip(head)


def _nested_kind(path: str, data: bytes) -> str | None:
    """Archive kind when a member should be opened in-process as a nested archive."""
    ext = posixpath.splitext(path.lower())[1]
    if ext in DOCUMENT_ZIP_EXTS:
        return None
    kind = sniff(data[:512])
    if kind is None:
        return None
    if kind == "zip" and _is_document_zip(data[:128]):
        return None
    return kind


def _guess_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path, strict=False)
    return mime or "unknown"


def _set_child_provenance(child: Document, label: str, path: str) -> None:
    for b in child.blocks:
        prov = b.provenance
        prov.source = label
        prov.path = path if prov.path is None else f"{path}!{prov.path}"
    child.metadata.source = label


def _tree(paths: list[tuple[str, bool]], archive_nodes: set[str]) -> list[ListItem]:
    """Nested list of the tree. Members of nested archives hang under the archive's own (slashless) node."""
    root: dict[str, object] = {}
    for p, is_dir in paths:
        node = root
        parts = p.split("/")
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            container = not last and "/".join(parts[: i + 1]) not in archive_nodes
            key = part + ("/" if (container or (last and is_dir)) else "")
            nxt = node.setdefault(key, {})
            assert isinstance(nxt, dict)
            node = nxt
    return _items(root)


def _items(node: dict[str, object]) -> list[ListItem]:
    out: list[ListItem] = []
    for name, sub in node.items():
        assert isinstance(sub, dict)
        out.append(ListItem(spans=[InlineSpan(text=name)], children=_items(sub)))
    return out


def _table(rows: list[_Row], source: str) -> Table:
    header = ["Path", "Size", "Modified", "Type", "Converted"]
    cells = [TableCell(spans=[InlineSpan(text=h)], row=0, col=c, is_header=True) for c, h in enumerate(header)]
    for r, row in enumerate(rows, start=1):
        values = [row.path, "" if row.size is None else str(row.size), row.modified, row.type, row.status]
        cells.extend(TableCell(spans=[InlineSpan(text=v)] if v else [], row=r, col=c) for c, v in enumerate(values))
    return Table(
        cells=cells,
        n_rows=len(rows) + 1,
        n_cols=len(header),
        header_rows=1,
        column_types=["text", "int", "date", "text", "text"],
        provenance=Provenance(source=source),
    )
