"""Check that every golden fixture has valid provenance (docs/spec/part4.md 4.14.7, CLAUDE.md "Fixtures").

Rules, per `fixtures/<family>/<name>/meta.toml`:
- a `[provenance]` table with `origin` in ORIGIN_LICENSES and a `license` allowed for that origin;
- a non-empty `source`: for `self-generated`, a relative POSIX path to an existing file inside the repository
  (the generator script), or exactly HAND_WRITTEN_SOURCE for inputs written by hand; for every other origin,
  an https URL;
- for every origin except `self-generated`, an entry in CREDITS.md headed `### fixtures/<family>/<name>` with
  Title, Author, License, URL and Retrieved (ISO date) lines, whose License and URL match meta.toml.
CREDITS.md entries for fixtures that no longer exist are errors too (stale credits).

Run: `uv run python tools/check_fixture_provenance.py` (exit 1 on any problem). Also run by
tests/test_fixture_provenance.py, so the pytest gate enforces it.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]

ORIGIN_LICENSES: dict[str, frozenset[str]] = {
    "self-generated": frozenset({"CC0-1.0"}),
    "public-domain": frozenset({"LicenseRef-US-Government-Work", "LicenseRef-Public-Domain", "CC-PDDC"}),
    "cc0": frozenset({"CC0-1.0"}),
    "cc-by": frozenset({"CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0"}),
}
"""Allowed licenses per origin. No NC, ND, SA-incompatible, commercial, or platform-scraped content."""

CREDIT_FIELDS = ("Title", "Author", "License", "URL", "Retrieved")
HAND_WRITTEN_SOURCE = "hand-written for this repository (CC0)"
_HEADING = re.compile(r"^### (fixtures/[^\s/]+/[^\s/]+)\s*$")
_FIELD = re.compile(r"^- (\w+): (.+?)\s*$")


@dataclass(frozen=True, slots=True)
class Credit:
    fixture: str
    fields: dict[str, str]


def parse_credits(text: str) -> tuple[dict[str, Credit], list[str]]:
    """Parse CREDITS.md into {fixture path: Credit}; second value lists format problems."""
    credits: dict[str, Credit] = {}
    problems: list[str] = []
    current: str | None = None
    fields: dict[str, str] = {}

    def flush() -> None:
        if current is None:
            return
        if current in credits:
            problems.append(f"CREDITS.md: duplicate entry for {current}")
        credits[current] = Credit(fixture=current, fields=dict(fields))

    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            flush()
            current, fields = heading.group(1), {}
            continue
        if line.startswith("#"):
            flush()
            current, fields = None, {}
            continue
        field = _FIELD.match(line)
        if field and current is not None:
            fields[field.group(1)] = field.group(2)
    flush()
    return credits, problems


def _check_credit(fx: str, prov: dict[str, object], credit: Credit | None) -> list[str]:
    if credit is None:
        return [f"{fx}: origin {prov.get('origin')!r} needs a CREDITS.md entry headed '### {fx}'"]
    errors = [f"{fx}: CREDITS.md entry lacks '- {name}:'" for name in CREDIT_FIELDS if not credit.fields.get(name)]
    if credit.fields.get("License") and credit.fields["License"] != prov.get("license"):
        errors.append(f"{fx}: CREDITS.md License {credit.fields['License']!r} != meta.toml {prov.get('license')!r}")
    if credit.fields.get("URL") and credit.fields["URL"] != prov.get("source"):
        errors.append(f"{fx}: CREDITS.md URL does not match meta.toml provenance.source")
    retrieved = credit.fields.get("Retrieved")
    if retrieved:
        try:
            dt.date.fromisoformat(retrieved)
        except ValueError:
            errors.append(f"{fx}: CREDITS.md Retrieved {retrieved!r} is not an ISO date (YYYY-MM-DD)")
    return errors


def _repo_file(root: Path, source: str) -> bool:
    """A relative, forward-slash path without `..` that names an existing regular file under `root`."""
    pure = PurePosixPath(source)
    if pure.is_absolute() or PureWindowsPath(source).is_absolute() or chr(92) in source or ".." in pure.parts:
        return False
    target = (root / pure).resolve()
    return target.is_file() and target.is_relative_to(root.resolve())


def check_fixture(meta_path: Path, root: Path, credits: dict[str, Credit]) -> list[str]:
    fx = meta_path.parent.relative_to(root).as_posix()
    try:
        meta = tomllib.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return [f"{fx}: cannot read meta.toml: {e}"]
    prov = meta.get("provenance")
    if not isinstance(prov, dict):
        return [f"{fx}: meta.toml has no [provenance] table"]
    origin, license_, source = prov.get("origin"), prov.get("license"), prov.get("source")
    if origin not in ORIGIN_LICENSES:
        return [f"{fx}: provenance.origin {origin!r} not in {sorted(ORIGIN_LICENSES)}"]
    errors: list[str] = []
    if license_ not in ORIGIN_LICENSES[origin]:
        allowed = sorted(ORIGIN_LICENSES[origin])
        errors.append(f"{fx}: license {license_!r} not allowed for origin {origin!r} ({allowed})")
    if not isinstance(source, str) or not source.strip():
        errors.append(f"{fx}: provenance.source is empty")
        return errors
    if origin == "self-generated":
        if source != HAND_WRITTEN_SOURCE and not _repo_file(root, source):
            errors.append(
                f"{fx}: self-generated source {source!r} must be a relative path to an existing file in the "
                f"repository or exactly {HAND_WRITTEN_SOURCE!r}"
            )
        return errors
    if not source.startswith("https://"):
        errors.append(f"{fx}: provenance.source must be an https URL for origin {origin!r}")
    errors.extend(_check_credit(fx, prov, credits.get(fx)))
    return errors


def check(root: Path = ROOT) -> list[str]:
    """Return every provenance problem under `root` (the repository root)."""
    credits_path = root / "CREDITS.md"
    credits: dict[str, Credit] = {}
    errors: list[str] = []
    if credits_path.exists():
        credits, errors = parse_credits(credits_path.read_text(encoding="utf-8"))
    metas = sorted(m for m in (root / "fixtures").glob("*/*/meta.toml") if not m.parent.name.startswith("_"))
    if not metas:
        errors.append("no fixtures found under fixtures/*/*/meta.toml")
    for meta_path in metas:
        errors.extend(check_fixture(meta_path, root, credits))
    present = {m.parent.relative_to(root).as_posix() for m in metas}
    errors.extend(f"CREDITS.md: entry {fx} has no matching fixture (stale)" for fx in sorted(set(credits) - present))
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else ROOT
    errors = check(root)
    for e in errors:
        print(e, file=sys.stderr)
    count = len(list((root / "fixtures").glob("*/*/meta.toml")))
    print(f"fixture provenance: {count} fixtures, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
