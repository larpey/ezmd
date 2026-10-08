"""PDF sanitization with pikepdf (MPL-2.0) before any engine sees the file (docs/spec/part1.md 8.2).

Removes `/OpenAction`, `/AA`, JavaScript (`/JavaScript` name tree, `/JS`, JavaScript actions), `/Launch` and
other active actions, `/EmbeddedFiles` and file-attachment annotations (one `attachment_skipped` warning per
name), `/RichMedia` (and other multimedia annotations), and `/XFA` (`unsupported_feature`). Encrypted files are
opened with the empty user password, then the caller's candidates (at most 50, never logged); a file that stays
locked is reported as `encrypted_no_password`. The page cap is applied by truncating the sanitized copy
(`page_cap_reached`). The sanitized copy is written unencrypted to a private temporary directory.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name

from ezmd.ir import Warning, WarningKind
from ezmd_converters.pdf.pdfinfo import PdfInfo, read_info

_ACTIVE_ACTIONS = frozenset(
    {
        "/JavaScript",
        "/Launch",
        "/ImportData",
        "/SubmitForm",
        "/ResetForm",
        "/RichMediaExecute",
        "/GoToE",
        "/GoToR",
        "/Rendition",
        "/Movie",
        "/Sound",
        "/SetOCGState",
        "/Hide",
        "/Trans",
        "/GoTo3DView",
    }
)
_MEDIA_ANNOTS = frozenset({"/RichMedia", "/Movie", "/Sound", "/Screen", "/3D"})
_STRIP_KEYS = ("/AA", "/OpenAction", "/JS", "/RichMediaContent", "/RichMediaSettings")
_MAX_WALK = 2_000_000
"""Upper bound on visited objects during the sanitizing walk (hostile files can contain millions)."""


class EncryptedNoPassword(Exception):
    """The PDF needs a user password and none of the candidates opened it."""


class UnreadablePdf(Exception):
    """pikepdf/qpdf could not parse the file even with recovery."""


@dataclass(slots=True)
class Sanitized:
    path: Path
    pages_total: int
    pages_kept: int
    info: PdfInfo
    warnings: list[Warning] = field(default_factory=list)
    truncated: bool = False
    tmpdir: tempfile.TemporaryDirectory[str] | None = None

    def cleanup(self) -> None:
        if self.tmpdir is not None:
            self.tmpdir.cleanup()
            self.tmpdir = None


def _open(path: Path, passwords: list[str]) -> tuple[pikepdf.Pdf, bool]:
    """Open with each candidate password. Returns (pdf, opened_with_a_supplied_password)."""
    for i, pw in enumerate(passwords):
        try:
            return pikepdf.open(path, password=pw), i > 0
        except pikepdf.PasswordError:  # noqa: S112 - try the next candidate; passwords are never logged
            continue
        except pikepdf.PdfError as e:
            raise UnreadablePdf(type(e).__name__) from e
    raise EncryptedNoPassword()


def sanitize(path: Path, *, passwords: list[str], max_pages: int, source: str) -> Sanitized:
    """Open, strip active content, cap pages, and save a sanitized copy. Raises EncryptedNoPassword or
    UnreadablePdf."""
    pdf, used_password = _open(path, passwords)
    warnings: list[Warning] = []
    try:
        if pdf.is_encrypted and not used_password and not pdf.allow.extract:
            warnings.append(
                Warning(
                    kind=WarningKind.COPY_RESTRICTED_IGNORED,
                    message="The PDF sets a copy restriction (owner password); its text was extracted anyway.",
                )
            )
        removed: dict[str, int] = {}

        def bump(key: str) -> None:
            removed[key] = removed.get(key, 0) + 1

        attachments = _strip_attachments(pdf, bump)
        for name in attachments:
            warnings.append(
                Warning(
                    kind=WarningKind.ATTACHMENT_SKIPPED,
                    message=f"Embedded file {name!r} was removed during sanitization and not converted.",
                    detail={"name": name},
                )
            )
        if _strip_xfa(pdf):
            warnings.append(
                Warning(
                    kind=WarningKind.UNSUPPORTED_FEATURE,
                    message="The XFA form layer was removed; only the AcroForm fields (if any) are extracted.",
                    detail={"feature": "xfa"},
                )
            )
        _strip_active(pdf, bump)
        if removed:
            warnings.append(
                Warning(
                    kind=WarningKind.REMOVED_SCRIPT_OR_MACRO,
                    message=f"Removed {sum(removed.values())} scripts, actions, or media objects from the PDF.",
                    count=sum(removed.values()),
                    detail={k.lstrip("/"): v for k, v in sorted(removed.items())},
                )
            )
        total = len(pdf.pages)
        kept = min(total, max_pages)
        truncated = kept < total
        if truncated:
            del pdf.pages[kept:]
            warnings.append(
                Warning(
                    kind=WarningKind.PAGE_CAP_REACHED,
                    message=(
                        f"Only the first {kept} of {total} pages were converted; raise the page cap "
                        "(pdf.max_pages / max_pages) to convert more."
                    ),
                    count=total - kept,
                    detail={"pages_total": total, "pages_converted": kept},
                )
            )
        info = read_info(pdf, source=source)
        tmp = tempfile.TemporaryDirectory(prefix="ezmd-pdf-")
        out = Path(tmp.name) / "sanitized.pdf"
        try:
            pdf.save(out, encryption=False)
        except Exception:
            tmp.cleanup()
            raise
        return Sanitized(
            path=out, pages_total=total, pages_kept=kept, info=info, warnings=warnings, truncated=truncated, tmpdir=tmp
        )
    finally:
        pdf.close()


def _strip_attachments(pdf: pikepdf.Pdf, bump: Callable[[str], None]) -> list[str]:
    names: list[str] = []
    try:
        names.extend(str(k) for k in pdf.attachments)
    except Exception:
        names.append("(unreadable name tree)")
    root_names = pdf.Root.get("/Names")
    if isinstance(root_names, Dictionary):
        for key in ("/EmbeddedFiles", "/JavaScript"):
            if key in root_names:
                del root_names[key]
                if key == "/JavaScript":
                    bump("/JavaScript")
    for page in pdf.pages:
        annots = page.obj.get("/Annots")
        if not isinstance(annots, Array):
            continue
        keep = Array()
        for a in annots:
            sub = str(a.get("/Subtype", "")) if isinstance(a, Dictionary) else ""
            if sub == "/FileAttachment":
                fs = a.get("/FS")
                label = ""
                if isinstance(fs, Dictionary):
                    label = str(fs.get("/UF", fs.get("/F", "")))
                names.append(label or "(unnamed attachment annotation)")
                continue
            if sub in _MEDIA_ANNOTS:
                bump(sub)
                continue
            keep.append(a)
        page.obj.Annots = keep
    return names


def _strip_xfa(pdf: pikepdf.Pdf) -> bool:
    form = pdf.Root.get("/AcroForm")
    if isinstance(form, Dictionary) and "/XFA" in form:
        del form["/XFA"]
        return True
    return False


def _strip_active(pdf: pikepdf.Pdf, bump: Callable[[str], None]) -> None:
    """Walk every object reachable from the document catalog and remove active content, counting by key."""
    seen: set[tuple[int, int]] = set()
    stack: list[object] = [pdf.Root]
    visited = 0
    while stack and visited < _MAX_WALK:
        obj = stack.pop()
        visited += 1
        if isinstance(obj, pikepdf.Object) and obj.is_indirect:
            og = obj.objgen
            if og in seen:
                continue
            seen.add(og)
        if isinstance(obj, Dictionary | pikepdf.Stream):
            _clean_dict(obj, bump)
            for key in list(obj.keys()):
                if key in ("/Parent", "/P"):
                    continue
                stack.append(obj[key])
        elif isinstance(obj, Array):
            stack.extend(obj)


def _clean_dict(d: Dictionary | pikepdf.Stream, bump: Callable[[str], None]) -> None:
    for key in _STRIP_KEYS:
        if key in d:
            del d[key]
            bump(key)
    for key in ("/A", "/Next"):
        action = d.get(key)
        if isinstance(action, Dictionary) and str(action.get("/S", "")) in _ACTIVE_ACTIONS:
            bump(str(action.get("/S")))
            del d[key]
        elif isinstance(action, Array):
            del d[key]
            bump("/Next")
    if str(d.get("/S", "")) in _ACTIVE_ACTIONS and "/Type" not in d:
        # A bare action dictionary reached through a name tree or array; neutralize it in place.
        bump(str(d.get("/S")))
        d.S = Name.Named
        d.N = Name.NextPage
