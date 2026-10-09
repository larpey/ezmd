"""License gate for the default (non-dev) dependency tree.

Usage:
    uv run python tools/license_check.py                   # Python tree from uv.lock
    uv run python tools/license_check.py --offline         # never query PyPI
    uv run python tools/license_check.py --pnpm-json f.json   # also check `pnpm licenses list --prod --json`

The Python package set comes from `uv export --no-dev --all-packages --all-extras --no-extra nonfree`
(every platform marker, so packages that only install on another OS are still checked, and every
optional extra except `nonfree`, which is the one place copyleft engines may live). License metadata comes from the
installed distribution when available, else from the PyPI JSON API for the exact locked version.
Each license is normalized to SPDX (License-Expression, then classifiers, then the License field),
compared against tools/license_allowlist.toml, with per-package decisions from
tools/license_overrides.toml. Packages in the allowlist's [platform_runtime] exception class
(proprietary GPU runtime libraries that only an optional extra pulls in, on some platforms) pass with
their own verdict source; a test keeps them out of the no-extras tree. Exit 1 lists every offender with
name, version, and evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALLOWLIST = ROOT / "tools" / "license_allowlist.toml"
DEFAULT_OVERRIDES = ROOT / "tools" / "license_overrides.toml"
PYPI_TIMEOUT_S = 15

# Trove classifier -> SPDX. Only unambiguous classifiers are mapped; "BSD License" is ambiguous
# (2- or 3-clause) and is resolved from the License text or an override instead.
CLASSIFIER_SPDX: dict[str, str] = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: MIT No Attribution License (MIT-0)": "MIT-0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: OSI Approved :: zlib/libpng License": "Zlib",
    "License :: OSI Approved :: Boost Software License 1.0 (BSL-1.0)": "BSL-1.0",
    "License :: OSI Approved :: Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)": "GPL-2.0-or-later",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "License :: OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0-only",
    "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0-or-later",
}

# Free-text License field / pnpm license strings -> SPDX (case-insensitive exact match).
TEXT_SPDX: dict[str, str] = {
    "mit": "MIT",
    "mit license": "MIT",
    "the mit license": "MIT",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache software license 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "modified bsd": "BSD-3-Clause",
    "3-clause bsd": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "bsd-3-clause license": "BSD-3-Clause",
    "2-clause bsd license": "BSD-2-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    "isc": "ISC",
    "isc license": "ISC",
    "mpl-2.0": "MPL-2.0",
    "mpl 2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "psf": "PSF-2.0",
    "psf-2.0": "PSF-2.0",
    "psf license": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "unlicense": "Unlicense",
    "0bsd": "0BSD",
    "cc0-1.0": "CC0-1.0",
    "zlib": "Zlib",
    "hpnd": "HPND",
}

SPDX_TOKEN = re.compile(r"\(|\)|[A-Za-z0-9.+\-]+")

# SPDX ids we recognize when a free-text License field already looks like an expression. Ids
# outside this set (and outside the policy's allow/deny lists) mean "not recognized".
EXTRA_KNOWN_SPDX = frozenset({"MIT-0", "CNRI-Python", "BlueOak-1.0.0", "Artistic-2.0", "EPL-2.0", "CC-BY-4.0"})


@dataclass(frozen=True)
class Package:
    name: str
    version: str


@dataclass(frozen=True)
class Verdict:
    package: Package
    spdx: str | None
    source: str
    evidence: str
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class Policy:
    allow: frozenset[str]
    deny: frozenset[str]
    nonfree: frozenset[str]
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    platform_runtime: frozenset[str] = frozenset()
    platform_runtime_reason: str = ""


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_policy(allowlist: Path, overrides_path: Path) -> Policy:
    data = tomllib.loads(allowlist.read_text(encoding="utf-8"))
    overrides: dict[str, dict[str, Any]] = {}
    for name, spdx in data.get("overrides", {}).items():
        overrides[normalize_name(name)] = {"license": spdx, "url": "", "source": str(allowlist.name)}
    if overrides_path.exists():
        odata = tomllib.loads(overrides_path.read_text(encoding="utf-8"))
        for name, entry in odata.get("packages", {}).items():
            if not isinstance(entry, dict) or not entry.get("license") or not entry.get("url"):
                raise SystemExit(f"{overrides_path}: override for {name!r} needs both 'license' and 'url'")
            overrides[normalize_name(name)] = {**entry, "source": overrides_path.name}
    runtime = data.get("platform_runtime", {})
    runtime_packages = frozenset(normalize_name(p) for p in runtime.get("packages", []))
    if runtime_packages and not str(runtime.get("reason", "")).strip():
        raise SystemExit(f"{allowlist}: [platform_runtime] needs a 'reason'")
    return Policy(
        allow=frozenset(data.get("allow", {}).get("licenses", [])),
        deny=frozenset(data.get("deny", {}).get("licenses", [])),
        nonfree=frozenset(normalize_name(p) for p in data.get("nonfree", {}).get("packages", [])),
        overrides=overrides,
        platform_runtime=runtime_packages,
        platform_runtime_reason=str(runtime.get("reason", "")),
    )


def exported_packages(*, extras: bool = True) -> list[Package]:
    """The locked non-dev tree; with `extras`, every optional extra except `nonfree` is included."""
    cmd = [
        os.environ.get("UV", "uv"),
        "export",
        "--frozen",
        "--no-dev",
        "--all-packages",
        *(["--all-extras", "--no-extra", "nonfree"] if extras else []),
        "--format",
        "requirements-txt",
        "--no-hashes",
        "--no-emit-workspace",
        "--no-header",
        "--no-annotate",
    ]
    try:
        out = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout  # noqa: S603
    except FileNotFoundError as exc:
        raise SystemExit("uv not found on PATH; install uv or run via `uv run`") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"uv export failed:\n{exc.stderr}") from exc
    pkgs: dict[str, Package] = {}
    for raw in out.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._\-]*)(?:\[[^\]]*\])?==([^\s]+)", line)
        if not m:
            raise SystemExit(f"unexpected line in uv export output: {raw!r}")
        pkg = Package(normalize_name(m.group(1)), m.group(2))
        pkgs[pkg.name] = pkg
    return sorted(pkgs.values(), key=lambda p: p.name)


def installed_metadata(pkg: Package) -> dict[str, Any] | None:
    try:
        dist = metadata.distribution(pkg.name)
    except metadata.PackageNotFoundError:
        return None
    if dist.version != pkg.version:
        return None
    md = dist.metadata
    return {
        "license_expression": md.get("License-Expression"),
        "license": md.get("License"),
        "classifiers": md.get_all("Classifier") or [],
    }


def pypi_metadata(pkg: Package) -> dict[str, Any] | None:
    url = f"https://pypi.org/pypi/{pkg.name}/{pkg.version}/json"
    try:
        with urllib.request.urlopen(url, timeout=PYPI_TIMEOUT_S) as resp:
            info = json.load(resp)["info"]
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        return None
    return {
        "license_expression": info.get("license_expression"),
        "license": info.get("license"),
        "classifiers": info.get("classifiers") or [],
    }


def text_to_spdx(text: str | None, known: frozenset[str] = frozenset()) -> str | None:
    if not text:
        return None
    t = text.strip()
    if "\n" in t or len(t) > 120:
        # Full license text pasted into the field: recognize the common ones by their wording.
        low = t.lower()
        if "permission is hereby granted, free of charge" in low:
            return "MIT"
        if "apache license" in low and "version 2.0" in low:
            return "Apache-2.0"
        if "redistribution and use in source and binary forms" in low:
            return "BSD-3-Clause" if "neither the name" in low or "endorse or promote" in low else "BSD-2-Clause"
        return None
    mapped = TEXT_SPDX.get(t.lower())
    if mapped:
        return mapped
    ids = parse_expression_ids(t)
    known_ids = known | EXTRA_KNOWN_SPDX | frozenset(CLASSIFIER_SPDX.values()) | frozenset(TEXT_SPDX.values())
    if ids is not None and all(i in known_ids for i in ids):
        return t  # already an SPDX expression over known ids
    return None


def parse_expression_ids(expr: str) -> list[str] | None:
    tokens = SPDX_TOKEN.findall(expr)
    if not tokens or "".join(tokens).replace(" ", "") != expr.replace(" ", ""):
        return None
    ids = [t for t in tokens if t not in ("(", ")") and t.upper() not in ("AND", "OR", "WITH")]
    if not ids or not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+\-]*", i) for i in ids):
        return None
    return ids


def expression_allowed(expr: str, policy: Policy) -> bool:
    """Evaluate an SPDX expression: OR needs one allowed side, AND needs both. WITH exceptions
    are evaluated on the base license."""
    tokens = SPDX_TOKEN.findall(expr)
    pos = 0

    def atom() -> bool:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            val = disjunction()
            pos += 1  # ")"
            return val
        if pos < len(tokens) and tokens[pos].upper() == "WITH":
            pos += 2
        return tok in policy.allow and tok not in policy.deny

    def conjunction() -> bool:
        nonlocal pos
        val = atom()
        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1
            val = atom() and val
        return val

    def disjunction() -> bool:
        nonlocal pos
        val = conjunction()
        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1
            val = conjunction() or val
        return val

    try:
        return disjunction()
    except IndexError:
        return False


def resolve_spdx(md: dict[str, Any], known: frozenset[str]) -> tuple[str | None, str]:
    expr = md.get("license_expression")
    if expr:
        return expr.strip(), f"License-Expression: {expr.strip()}"
    mapped = sorted({CLASSIFIER_SPDX[c] for c in md.get("classifiers", []) if c in CLASSIFIER_SPDX})
    if mapped:
        return " OR ".join(mapped) if len(mapped) > 1 else mapped[0], "classifiers: " + ", ".join(mapped)
    lic = md.get("license")
    spdx = text_to_spdx(lic, known)
    snippet = (lic or "").strip().replace("\n", " ")[:80]
    lic_classifiers = [c for c in md.get("classifiers", []) if c.startswith("License ::")]
    evidence = f"License: {snippet!r}; classifiers: {lic_classifiers}"
    return spdx, evidence


def check_package(pkg: Package, policy: Policy, offline: bool) -> Verdict:
    if pkg.name in policy.nonfree:
        return Verdict(pkg, None, "-", "nonfree package", False, "nonfree package in the default tree")
    if pkg.name in policy.platform_runtime:
        return Verdict(pkg, None, "platform-runtime exception", policy.platform_runtime_reason.strip(), True)
    ov = policy.overrides.get(pkg.name)
    if ov and (not ov.get("version") or ov["version"] == pkg.version):
        ov_spdx = str(ov["license"])
        ok = expression_allowed(ov_spdx, policy)
        return Verdict(
            pkg,
            ov_spdx,
            f"override ({ov['source']})",
            str(ov.get("url", "")),
            ok,
            "" if ok else "override license not allowed",
        )
    md = installed_metadata(pkg)
    source = "installed"
    if md is None and not offline:
        md, source = pypi_metadata(pkg), "pypi"
    if md is None:
        return Verdict(pkg, None, "none", "no metadata (not installed; PyPI unavailable)", False, "unknown license")
    spdx, evidence = resolve_spdx(md, policy.allow | policy.deny)
    if spdx is None:
        return Verdict(pkg, None, source, evidence, False, "license not recognized as SPDX")
    ids = parse_expression_ids(spdx) or []
    if any(i in policy.deny for i in ids) and not expression_allowed(spdx, policy):
        return Verdict(pkg, spdx, source, evidence, False, "denied license")
    ok = expression_allowed(spdx, policy)
    return Verdict(pkg, spdx, source, evidence, ok, "" if ok else "license not in allowlist")


def check_pnpm(path: Path, policy: Policy) -> list[Verdict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    verdicts: list[Verdict] = []
    for lic, entries in data.items():
        for entry in entries:
            for version in entry.get("versions", [entry.get("version", "?")]):
                pkg = Package(f"npm:{entry['name']}", version)
                ov = policy.overrides.get(pkg.name)
                spdx = str(ov["license"]) if ov else (text_to_spdx(lic, policy.allow | policy.deny) or lic)
                ok = expression_allowed(spdx, policy)
                verdicts.append(
                    Verdict(pkg, spdx, "override" if ov else "pnpm", lic, ok, "" if ok else "license not in allowlist")
                )
    return verdicts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    ap.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    ap.add_argument("--offline", action="store_true", help="do not query PyPI for packages not installed here")
    ap.add_argument("--pnpm-json", type=Path, help="output of `pnpm licenses list --prod --json`")
    ap.add_argument("--skip-python", action="store_true")
    ap.add_argument("--json", action="store_true", help="print every verdict as JSON")
    args = ap.parse_args(argv)

    policy = load_policy(args.allowlist, args.overrides)
    verdicts: list[Verdict] = []
    if not args.skip_python:
        verdicts += [check_package(p, policy, args.offline) for p in exported_packages()]
    if args.pnpm_json:
        verdicts += check_pnpm(args.pnpm_json, policy)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": v.package.name,
                        "version": v.package.version,
                        "license": v.spdx,
                        "source": v.source,
                        "ok": v.ok,
                        "reason": v.reason,
                        "evidence": v.evidence,
                    }
                    for v in verdicts
                ],
                indent=2,
            )
        )
    offenders = [v for v in verdicts if not v.ok]
    if offenders:
        print(f"license check FAILED: {len(offenders)} of {len(verdicts)} packages", file=sys.stderr)
        for v in offenders:
            print(
                f"  {v.package.name}=={v.package.version}: {v.reason} [{v.spdx or '?'}] ({v.source}) {v.evidence}",
                file=sys.stderr,
            )
        print(
            "Fix by choosing another dependency, or add a verified entry with a license URL to "
            f"{args.overrides.relative_to(ROOT) if args.overrides.is_relative_to(ROOT) else args.overrides}.",
            file=sys.stderr,
        )
        return 1
    print(f"license check ok: {len(verdicts)} packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
