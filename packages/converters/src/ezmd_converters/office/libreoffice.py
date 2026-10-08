"""documents.libreoffice: legacy and non-OOXML Office formats through LibreOffice headless (Part 2 2c step 38).

`.doc`, `.dot`, `.wpd`, `.rtf` go to DOCX; `.xls`, `.xlsb` to XLSX; `.ppt`, `.pps` to PPTX; ODF is a fallback
behind the native ODF parser. `soffice` (MPL-2.0) is never linked: it runs through `ezmd.core.sandbox.run`
with a throwaway profile whose `registrymodifications.xcu` disables macros, `HOME` pointed at the temp dir,
and a per-file timeout. The OOXML it writes goes through the same package sanitizer and native converters.
Without `soffice` the converter returns an empty document carrying `libreoffice_missing`, so the registry falls
through to the next converter (striprtf for RTF) or reports why nothing came out.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ezmd.context import Limits
from ezmd.core import sandbox
from ezmd.inputs import InputRef
from ezmd.ir import Document, Metadata, SourceType, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.office._common import (
    FAMILY,
    LEGACY_EXTS,
    LEGACY_MIMES,
    MB,
    ODF_EXTS,
    ODF_MIMES,
    RTF_EXTS,
    RTF_MIMES,
    OfficeOptions,
    confidence,
)

_STANDARD_PATHS = (
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
    "/opt/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)
_TARGET_BY_EXT = {
    ".doc": "docx", ".dot": "docx", ".wpd": "docx", ".rtf": "docx", ".odt": "docx", ".ott": "docx",
    ".xls": "xlsx", ".xlsb": "xlsx", ".ods": "xlsx", ".ots": "xlsx",
    ".ppt": "pptx", ".pps": "pptx", ".odp": "pptx", ".otp": "pptx",
}  # fmt: skip
_TARGET_BY_MIME = {
    "application/msword": "docx",
    "application/vnd.wordperfect": "docx",
    "application/rtf": "docx",
    "text/rtf": "docx",
    "application/vnd.ms-excel": "xlsx",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12": "xlsx",
    "application/vnd.ms-powerpoint": "pptx",
    "application/vnd.oasis.opendocument.text": "docx",
    "application/vnd.oasis.opendocument.spreadsheet": "xlsx",
    "application/vnd.oasis.opendocument.presentation": "pptx",
}
_SOURCE_TYPE = {"docx": SourceType.DOCX, "xlsx": SourceType.XLSX, "pptx": SourceType.PPTX}

# Macro security "very high" and macro execution disabled for the throwaway profile.
_XCU = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
    '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>\n'
    '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
    '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>\n'
    '<item oor:path="/org.openoffice.Office.Common/Misc">'
    '<prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>\n'
    "</oor:items>\n"
)


def find_soffice() -> str | None:
    """`LIBREOFFICE_PATH`, then PATH, then standard install locations. `EZMD_DISABLE_LIBREOFFICE=1` hides it."""
    if os.environ.get("EZMD_DISABLE_LIBREOFFICE", "").strip() in ("1", "true", "yes"):
        return None
    env = os.environ.get("LIBREOFFICE_PATH", "").strip()
    if env and Path(env).is_file():
        return env
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for p in _STANDARD_PATHS:
        if Path(p).is_file():
            return p
    return None


def _target(ref: InputRef) -> str | None:
    mime = (ref.detected.mime if ref.detected else "") or ""
    if mime in _TARGET_BY_MIME:
        return _TARGET_BY_MIME[mime]
    return _TARGET_BY_EXT.get(Path(ref.display).suffix.lower())


class LibreOfficeConverter:
    id = "documents.libreoffice"
    family = FAMILY
    priority = 0
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = (*LEGACY_MIMES, *RTF_MIMES, *ODF_MIMES)
    limits = Limits(max_bytes=100 * MB, timeout_s=180)

    def can_handle(self, ref: InputRef) -> float:
        legacy = confidence(ref, LEGACY_MIMES, LEGACY_EXTS)
        if legacy:
            return legacy
        other = max(confidence(ref, RTF_MIMES, RTF_EXTS), confidence(ref, ODF_MIMES, ODF_EXTS))
        return 0.5 if other else 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = OfficeOptions.from_options(options)
        target = _target(ref)
        if target is None:
            raise ConversionError(f"no LibreOffice target for {ref.display}", user_message="Unsupported Office format.")
        soffice = find_soffice()
        if soffice is None:
            return _missing(ref)
        size = ref.size()
        if size > opts.libreoffice_max_bytes:
            raise ConversionError(
                f"{size} bytes exceeds libreoffice_max_bytes",
                user_message=f"This file is larger than the {opts.libreoffice_max_bytes // MB} MB LibreOffice limit.",
                retryable_with_fallback=False,
            )
        options.ctx.check_deadline()
        options.ctx.progress("libreoffice", None, f"Converting to {target} with LibreOffice")
        out = _run(soffice, ref, target, opts.libreoffice_timeout_s)
        return _native(out, target, ref, options)


def _missing(ref: InputRef) -> Document:
    meta = Metadata(source=ref.display, source_type=SourceType.OTHER, mime=ref.detected.mime if ref.detected else None)
    doc = Document(metadata=meta)
    doc.warnings.append(
        Warning(
            kind=WarningKind.LIBREOFFICE_MISSING,
            message=f"LibreOffice is not installed, so {Path(ref.display).suffix or 'this format'} files cannot be "
            "converted with full structure.",
        )
    )
    return doc.finalize()


def _run(soffice: str, ref: InputRef, target: str, timeout: int) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ezmd-lo-") as tmp:
        root = Path(tmp)
        suffix = Path(ref.display).suffix.lower()
        suffix = suffix if suffix[1:].isalnum() and len(suffix) <= 6 else ".bin"
        src = root / f"input{suffix}"
        src.write_bytes(ref.read())
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user" / "registrymodifications.xcu").write_text(_XCU, encoding="utf-8", newline="\n")
        outdir = root / "out"
        outdir.mkdir()
        argv = [
            soffice,
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to",
            target,
            "--outdir",
            str(outdir),
            str(src),
        ]
        try:
            result = sandbox.run(argv, timeout=float(timeout), cwd=root, env={"HOME": tmp, "TMPDIR": tmp})
        except sandbox.SandboxTimeout as e:
            raise ConversionError(
                f"LibreOffice exceeded {timeout}s", user_message="LibreOffice took too long to convert this file."
            ) from e
        except sandbox.SandboxError as e:
            raise ConversionError(f"LibreOffice failed to start: {e}", user_message="LibreOffice could not run.") from e
        produced = outdir / f"input.{target}"
        if result.returncode != 0 or not produced.is_file():
            raise ConversionError(
                f"LibreOffice exited with {result.returncode} and wrote no {target}",
                user_message="LibreOffice could not convert this file.",
            )
        return produced.read_bytes()


def _native(data: bytes, target: str, ref: InputRef, options: ConvertOptions) -> Document:
    from ezmd_converters.office import docx, pptx, xlsx
    from ezmd_converters.office._package import OfficePackage

    pkg = OfficePackage(data, what=target.upper())
    mime = ref.detected.mime if ref.detected else None
    if target == "docx":
        doc = docx.convert_package(pkg, ref.display, options, mime=mime)
    elif target == "xlsx":
        doc = xlsx.convert_package(pkg, ref.display, options, mime=mime)
    else:
        doc = pptx.convert_package(pkg, ref.display, options, mime=mime)
    ext = Path(ref.display).suffix.lower()
    doc.metadata.source_type = (
        SourceType.RTF if ext == ".rtf" else SourceType.ODF if ext in ODF_EXTS else _SOURCE_TYPE[target]
    )
    doc.metadata.extra["converted_with"] = "libreoffice"
    return doc
