"""Every command shown in README.md runs (ROADMAP P1-T17).

Each ```sh or ```python block in the README is preceded by a marker comment:

    <!-- readme: run -->              every line (sh) or the whole block (python) is executed here
    <!-- readme: skip (reason) -->    reported as a skipped test with that reason (network, Docker, servers)

Runnable shell lines must be `uv run ezmd ...`; they are invoked in-process through the Typer app (the
same entry point `uv run ezmd` starts), offline, from a temporary working directory, with `fixtures/...`
arguments pointed at this checkout. Python blocks are executed with the same path rewrite.
"""

from __future__ import annotations

import contextlib
import io
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MARKER = re.compile(r"^<!-- readme: (run|skip \((?P<reason>[^)]+)\)) -->$")
FENCE = re.compile(r"^```(\w*)\s*$")
EXECUTABLE_LANGS = {"sh", "bash", "shell", "console", "python", "py"}
CLI_PREFIX = ["uv", "run", "ezmd"]


@dataclass(frozen=True, slots=True)
class Block:
    line: int
    lang: str
    body: str
    skip_reason: str | None


def blocks(text: str | None = None) -> list[Block]:
    lines = (text if text is not None else README.read_text(encoding="utf-8")).splitlines()
    out: list[Block] = []
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        lang, start = m.group(1).lower(), i
        j = i + 1
        while j < len(lines) and not lines[j].startswith("```"):
            j += 1
        if lang in EXECUTABLE_LANGS:
            prev = lines[start - 1].strip() if start > 0 else ""
            marker = MARKER.match(prev)
            if marker is None:
                raise AssertionError(f"README.md:{start + 1}: ```{lang} block has no `<!-- readme: ... -->` marker")
            out.append(Block(start + 1, lang, "\n".join(lines[start + 1 : j]), marker.group("reason")))
        i = j + 1
    return out


def _strip_comment(line: str) -> str:
    return re.sub(r"\s+#.*$", "", line).strip()


def commands() -> list[tuple[str, Block, str]]:
    """(test id, block, command or python source) for every command in the README."""
    out: list[tuple[str, Block, str]] = []
    for b in blocks():
        if b.lang in ("python", "py"):
            out.append((f"L{b.line}-python", b, b.body))
            continue
        for k, raw in enumerate(b.body.splitlines()):
            cmd = _strip_comment(raw)
            if cmd and not cmd.startswith("#"):
                slug = re.sub(r"\W+", "-", cmd.removeprefix("uv run ")).strip("-")[:48]
                out.append((f"L{b.line + 1 + k}-{slug}", b, cmd))
    return out


def _absolute_fixture(arg: str) -> str:
    return str(ROOT / arg) if arg.startswith("fixtures/") else arg


def test_every_executable_block_is_marked() -> None:
    found = blocks()
    assert found, "README.md has no shell or python blocks"
    assert any(b.skip_reason is None for b in found), "no README block is marked runnable"


def test_marker_parsing_rejects_unmarked_blocks() -> None:
    with pytest.raises(AssertionError, match="no `<!-- readme"):
        blocks("text\n```sh\nuv run ezmd version\n```\n")


CASES = commands()


@pytest.mark.parametrize(("block", "command"), [(b, c) for _, b, c in CASES], ids=[i for i, _, _ in CASES])
def test_readme_command_runs(block: Block, command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if block.skip_reason is not None:
        pytest.skip(block.skip_reason)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EZMD_ENABLE_SOCIAL", raising=False)
    if block.lang in ("python", "py"):
        source = command.replace('"fixtures/', f'"{ROOT.as_posix()}/fixtures/')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(source, f"README.md:{block.line}", "exec"), {"__name__": "__readme__"})
        assert out.getvalue().strip(), "the README python example printed nothing"
        return
    argv = shlex.split(command)
    assert argv[:3] == CLI_PREFIX, f"runnable README commands must start with `uv run ezmd`: {command}"
    from typer.testing import CliRunner

    from ezmd.cli import app

    result = CliRunner().invoke(app, [_absolute_fixture(a) for a in argv[3:]], catch_exceptions=False)
    assert result.exit_code == 0, f"`{command}` exited {result.exit_code}:\n{result.output[-2000:]}"
    assert result.output.strip(), f"`{command}` printed nothing"
