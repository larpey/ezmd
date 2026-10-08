"""Small commands: `capabilities`, `detect`, `version`, `serve`."""

from __future__ import annotations

import importlib.metadata as md
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from intomd import __version__
from intomd.cli.exitcodes import EXIT_ARGS, classify

__all__ = ["build_info", "capabilities", "detect", "serve", "version"]

_BUILD_FILE = Path(__file__).resolve().parents[1] / "_build_info.json"
"""Written by release builds: {"commit": "...", "build_date": "..."}. Absent in a source checkout."""


def _git_commit(start: Path) -> str | None:
    """The checked-out commit of a source checkout, read from .git files (no subprocess)."""
    for d in [start, *start.parents]:
        dotgit = d / ".git"
        if dotgit.is_file():
            text = dotgit.read_text(encoding="utf-8").strip()
            if not text.startswith("gitdir:"):
                return None
            gitdir = (d / text.split(":", 1)[1].strip()).resolve()
        elif dotgit.is_dir():
            gitdir = dotgit
        else:
            continue
        return _resolve_head(gitdir)
    return None


def _resolve_head(gitdir: Path) -> str | None:
    try:
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head[:40] or None
    ref = head.split(":", 1)[1].strip()
    common = gitdir
    if (gitdir / "commondir").is_file():
        common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    for root in (gitdir, common):
        p = root / ref
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()[:40] or None
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            parts = line.split(" ")
            if len(parts) == 2 and parts[1] == ref:
                return parts[0][:40]
    return None


def build_info() -> dict[str, str | None]:
    """Version, commit, and build date from the release build file, the install's direct_url.json
    (VCS installs), or the source checkout; `None` when unknown."""
    info: dict[str, str | None] = {"version": __version__, "commit": None, "build_date": None}
    try:
        data = json.loads(_BUILD_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            info["commit"] = str(data["commit"]) if data.get("commit") else None
            info["build_date"] = str(data["build_date"]) if data.get("build_date") else None
    except (OSError, ValueError):
        pass
    if info["commit"] is None:
        try:
            direct = md.distribution("intomd").read_text("direct_url.json")
            vcs = json.loads(direct).get("vcs_info", {}) if direct else {}
            info["commit"] = vcs.get("commit_id") or None
        except (md.PackageNotFoundError, ValueError, AttributeError):
            pass
    if info["commit"] is None:
        try:
            info["commit"] = _git_commit(Path(__file__).resolve().parent)
        except OSError:
            info["commit"] = None
    return info


def version(as_json: Annotated[bool, typer.Option("--json", help="As JSON.")] = False) -> None:
    """Print the version, commit, and build date."""
    info = build_info()
    if as_json:
        typer.echo(json.dumps(info))
        return
    commit = (info["commit"] or "unknown")[:12]
    typer.echo(f"intomd {info['version']} (commit {commit}, built {info['build_date'] or 'unknown'})")


def capabilities(
    remote: Annotated[str | None, typer.Option("--remote", help="Ask this intomd instance instead.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="As JSON.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", hidden=True)] = False,
) -> None:
    """List converters (loaded or unavailable, with the reason)."""
    from intomd.cli.convert import emit_json, fail, load_config_or_exit

    cfg = load_config_or_exit(as_json=as_json, quiet=quiet)
    target = (remote if remote is not None else cfg.remote_url).strip()
    try:
        if target:
            from intomd.cli.remote import RemoteClient

            with RemoteClient(target, cfg.api_key) as client:
                data: dict[str, Any] = client.capabilities()
        else:
            import intomd.library as lib

            data = lib.capabilities()
    except Exception as e:
        f = classify(e)
        raise fail(f.message, f.exit_code, as_json=as_json) from e
    if as_json:
        emit_json(data)
        return
    from rich.console import Console
    from rich.markup import escape
    from rich.table import Table

    t = Table("id", "family", "mimes", "loaded", "note")
    for r in data.get("converters") or []:
        if not isinstance(r, dict):
            continue
        mimes = r.get("mimes")
        note = r.get("reason") or r.get("error") or ("experimental" if r.get("experimental") else "")
        t.add_row(
            escape(str(r.get("id"))),
            escape(str(r.get("family"))),
            escape(", ".join(map(str, mimes)) if isinstance(mimes, list) else ""),
            "yes" if r.get("loaded", True) else "no",
            escape(str(note)),
        )
    Console().print(t)


def detect(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="File to inspect.")],
) -> None:
    """Show the detected content type of a file (always JSON)."""
    from intomd.detect import detect as run_detect
    from intomd.inputs import InputRef

    d = run_detect(InputRef.from_path(path))
    payload = {
        "mime": d.mime,
        "confidence": round(d.confidence, 4),
        "magika_label": d.magika_label,
        "libmagic_mime": d.libmagic_mime,
        "extension_mime": d.extension_mime,
    }
    typer.echo(json.dumps(payload, indent=2))


_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8080,
    public: Annotated[bool, typer.Option("--i-know-this-is-public", help="Allow binding non-loopback.")] = False,
) -> None:
    """Run the HTTP API and web UI in-process (inline queue without Redis)."""
    from intomd.cli.convert import fail

    if host not in _LOOPBACK and not public:
        raise fail("Refusing to bind a non-loopback address without --i-know-this-is-public.", EXIT_ARGS)
    try:
        from intomd_api.main import serve as api_serve  # type: ignore[import-untyped,unused-ignore]
    except ImportError as e:
        raise fail("The API is not installed. Install intomd-api (pip install intomd-api).", EXIT_ARGS) from e
    typer.echo(f"intomd serving on http://{host}:{port}", err=True)
    api_serve(host=host, port=port)
