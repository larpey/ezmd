"""code.repo_pack: a repository archive packed into one Markdown document (docs/spec/part2.md 8c steps 1-10).

Inputs: a zip or tar(.gz) of a repository (selected with `--converter code.repo_pack`, or automatically for
`*.repo.zip` / `*.repo.tar.gz` names and for GitHub codeload tarballs), or a github.com repository URL without a
body, for which the converter raises `FetchRequired` with the codeload tarball URL. Options (`--opt extra.<key>`):
`signatures_only`, `token_budget`, `max_file_bytes` (512 KB), `respect_gitignore` (true), `include` / `exclude`
(comma-separated globs), `tests_first` (false), `subpath`.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from pathlib import PurePosixPath

from ezmd.context import Limits
from ezmd.inputs import FetchRequired, InputRef
from ezmd.ir import Document, Metadata, SourceType, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.code.archive import ArchiveLimits, Member, ReadResult, read_archive
from ezmd_converters.code.budget import PackFile, apply_budget
from ezmd_converters.code.collect import Collected, FileEntry, collect
from ezmd_converters.code.common import count_tokens, opt_bool, opt_int, opt_str, secret_warning
from ezmd_converters.code.emit import PackInfo, emit_pack
from ezmd_converters.code.github import RepoUrl, is_codeload_url, parse_repo_url
from ezmd_converters.code.languages import is_code_name
from ezmd_converters.code.secrets import Redactions, redact
from ezmd_converters.code.signatures import signatures

DEFAULT_MAX_FILE_BYTES = 512 * 1024
_REPO_SUFFIXES = (".repo.zip", ".repo.tar.gz", ".repo.tgz", ".repo.tar")
_ARCHIVE_MIMES = frozenset(
    {"application/zip", "application/gzip", "application/x-gzip", "application/x-tar", "application/x-compressed-tar"}
)
_MANIFESTS = ("package.json", "pyproject.toml", "cargo.toml", "go.mod")
_LICENSE = re.compile(r"^(?:license|licence|copying|unlicense)(?:[.-].*)?$", re.IGNORECASE)


class RepoPackConverter:
    id = "code.repo_pack"
    family = "code"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = (*sorted(_ARCHIVE_MIMES), "text/x-uri")
    limits = Limits(max_entries=10_000, max_depth=3)

    def can_handle(self, ref: InputRef) -> float:
        if not ref.has_body:
            return 0.7 if parse_repo_url(ref.url or ref.display) else 0.0
        mime = ref.detected.mime if ref.detected else ""
        if is_codeload_url(ref.url) and mime in _ARCHIVE_MIMES:
            return 1.0
        if ref.display.lower().endswith(_REPO_SUFFIXES) and mime in _ARCHIVE_MIMES:
            return 0.95
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        if not ref.has_body:
            repo = parse_repo_url(ref.url or ref.display)
            if repo is None:
                raise ConversionError(
                    f"not a repository URL: {ref.display}", user_message="This URL is not a GitHub repository."
                )
            raise FetchRequired(repo.tarball_url, residential=False, reason="repository tarball needed")
        max_file = opt_int(options, "max_file_bytes", DEFAULT_MAX_FILE_BYTES) or DEFAULT_MAX_FILE_BYTES
        options.ctx.progress("read", None, "reading archive")
        archive = read_archive(ref.path(), ArchiveLimits.from_env(max_file))
        url_repo = is_codeload_url(ref.url) or parse_repo_url(ref.url)
        subpath = (opt_str(options, "subpath") or (url_repo.subpath if url_repo else None) or "").strip("/")
        members = _restrict(archive.members, subpath) if subpath else archive.members
        coll = collect(members, dict(options.extra), max_file, within=subpath)
        options.ctx.check_deadline()
        doc, found = _build(ref, options, archive, coll, url_repo, subpath)
        warnings = _warnings(archive, coll, found)
        doc.warnings.extend(warnings)
        return doc.finalize()


def _restrict(members: list[Member], subpath: str) -> list[Member]:
    prefix = subpath + "/"
    out: list[Member] = []
    for m in members:
        parent = str(PurePosixPath(m.path).parent)
        ancestor_ignore = PurePosixPath(m.path).name in (".gitignore", ".ezmdignore") and (
            parent == "." or prefix.startswith(parent + "/")
        )
        if m.path.startswith(prefix) or ancestor_ignore:
            out.append(m)
    return out


def _repo_name(ref: InputRef, archive: ReadResult, url_repo: RepoUrl | None) -> str:
    if url_repo is not None:
        return url_repo.display
    if archive.root_name:
        return archive.root_name
    name = PurePosixPath(ref.display.replace("\\", "/")).name
    for suffix in (*_REPO_SUFFIXES, ".tar.gz", ".tgz", ".zip", ".tar"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)] or name
    return name


def _order_key(f: FileEntry, tests_first: bool) -> tuple[int, int, str]:
    name = PurePosixPath(f.path).name.lower()
    top = f.path.split("/", 1)[0].lower()
    if f.depth == 0 and name.startswith("readme"):
        group = 0
    elif f.depth == 0 and not is_code_name(f.path):
        group = 1
    elif f.is_test:
        group = 2 if tests_first else 5
    elif top in ("docs", "doc") and f.depth > 0:
        group = 4
    else:
        group = 3
    return group, f.depth, f.path


def _scan(coll: Collected, options: ConvertOptions) -> tuple[list[PackFile], Redactions]:
    found = Redactions()
    tests_first = opt_bool(options, "tests_first", False)
    compress_all = opt_bool(options, "signatures_only", False) or opt_bool(options, "compress", False)
    packed = sorted(coll.packed, key=lambda f: _order_key(f, tests_first))
    out: list[PackFile] = []
    for i, f in enumerate(packed):
        options.ctx.check_deadline()
        if i % 50 == 0:
            options.ctx.progress("pack", i / max(1, len(packed)), f.path)
        text, hits = redact(f.text, f.path)
        found.merge(hits)
        compressed = compress_all and not f.lockfile and f.language is not None
        if compressed:
            text = signatures(text, f.language)
        out.append(
            PackFile(
                path=f.path,
                size=f.size,
                text=text,
                language=f.language,
                lines=f.lines,
                tokens=count_tokens(text) + (count_tokens(f.note) if f.note else 0),
                depth=f.depth,
                is_test=f.is_test,
                disposable=f.lockfile or f.generated or f.minified,
                note=f.note,
                compressed=compressed,
            )
        )
    return out, found


def _build(
    ref: InputRef,
    options: ConvertOptions,
    archive: ReadResult,
    coll: Collected,
    url_repo: RepoUrl | None,
    subpath: str,
) -> tuple[Document, Redactions]:
    files, found = _scan(coll, options)
    name = _repo_name(ref, archive, url_repo)
    info = PackInfo(
        source=ref.display,
        name=name,
        ref=url_repo.ref if url_repo and url_repo.ref != "HEAD" else None,
        commit=archive.commit,
        subpath=subpath or None,
        root_label=PurePosixPath(name).name,
    )
    title = f"{name} at {info.ref}" if info.ref else name
    meta = Metadata(source=ref.display, source_type=SourceType.REPO, title=title, mime=_mime(ref))
    doc = Document(metadata=meta)
    tree_overhead_files = [(f.path, f.excluded or "") for f in coll.files]
    budget = opt_int(options, "token_budget", None)
    actions: list[str] = []
    if budget is not None:
        from ezmd_converters.code.tree import render_tree

        overhead = count_tokens(render_tree(info.root_label, tree_overhead_files, coll.excluded_dirs))
        actions = apply_budget(files, budget, overhead, count_tokens)
    emit_pack(doc, info, coll, files)
    _metadata(meta, coll, files, info, actions)
    if actions:
        doc.warnings.append(
            Warning(
                kind=WarningKind.TOKEN_BUDGET_APPLIED,
                message=f"Applied the {budget:,}-token budget: " + "; ".join(actions) + ".",
                count=len(actions),
                detail={"budget": budget or 0, "actions": " | ".join(actions)},
            )
        )
    return doc, _live_redactions(found, files)


def _live_redactions(found: Redactions, files: list[PackFile]) -> Redactions:
    """Only report redactions in files that are in the output; a file the budget dropped never shows its
    redacted text, so listing its locations would point at nothing."""
    dropped = {f.path for f in files if f.dropped is not None}
    if not dropped:
        return found
    live = Redactions()
    for path, line, rule in found.locations:
        if path not in dropped:
            live.locations.append((path, line, rule))
            live.by_rule[rule] += 1
    return live


def _mime(ref: InputRef) -> str | None:
    return ref.detected.mime if ref.detected else None


def _metadata(meta: Metadata, coll: Collected, files: list[PackFile], info: PackInfo, actions: list[str]) -> None:
    live = [f for f in files if f.dropped is None]
    langs: Counter[str] = Counter()
    for e in coll.packed:
        if e.language and is_code_name(e.path):
            langs[e.language] += e.size
    extra = meta.extra
    extra["repo"] = info.name
    if info.ref:
        extra["ref"] = info.ref
    if info.commit:
        extra["commit"] = info.commit
    if info.subpath:
        extra["subpath"] = info.subpath
    extra["languages"] = ", ".join(lang for lang, _n in langs.most_common(8))
    extra["files"] = len(live)
    extra["bytes"] = sum(f.size for f in live)
    extra["packed_bytes"] = sum(len(f.text.encode("utf-8")) for f in live)
    extra["tokens"] = sum(f.tokens for f in live)
    for reason, n in sorted(coll.reasons.items()):
        extra[f"excluded.{reason}"] = n
    if actions:
        extra["budget_actions"] = " | ".join(actions)
    lic = next((e.path for e in coll.files if e.depth == 0 and _LICENSE.match(e.path)), None)
    if lic:
        extra["license_file"] = lic
    for e in coll.packed:
        if e.depth == 0 and e.path.lower() in _MANIFESTS:
            _manifest(meta, e)
            break


def _manifest(meta: Metadata, e: FileEntry) -> None:
    """Project name and description from the root manifest (8c step 3). Malformed manifests are ignored."""
    name: object = None
    desc: object = None
    low = e.path.lower()
    try:
        if low == "package.json":
            data = json.loads(e.text)
            if isinstance(data, dict):
                name, desc = data.get("name"), data.get("description")
        elif low in ("pyproject.toml", "cargo.toml"):
            data = tomllib.loads(e.text)
            section = data.get("project") or data.get("package") or data.get("tool", {}).get("poetry") or {}
            if isinstance(section, dict):
                name, desc = section.get("name"), section.get("description")
        elif low == "go.mod":
            m = re.search(r"^module\s+(\S+)", e.text, re.MULTILINE)
            name = m.group(1) if m else None
    except (ValueError, tomllib.TOMLDecodeError, AttributeError):
        return
    if isinstance(name, str) and name:
        meta.extra["project"] = name[:200]
    if isinstance(desc, str) and desc:
        meta.description = desc[:500]


def _warnings(archive: ReadResult, coll: Collected, found: Redactions) -> list[Warning]:
    out: list[Warning] = []
    secret_files = [f.path for f in coll.files if f.excluded == "secret_file"]
    if secret_files:
        out.append(
            Warning(
                kind=WarningKind.SECRET_FILE_EXCLUDED,
                message=f"Excluded {len(secret_files)} credential file(s): {', '.join(secret_files[:20])}.",
                count=len(secret_files),
                detail={"files": ", ".join(secret_files[:200])},
            )
        )
    w = secret_warning(found)
    if w is not None:
        out.append(w)
    skipped = len(archive.skipped_unsafe) + archive.skipped_links
    if skipped:
        out.append(
            Warning(
                kind=WarningKind.ARCHIVE_ENTRY_SKIPPED,
                message=f"Skipped {skipped} archive entries with unsafe paths or symlinks.",
                count=skipped,
                detail={"unsafe_paths": len(archive.skipped_unsafe), "links": archive.skipped_links},
            )
        )
    if archive.encrypted:
        out.append(
            Warning(
                kind=WarningKind.ARCHIVE_ENCRYPTED,
                message=f"Skipped {archive.encrypted} encrypted archive entries.",
                count=archive.encrypted,
            )
        )
    if archive.truncated:
        out.append(
            Warning(
                kind=WarningKind.ARCHIVE_TRUNCATED,
                message="The archive has more entries than the limit; the rest were not read.",
            )
        )
    if coll.clean.total:
        out.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                severity="info",
                message=f"Removed {coll.clean.total} control or invisible characters (possible Trojan Source).",
                count=coll.clean.total,
            )
        )
    return out
