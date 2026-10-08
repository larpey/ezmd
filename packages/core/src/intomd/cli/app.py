"""The typer application: command registration and logging setup (docs/spec/part4.md 4.2)."""

from __future__ import annotations

import logging

import typer

from intomd.cli.batch import batch
from intomd.cli.convert import convert
from intomd.cli.doctor import doctor
from intomd.cli.info import capabilities, detect, serve, version
from intomd.cli.shadow import shadow_run

__all__ = ["app"]

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    help="Convert anything to LLM-ready Markdown.",
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_enable=False,
)


@app.callback()
def _setup() -> None:
    """Convert anything to LLM-ready Markdown."""
    logger = logging.getLogger("intomd")
    if not any(getattr(h, "_intomd_cli", False) for h in logger.handlers):
        from rich.logging import RichHandler

        from intomd.cli.output import err_console

        handler = RichHandler(console=err_console(), show_time=False, show_path=False, level=logging.WARNING)
        handler._intomd_cli = True  # type: ignore[attr-defined]
        logger.addHandler(handler)


app.command()(convert)
app.command()(batch)
app.command()(doctor)
app.command()(capabilities)
app.command()(detect)
app.command()(version)
app.command()(serve)
app.command(name="shadow-run")(shadow_run)
