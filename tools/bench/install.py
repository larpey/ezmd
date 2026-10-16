"""Create each competitor's isolated environment under the cache directory.

    uv run python -m tools.bench install [--tools a,b] [--force]

Venv tools get their own uv venv (Python 3.12) with exact pins from competitors.toml; tools with
`torch = true` resolve torch through `uv pip --torch-backend auto`, which picks the CUDA wheel matching the
installed driver (no system CUDA toolkit needed). ezmd is installed from the PyPI release when the pinned
version is published there, otherwise from wheels built from this checkout (same version, same code).
`pip freeze` of every venv is written to `<venv>/freeze.txt` and copied into each run's results.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from tools.bench.config import ROOT, Tool, cache_dir, load_tools

PYTHON = "3.12"


def _uv() -> str:
    found = shutil.which("uv")
    if not found:
        raise SystemExit("uv not found on PATH")
    return found


def _docker() -> str:
    from tools.bench.runner import docker_exe

    found = docker_exe()
    if not found:
        raise SystemExit("docker not found")
    return found


def on_pypi(name: str, version: str) -> bool:
    """Whether PyPI has `name==version`. A network failure stops the install: falling back to local wheels then
    would label this checkout's code with a PyPI version it may not match."""
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as resp:
            releases = json.load(resp).get("releases", {})
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise SystemExit(f"PyPI lookup for {name} failed: HTTP {exc.code}") from exc
    except OSError as exc:
        raise SystemExit(f"cannot reach PyPI to check {name}=={version}: {exc}") from exc
    return bool(releases.get(version))


def build_local_wheels() -> Path:
    """Wheels of this checkout's packages, for ezmd before its version is on PyPI."""
    out = cache_dir() / "wheels" / "ezmd-local"
    if out.exists():
        shutil.rmtree(out)
    for pkg in ("packages/core", "packages/converters", "packages/mcp"):
        subprocess.run([_uv(), "build", "--wheel", "-o", str(out), str(ROOT / pkg)], check=True)
    return out


def install_venv(tool: Tool, *, force: bool, find_links: Path | None) -> None:
    if tool.python.exists() and not force:
        print(f"{tool.name}: venv exists, skipping (use --force to rebuild)")
        return
    if tool.venv.exists():
        shutil.rmtree(tool.venv)
    subprocess.run([_uv(), "venv", "--python", PYTHON, str(tool.venv)], check=True)
    cmd = [_uv(), "pip", "install", "--python", str(tool.python), *tool.requirements]
    if tool.torch:
        cmd += ["--torch-backend", "auto"]
    if find_links is not None:
        cmd += ["--find-links", str(find_links), "--prerelease", "allow"]
    subprocess.run(cmd, check=True)
    freeze = subprocess.run(
        [_uv(), "pip", "freeze", "--python", str(tool.python)], check=True, capture_output=True, text=True
    )
    (tool.venv / "freeze.txt").write_text(freeze.stdout, encoding="utf-8")
    bindir = tool.python.parent
    for step in tool.extra.get("post_install", ()):
        argv = [str(a).replace("{bin}", str(bindir)).replace("{cache}", str(cache_dir())) for a in step]
        subprocess.run(argv, check=True)
    print(f"{tool.name}: installed")


def install_binary(tool: Tool, *, force: bool) -> None:
    dest = cache_dir() / "bin" / f"{tool.name}-{tool.version}"
    if dest.exists() and not force:
        print(f"{tool.name}: {dest} exists, skipping")
        return
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / Path(tool.url).name
    urllib.request.urlretrieve(tool.url, archive)  # noqa: S310 (pinned https URL from the manifest)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise SystemExit(f"{tool.name}: unsafe path in archive: {member}")
        zf.extractall(dest)
    print(f"{tool.name}: unpacked to {dest}")


def binary_path(tool: Tool) -> Path:
    dest = cache_dir() / "bin" / f"{tool.name}-{tool.version}"
    exe = f"{tool.name}.exe" if sys.platform == "win32" else tool.name
    hits = sorted(dest.rglob(exe))
    if not hits:
        raise FileNotFoundError(f"{tool.name} binary not installed under {dest}")
    return hits[0]


def main(names: list[str] | None, *, force: bool) -> int:
    tools = load_tools()
    selected = [tools[n] for n in names] if names else list(tools.values())
    find_links: Path | None = None
    failed: list[str] = []
    for tool in selected:
        try:
            if tool.kind == "binary":
                install_binary(tool, force=force)
                continue
            if tool.kind == "docker":
                subprocess.run([_docker(), "pull", str(tool.extra["image"])], check=True)
                continue
            links = None
            if tool.name.startswith("ezmd") and not on_pypi("ezmd", tool.requirements[0].split("==", 1)[1]):
                find_links = find_links or build_local_wheels()
                links = find_links
            install_venv(tool, force=force, find_links=links)
        except (subprocess.CalledProcessError, OSError, SystemExit) as exc:
            print(f"{tool.name}: install FAILED: {exc}")
            failed.append(tool.name)
    if failed:
        print("failed:", ", ".join(failed))
    return 1 if failed else 0
