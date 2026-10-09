"""Validate a release tag against the package versions (used by .github/workflows/release.yml).

    python tools/release_version.py v1.2.0        # final release
    python tools/release_version.py v1.2.0-rc1    # release candidate: PyPI pre-release, not npm

Accepted tags: vMAJOR.MINOR.PATCH and vMAJOR.MINOR.PATCH-rcN. Every published Python package must carry
the matching PEP 440 version (1.2.0 / 1.2.0rc1); for a final release the npm SDK must carry 1.2.0 too
(release candidates are not published to npm). Prints `key=value` lines for $GITHUB_OUTPUT:
version, pep440, prerelease (true/false). Exits 1 with a message per mismatch.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"^v(?P<base>(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))(?:-rc(?P<rc>[1-9][0-9]*))?$")
PYTHON_PACKAGES = ("packages/core", "packages/converters", "packages/mcp")
NPM_PACKAGE = "packages/sdk-ts/package.json"


def parse_tag(tag: str) -> tuple[str, str, bool]:
    """Return (semver, pep440, prerelease) for a release tag, or raise ValueError."""
    m = TAG.match(tag)
    if m is None:
        raise ValueError(f"tag {tag!r} is not vX.Y.Z or vX.Y.Z-rcN")
    base, rc = m.group("base"), m.group("rc")
    if rc is None:
        return base, base, False
    return f"{base}-rc{rc}", f"{base}rc{rc}", True


def check_versions(root: Path, pep440: str, semver: str, prerelease: bool) -> list[str]:
    problems: list[str] = []
    for pkg in PYTHON_PACKAGES:
        project = tomllib.loads((root / pkg / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        if project["version"] != pep440:
            problems.append(f"{pkg}/pyproject.toml: {project['name']} is {project['version']}, tag needs {pep440}")
    if not prerelease:
        npm = json.loads((root / NPM_PACKAGE).read_text(encoding="utf-8"))
        if npm["version"] != semver:
            problems.append(f"{NPM_PACKAGE}: {npm['name']} is {npm['version']}, tag needs {semver}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 64
    try:
        semver, pep440, prerelease = parse_tag(argv[1])
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    problems = check_versions(ROOT, pep440, semver, prerelease)
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"version={semver}")
    print(f"pep440={pep440}")
    print(f"prerelease={'true' if prerelease else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
