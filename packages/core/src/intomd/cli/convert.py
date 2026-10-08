"""`intomd convert`: one input to Markdown, in-process through `intomd.convert` or on a remote instance.

Profile default (Part 4 4.0 rule 3): an explicit `--profile` wins, then `INTOMD_PROFILE`, then
`defaults.profile` in the config file; with none of those, `compact` when Markdown goes to an interactive
terminal and `full` otherwise (`--out`, piped or redirected stdout, or `--json`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO, Annotated, Any

import typer

from intomd.cli.config import SUPPORTED_FORMATS, Config, ConfigError, check_format, check_profile, load_config
from intomd.cli.exitcodes import EXIT_ARGS, EXIT_INTERRUPTED, EXIT_OK, EXIT_PARTIAL, classify
from intomd.cli.options import library_options, parse_opts, resolve_engine
from intomd.cli.output import (
    Outcome,
    ProgressSink,
    err_console,
    failure_payload,
    outcome_from_result,
    print_warnings,
    progress_display,
    write_outcome,
)

__all__ = ["convert", "emit_json", "fail", "load_config_or_exit"]


def emit_json(payload: dict[str, object]) -> None:
    import json

    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fail(message: str, code: int = EXIT_ARGS, *, as_json: bool = False, source: str = "") -> typer.Exit:
    """Report a usage-level failure (stderr, plus a JSON object in --json mode) and return the Exit."""
    if as_json:
        emit_json(failure_payload(source, "invalid_request", message, "other", code))
    err_console().print(f"error: {message}", style="red", markup=False, highlight=False)
    return typer.Exit(code)


def load_config_or_exit(*, as_json: bool = False, quiet: bool = False) -> Config:
    try:
        cfg = load_config()
    except ConfigError as e:
        raise fail(str(e), as_json=as_json) from e
    if cfg.unknown_keys and not quiet:
        err_console().print(f"note: ignoring unknown config keys: {', '.join(cfg.unknown_keys)}", markup=False)
    return cfg


def auto_profile(out: Path | None, as_json: bool) -> str:
    return "compact" if out is None and not as_json and sys.stdout.isatty() else "full"


def build_options(cfg: Config, opt: list[str], lang: str | None, converter: str | None) -> dict[str, object]:
    options: dict[str, object] = {}
    if cfg.max_file_mb is not None:
        options["max_bytes"] = int(cfg.max_file_mb * 1024 * 1024)
    if cfg.max_duration_s is not None:
        options["max_duration_seconds"] = cfg.max_duration_s
    options.update(library_options(parse_opts(opt)))
    if lang:
        options["languages"] = [s.strip() for s in lang.split(",") if s.strip()]
    if converter:
        options["converter"] = converter
    return options


def _run_local(
    source: str, profile: str, fmt: str, options: dict[str, object], engine: str | None, sink: ProgressSink
) -> Outcome:
    import intomd.library as lib

    if engine and "converter" not in options:
        rows = lib.capabilities()["converters"]
        options = {**options, "converter": resolve_engine(engine, rows if isinstance(rows, list) else [])}
    opts = lib.Options(**options)
    src: str | IO[bytes] = sys.stdin.buffer if source == "-" else source

    def relay(p: Any) -> None:
        sink(str(p.stage), p.progress, str(p.message))

    result = lib.convert(
        src, profile=profile, options=opts, on_progress=relay, filename="stdin" if source == "-" else None
    )
    sink("rendering", None, "")
    display = "stdin" if source == "-" else source
    return outcome_from_result(result, source=display, profile=profile, fmt=fmt)


def _run_remote(
    source: str,
    remote: str,
    cfg: Config,
    profile: str,
    fmt: str,
    options: dict[str, object],
    engine: str | None,
    sink: ProgressSink,
) -> Outcome:
    from intomd.cli.remote import RemoteClient

    with RemoteClient(remote, cfg.api_key) as client:
        if engine and "converter" not in options:
            rows = client.capabilities().get("converters")
            options = {**options, "converter": resolve_engine(engine, rows if isinstance(rows, list) else [])}
        max_bytes = options.get("max_bytes")
        return client.convert(
            source,
            profile=profile,
            fmt=fmt,
            options=options,
            stdin=sys.stdin.buffer if source == "-" else None,
            max_bytes=max_bytes if isinstance(max_bytes, int) else 100 * 1024 * 1024,
            progress=sink,
        )


def convert(
    source: Annotated[str, typer.Argument(help="File path, http(s) URL, or '-' for stdin.")],
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="full | compact | rag | agent [default: auto]")
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Output file, or directory for <title>.md.")] = None,
    fmt: Annotated[str | None, typer.Option("--format", "-f", help="md | txt | json [default: md]")] = None,
    sidecar: Annotated[
        bool | None, typer.Option("--sidecar/--no-sidecar", help="Write <name>.intomd.json beside --out.")
    ] = None,
    engine: Annotated[str | None, typer.Option("--engine", help="Engine as family=name, e.g. pdf=docling.")] = None,
    converter: Annotated[str | None, typer.Option("--converter", help="Force a converter id.")] = None,
    lang: Annotated[str | None, typer.Option("--lang", help="Language hint(s), e.g. en or en,de.")] = None,
    remote: Annotated[str | None, typer.Option("--remote", help="Convert on this intomd instance.")] = None,
    opt: Annotated[list[str] | None, typer.Option("--opt", help="key=value converter or profile option.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="One JSON object on stdout.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="No progress or warnings on stderr.")] = False,
) -> None:
    """Convert one input to Markdown (stdout, or a file with --out)."""
    cfg = load_config_or_exit(as_json=as_json, quiet=quiet)
    try:
        chosen_fmt = check_format(fmt or cfg.format, "--format")
        if chosen_fmt not in SUPPORTED_FORMATS:
            raise ConfigError(f"--format {chosen_fmt} is not yet supported; use md, txt, or json")
        chosen_profile = check_profile(profile, "--profile") if profile else cfg.profile or auto_profile(out, as_json)
        options = build_options(cfg, opt or [], lang, converter)
    except ValueError as e:
        raise fail(str(e), as_json=as_json, source=source) from e
    target_remote = (remote if remote is not None else cfg.remote_url).strip()
    write_sidecar = cfg.sidecar if sidecar is None else sidecar
    initial = "fetching" if source.startswith(("http://", "https://")) or target_remote else "converting"
    target: Path | None = None
    try:
        with progress_display(not quiet and not as_json, initial) as sink:
            if target_remote:
                outcome = _run_remote(source, target_remote, cfg, chosen_profile, chosen_fmt, options, engine, sink)
            else:
                outcome = _run_local(source, chosen_profile, chosen_fmt, options, engine, sink)
        if out is not None:
            target = write_outcome(outcome, out, sidecar=write_sidecar)
    except KeyboardInterrupt:
        err_console().print("interrupted", markup=False)
        raise typer.Exit(EXIT_INTERRUPTED) from None
    except Exception as e:
        f = classify(e)
        if as_json:
            emit_json(failure_payload(source, f.code, f.message, f.warning_kind, f.exit_code))
        else:
            err_console().print(f"error: {f.message}", style="red", markup=False, highlight=False)
        raise typer.Exit(f.exit_code) from e
    code = EXIT_PARTIAL if outcome.status == "partial" else EXIT_OK
    _report(outcome, target, as_json=as_json, quiet=quiet, exit_code=code)
    raise typer.Exit(code)


def _report(outcome: Outcome, target: Path | None, *, as_json: bool, quiet: bool, exit_code: int) -> None:
    if as_json:
        emit_json(
            {
                "source": outcome.source,
                "status": outcome.status,
                "exit_code": exit_code,
                "profile": outcome.profile,
                "format": outcome.format,
                "out": str(target) if target else None,
                "markdown": None if target else outcome.text,
                "tokens": outcome.tokens,
                "truncated": outcome.truncated,
                "warnings": outcome.warnings,
            }
        )
        return
    if target is None:
        sys.stdout.write(outcome.text)
        sys.stdout.flush()
    elif not quiet:
        err_console().print(f"wrote {target}", markup=False, highlight=False)
    if not quiet:
        print_warnings(outcome.warnings)
