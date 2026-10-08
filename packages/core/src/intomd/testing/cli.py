"""`intomd-score` and `intomd-golden` console scripts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from intomd.testing.fixtures import Fixture, fixtures_root, load_meta, run_fixture, write_golden

_score_app = typer.Typer(add_completion=False, help="Score one fixture (or all) against its golden.")
_golden_app = typer.Typer(add_completion=False, help="Regenerate a fixture golden.")


def _fixtures(target: Path) -> list[Fixture]:
    target = target.resolve()
    if (target / "meta.toml").exists():
        return [Fixture(path=target, meta=load_meta(target))]
    return [Fixture(path=m.parent, meta=load_meta(m.parent)) for m in sorted(target.glob("**/meta.toml"))]


@_score_app.command()
def _score(
    target: Annotated[Path, typer.Argument(help="A fixture directory or a directory of fixtures.")],
) -> None:
    root = fixtures_root(target)
    failed = 0
    for fx in _fixtures(target):
        run = run_fixture(fx, root)
        if run.score is None:
            typer.echo(f"{fx.id}: FAIL {'; '.join(run.hard_failures)}")
            failed += 1
            continue
        s = run.score.as_dict()
        status = "PASS" if run.passed else "FAIL"
        failed += status == "FAIL"
        typer.echo(
            f"{fx.id}: {status} heading={s['heading']:.3f} table={s['table']:.3f} text={s['text']:.3f} "
            f"structure={s['structure']:.3f} overall={s['overall']:.3f} threshold={run.threshold:.2f} "
            f"({run.seconds:.2f}s)"
        )
        for h in run.hard_failures:
            typer.echo(f"  hard failure: {h}")
    raise typer.Exit(1 if failed else 0)


@_golden_app.command()
def _golden(
    target: Annotated[Path, typer.Argument(help="A fixture directory.")],
    write: Annotated[bool, typer.Option("--write", help="Write expected.full.md and expected.sidecar.json.")] = False,
) -> None:
    for fx in _fixtures(target):
        if not write:
            from intomd.testing.fixtures import convert_fixture, render_full

            md, _ = render_full(convert_fixture(fx))
            sys.stdout.write(md)
            continue
        md_path, sc_path = write_golden(fx)
        typer.echo(f"wrote {md_path} and {sc_path}")
    if write:
        typer.secho(
            "Reminder: goldens need a Skeptic review (docs/spec/part1.md 2.4) before they are committed.",
            fg=typer.colors.YELLOW,
            err=True,
        )


def score() -> None:
    _score_app()


def golden() -> None:
    _golden_app()
