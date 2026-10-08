"""The `intomd` command line (docs/spec/part1.md P0-T08, part4.md 4.2).

Phase 0 commands: convert, capabilities, detect, version, serve. Conversion runs in-process through
`intomd.pipeline.convert_ref`; URLs are fetched through the SSRF guard first.

Exit codes (part4 4.2.2): 0 success; 1 generic failure; 2 bad arguments, missing dependency, or an
error-severity warning; 4 fetch blocked by platform; 5 input too large; 6 unsupported type; 130 interrupted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from intomd import __version__
from intomd.cli.options import parse_opts, split_options

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    help="Convert anything to LLM-ready Markdown.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

EXIT_FAIL, EXIT_ARGS, EXIT_BLOCKED, EXIT_TOO_LARGE, EXIT_UNSUPPORTED = 1, 2, 4, 5, 6


def _err(msg: str) -> None:
    typer.secho(msg, err=True, fg=typer.colors.RED)


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


@app.command()
def convert(
    source: Annotated[str, typer.Argument(help="File path, URL, or '-' for stdin.")],
    profile: Annotated[str, typer.Option("--profile", "-p", help="full | compact | rag | agent")] = "full",
    fmt: Annotated[str, typer.Option("--format", "-f", help="md | json | txt")] = "md",
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Output file or directory.")] = None,
    sidecar: Annotated[
        bool, typer.Option("--sidecar/--no-sidecar", help="Write <name>.intomd.json beside --out.")
    ] = False,
    converter: Annotated[str | None, typer.Option("--converter", help="Force a converter id.")] = None,
    opt: Annotated[list[str] | None, typer.Option("--opt", help="key=value converter or profile option.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable result on stdout.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="No warnings on stderr.")] = False,
) -> None:
    """Convert one input to Markdown."""
    from intomd.core.netguard import NetguardError, ResidentialOnly, ResponseTooLarge
    from intomd.inputs import FetchRequired, InputTooLarge
    from intomd.pipeline import UnsupportedMediaType, convert_ref
    from intomd.registry import ConversionError

    try:
        options, profile_overrides = split_options(parse_opts(opt or []))
    except ValueError as e:
        _err(str(e))
        raise typer.Exit(EXIT_ARGS) from e
    status = "ok"
    code = 0
    payload: dict[str, Any] = {"source": source}
    try:
        ref = _make_ref(source)
        try:
            result = convert_ref(ref, options, converter_id=converter)
        finally:
            ref.cleanup()
        rendered = _render(result, profile, fmt, profile_overrides)
    except (UnsupportedMediaType, ConversionError, InputTooLarge, NetguardError, FetchRequired, ValueError) as e:
        if isinstance(e, UnsupportedMediaType) or (
            isinstance(e, ConversionError) and e.user_message == "This file type is not supported yet."
        ):
            code = EXIT_UNSUPPORTED
        elif isinstance(e, (InputTooLarge, ResponseTooLarge)):
            code = EXIT_TOO_LARGE
        elif isinstance(e, (ResidentialOnly, FetchRequired)):
            code = EXIT_BLOCKED
        elif isinstance(e, ValueError):
            code = EXIT_ARGS
        else:
            code = EXIT_FAIL
        message = e.user_message if isinstance(e, ConversionError) else str(e)
        if as_json:
            sys.stdout.write(json.dumps({**payload, "status": "failed", "error": message, "warnings": []}) + "\n")
        else:
            _err(f"error: {message}")
        raise typer.Exit(code) from e
    except FileNotFoundError as e:
        _err(f"error: no such file: {source}")
        raise typer.Exit(EXIT_ARGS) from e
    warnings = rendered.warnings
    if any(w.severity == "error" for w in warnings):
        status, code = "partial", EXIT_ARGS
    if out is not None:
        target = _write_out(out, source, rendered, fmt, sidecar)
        payload["out"] = str(target)
    if as_json:
        payload.update(
            status=status,
            markdown=None if out else rendered.markdown,
            tokens=rendered.tokens,
            truncated=rendered.truncated,
            warnings=[w.model_dump(mode="json") for w in warnings],
        )
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    elif out is None:
        sys.stdout.write(rendered.markdown)
    if not quiet and not as_json:
        for w in warnings:
            typer.echo(f"WARN [{w.kind}] {w.message}", err=True)
    raise typer.Exit(code)


def _make_ref(source: str) -> Any:
    from intomd.core.netguard import fetch
    from intomd.inputs import InputRef

    if source == "-":
        return InputRef.from_bytes(sys.stdin.buffer.read(), filename="stdin")
    if _is_url(source):
        res = fetch(source)
        name = Path(res.url.split("?", 1)[0].rstrip("/")).name or "index"
        ref = InputRef.from_bytes(res.body, filename=name, declared_mime=res.content_type)
        ref.kind = "url"
        ref.url = res.url
        ref.display = res.url
        return ref
    p = Path(source)
    if not p.is_file():
        raise FileNotFoundError(source)
    return InputRef.from_path(p)


def _render(result: Any, profile: str, fmt: str, overrides: dict[str, object]) -> Any:
    from intomd.render import render

    return render(result, profile, fmt, **overrides)


def _write_out(out: Path, source: str, rendered: Any, fmt: str, sidecar: bool) -> Path:
    ext = {"md": ".md", "markdown": ".md", "json": ".json", "txt": ".txt"}.get(fmt, ".md")
    if out.is_dir():
        stem = Path(source.split("?", 1)[0].rstrip("/")).stem or "output"
        target = out / f"{stem}{ext}"
    else:
        target = out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered.markdown, encoding="utf-8", newline="\n")
    if sidecar and rendered.sidecar is not None:
        sc = target.with_name(target.stem + ".intomd.json")
        sc.write_text(json.dumps(rendered.sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return target


@app.command()
def capabilities(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List registered converters and whether they loaded."""
    from intomd.registry import default_registry

    rows = [
        {
            "id": r.converter.id,
            "family": r.converter.family,
            "mimes": list(getattr(r.converter, "mimes", ())),
            "source": r.source,
            "experimental": r.converter.experimental,
            "extras": list(r.converter.requires_extras),
            "loaded": r.import_error is None,
            "error": r.import_error,
        }
        for r in default_registry().registrations()
    ]
    data = {"version": __version__, "converters": rows, "profiles": ["full", "compact", "rag", "agent"]}
    if as_json:
        typer.echo(json.dumps(data, indent=2))
        return
    from rich.console import Console
    from rich.table import Table

    t = Table("id", "family", "mimes", "source", "loaded")
    for r in rows:
        mimes = r["mimes"]
        t.add_row(
            str(r["id"]),
            str(r["family"]),
            ", ".join(mimes) if isinstance(mimes, list) else "",
            str(r["source"]),
            "yes" if r["loaded"] else "no",
        )
    Console().print(t)


@app.command()
def detect(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Show the detected content type of a file."""
    from intomd.detect import detect as run_detect
    from intomd.inputs import InputRef

    d = run_detect(InputRef.from_path(path))
    typer.echo(
        json.dumps(
            {
                "mime": d.mime,
                "confidence": round(d.confidence, 4),
                "magika_label": d.magika_label,
                "libmagic_mime": d.libmagic_mime,
                "extension_mime": d.extension_mime,
            },
            indent=2,
        )
    )


@app.command()
def version() -> None:
    """Print the intomd version."""
    typer.echo(f"intomd {__version__}")


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8080,
    public: Annotated[bool, typer.Option("--i-know-this-is-public", help="Allow binding non-loopback.")] = False,
) -> None:
    """Run the HTTP API and web UI in-process (inline queue when Redis is not configured)."""
    if host not in ("127.0.0.1", "localhost", "::1") and not public:
        _err("Refusing to bind a non-loopback address without --i-know-this-is-public.")
        raise typer.Exit(EXIT_ARGS)
    try:
        from intomd_api.main import serve as api_serve  # type: ignore[import-untyped,unused-ignore]
    except ImportError as e:
        _err("The API is not installed. Install intomd-api (pip install intomd-api).")
        raise typer.Exit(EXIT_ARGS) from e
    typer.echo(f"intomd serving on http://{host}:{port}", err=True)
    api_serve(host=host, port=port)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
