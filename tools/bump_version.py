"""Set one release version everywhere it is recorded (the counterpart of tools/release_version.py).

    python tools/bump_version.py 0.1.0rc1     # PEP 440: Python packages, intomd.__version__, server.json
    python tools/bump_version.py 0.1.0 --npm  # also the npm SDK (final releases only; npm takes the semver)

The published Python packages pin each other exactly (`intomd` -> `intomd-converters==V`,
`intomd-mcp` -> `intomd==V`) so an install never mixes releases. Run `uv lock` afterwards.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEP440 = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(rc[1-9][0-9]*)?$")
PYPROJECTS = ("packages/core", "packages/converters", "packages/mcp", "apps/api", "apps/fetch-node")
PINS = {"packages/core": "intomd-converters", "packages/mcp": "intomd"}


def _sub_once(text: str, pattern: str, repl: str, where: str) -> str:
    new, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"{where}: pattern {pattern!r} not found")
    return new


def bump(root: Path, version: str, *, npm: bool) -> list[str]:
    if not PEP440.match(version):
        raise SystemExit(f"{version!r} is not X.Y.Z or X.Y.ZrcN")
    if npm and "rc" in version:
        raise SystemExit("npm is only bumped for final releases (release candidates are not published to npm)")
    changed: list[str] = []
    for pkg in PYPROJECTS:
        path = root / pkg / "pyproject.toml"
        text = _sub_once(path.read_text(encoding="utf-8"), r'^version = "[^"]*"', f'version = "{version}"', str(path))
        if pkg in PINS:
            dep = re.escape(PINS[pkg])
            text = _sub_once(text, rf'^    "{dep}(==[^"]*)?",$', f'    "{PINS[pkg]}=={version}",', str(path))
        path.write_text(text, encoding="utf-8", newline="\n")
        changed.append(str(path.relative_to(root)))
    init = root / "packages/core/src/intomd/__init__.py"
    init.write_text(
        _sub_once(init.read_text(encoding="utf-8"), r'^__version__ = "[^"]*"', f'__version__ = "{version}"', str(init)),
        encoding="utf-8",
        newline="\n",
    )
    changed.append(str(init.relative_to(root)))
    server = root / "packages/mcp/server.json"
    data = json.loads(server.read_text(encoding="utf-8"))
    data["version"] = version
    for package in data.get("packages", []):
        package["version"] = version
    server.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    changed.append(str(server.relative_to(root)))
    if npm:
        pkg_json = root / "packages/sdk-ts/package.json"
        text = _sub_once(
            pkg_json.read_text(encoding="utf-8"), r'^  "version": "[^"]*",', f'  "version": "{version}",', str(pkg_json)
        )
        pkg_json.write_text(text, encoding="utf-8", newline="\n")
        changed.append(str(pkg_json.relative_to(root)))
    return changed


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--npm"]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 64
    for path in bump(ROOT, args[0], npm="--npm" in argv):
        print(f"bumped {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
