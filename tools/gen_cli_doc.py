"""Generate docs/cli.md from the `ezmd` typer app (a test asserts the committed file is current).

Help text is captured with typer's CliRunner with Rich formatting disabled and a fixed terminal
width, so the output is the same on every machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
import typer.core
import typer.main
from typer.testing import CliRunner

from ezmd.cli import app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "cli.md"
WIDTH = 100
FENCE = "`" * 3

EXIT_CODES = [
    ("0", "Success."),
    ("1", "Generic failure (the converter failed)."),
    ("2", "Bad arguments, missing file, or missing dependency."),
    ("3", "Partial success: a usable result with an error warning, or batch failures with --continue-on-error."),
    ("4", "The fetch was blocked by platform policy (residential-only host or fetch required)."),
    ("5", "Input too large."),
    ("6", "Unsupported input type."),
    ("130", "Interrupted."),
]


def _help(args: list[str]) -> str:
    previous = typer.core.HAS_RICH
    typer.core.HAS_RICH = False
    try:
        result = CliRunner().invoke(
            app,
            [*args, "--help"],
            prog_name="ezmd",
            env={"COLUMNS": str(WIDTH), "NO_COLOR": "1"},
            terminal_width=WIDTH,
        )
    finally:
        typer.core.HAS_RICH = previous
    if result.exit_code != 0:
        raise SystemExit(f"ezmd {' '.join(args)} --help exited {result.exit_code}: {result.output}")
    return "\n".join(line.rstrip() for line in result.output.strip("\n").splitlines())


def commands() -> list[str]:
    group = typer.main.get_command(app)
    return list(getattr(group, "commands", {}))


def render() -> str:
    lines = [
        "# CLI reference",
        "",
        "Generated from the `ezmd` typer app by `tools/gen_cli_doc.py`; do not edit by hand.",
        "In a source checkout run commands as `uv run ezmd ...`.",
        "",
        "## ezmd",
        "",
        FENCE + "text",
        _help([]),
        FENCE,
    ]
    for name in commands():
        lines += ["", f"## ezmd {name}", "", FENCE + "text", _help([name]), FENCE]
    lines += ["", "## Exit codes", "", "| Code | Meaning |", "|---|---|"]
    lines += [f"| {code} | {meaning} |" for code, meaning in EXIT_CODES]
    lines += [
        "",
        "`--opt key=value` is repeatable. A `ConvertOptions` field name (such as `max_pages` or `ocr`) sets",
        "that converter option, `extra.<key>` sets a family-specific converter option, and any other key is",
        "a profile override (for example `--opt chunk_tokens=600` or `--opt tables.max_pipe_rows=100`).",
        "See [Output format](output-format.md) for the profile options.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(commands())} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
