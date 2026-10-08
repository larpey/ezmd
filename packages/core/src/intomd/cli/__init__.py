"""The `intomd` command line (docs/spec/part4.md 4.2).

Commands: convert, batch, doctor, capabilities, detect, version, serve. Every command is a thin client
over the library (`intomd.convert`, `intomd.capabilities`) or, with `--remote`, the REST API.

Exit codes (part4 4.2.2): 0 success; 1 generic failure; 2 bad arguments or missing dependency; 3 partial
success (a usable result that carries an error-severity warning, D-0017; or a batch with failures under
--continue-on-error); 4 fetch blocked by platform; 5 input too large; 6 unsupported type; 130 interrupted.
"""

from __future__ import annotations

from intomd.cli.app import app
from intomd.cli.exitcodes import (
    EXIT_ARGS,
    EXIT_BLOCKED,
    EXIT_FAIL,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_TOO_LARGE,
    EXIT_UNSUPPORTED,
)

__all__ = [
    "EXIT_ARGS",
    "EXIT_BLOCKED",
    "EXIT_FAIL",
    "EXIT_INTERRUPTED",
    "EXIT_OK",
    "EXIT_PARTIAL",
    "EXIT_TOO_LARGE",
    "EXIT_UNSUPPORTED",
    "app",
    "main",
]


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
