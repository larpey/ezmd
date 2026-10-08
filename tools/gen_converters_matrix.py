"""Generate docs/converters/README.md (the converter matrix) from the built-in converter registry.

Also rewrites the generated "Converters" block of mkdocs.yml so every family page under docs/converters/
is in the site navigation. `tests/test_converters_matrix.py` fails when either file is stale.

The output must not depend on the machine it runs on, so the matrix never shows whether an engine is
installed here (that is `intomd capabilities`). It shows what the code declares:

- Install: "default" when the converter needs no extra; "extra `x`" when it needs an extra that
  `packages/converters/pyproject.toml` defines; "planned" when it names an extra that does not exist yet.
- Status: "Experimental" when the converter sets `experimental = True`; "Planned" when its extra does not
  exist yet; otherwise "Beta" (every converter is Beta until the first release, ROADMAP gate G1).
- Families behind a flag (a module-level `FLAG_ENV` and a `converters(env=...)` parameter) are documented
  with the flag switched on, and the flag is named in the notes.

Run: `uv run python tools/gen_converters_matrix.py`
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "converters" / "README.md"
MKDOCS = ROOT / "mkdocs.yml"
FIXTURES = ROOT / "fixtures"
CONVERTERS_PYPROJECT = ROOT / "packages" / "converters" / "pyproject.toml"
NAV_BEGIN = "  # BEGIN generated converters nav (tools/gen_converters_matrix.py)"
NAV_END = "  # END generated converters nav"
MAX_INLINE_MIMES = 3


@dataclass(frozen=True, slots=True)
class Row:
    id: str
    family: str
    package: str
    engine: str
    mimes: tuple[str, ...]
    install: str
    status: str
    fixtures: int
    threshold: float
    flag: str | None


def defined_extras() -> set[str]:
    data = tomllib.loads(CONVERTERS_PYPROJECT.read_text(encoding="utf-8"))
    return set(data.get("project", {}).get("optional-dependencies", {}))


def _family_converters(mod: ModuleType) -> tuple[list[Any], str | None]:
    flag = getattr(mod, "FLAG_ENV", None)
    fn = mod.converters
    if isinstance(flag, str) and "env" in inspect.signature(fn).parameters:
        return list(fn(env={flag: "1"})), flag
    return list(fn()), None


def fixture_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for meta in sorted(FIXTURES.glob("*/*/meta.toml")):
        conv = tomllib.loads(meta.read_text(encoding="utf-8")).get("converter")
        if isinstance(conv, str):
            counts[conv] = counts.get(conv, 0) + 1
    return counts


def thresholds() -> tuple[float, dict[str, float]]:
    from intomd.testing.fixtures import thresholds as load

    return load(FIXTURES)


def rows() -> list[Row]:
    import intomd_converters

    extras = defined_extras()
    counts = fixture_counts()
    default, per = thresholds()
    out: list[Row] = []
    for package in intomd_converters.family_names():
        mod = importlib.import_module(f"intomd_converters.{package}")
        convs, flag = _family_converters(mod)
        for c in convs:
            needed = tuple(getattr(c, "requires_extras", ()))
            missing = [e for e in needed if e not in extras]
            if missing:
                install, status = "planned", "Planned"
            else:
                install = ", ".join(f"extra `{e}`" for e in needed) if needed else "default"
                status = "Experimental" if c.experimental else "Beta"
            out.append(
                Row(
                    id=c.id,
                    family=c.family,
                    package=package,
                    engine=c.id.split(".", 1)[1] if "." in c.id else c.id,
                    mimes=tuple(getattr(c, "mimes", ())),
                    install=install,
                    status=status,
                    fixtures=counts.get(c.id, 0),
                    threshold=per.get(c.id, default),
                    flag=flag,
                )
            )
    return sorted(out, key=lambda r: (r.package, r.id))


def family_pages() -> list[tuple[str, str]]:
    """(title, path relative to docs/) for every family page in docs/converters/, sorted by title."""
    pages = []
    for p in sorted(TARGET.parent.glob("*.md")):
        if p.name == TARGET.name:
            continue
        m = re.search(r"^# (.+)$", p.read_text(encoding="utf-8"), re.M)
        title = m.group(1).strip() if m else p.stem
        pages.append((title.replace("`", ""), f"converters/{p.name}"))
    return sorted(pages, key=lambda t: t[0].lower())


def _page_link(package: str) -> str:
    page = TARGET.parent / f"{package}.md"
    return f"[{package}]({page.name})" if page.is_file() else package


def _mimes_cell(mimes: tuple[str, ...]) -> str:
    if not mimes:
        return "(by URL)"
    shown = ", ".join(f"`{m}`" for m in mimes[:MAX_INLINE_MIMES])
    rest = len(mimes) - MAX_INLINE_MIMES
    return f"{shown} and {rest} more" if rest > 0 else shown


def render() -> str:
    from intomd_converters import builtin_chains

    rs = rows()
    lines = [
        "# Converter matrix",
        "",
        "Generated from the built-in converter registry by `tools/gen_converters_matrix.py`; do not edit.",
        "`tests/test_converters_matrix.py` fails when this page is stale.",
        "",
        "This page lists what the code declares. Whether an engine is installed on a given machine is a",
        "runtime question: run `intomd capabilities` (or `GET /v1/capabilities`) to see each converter as",
        "loaded or unavailable with the reason, and `intomd doctor` for system programs such as LibreOffice.",
        "",
        "- **Engine** is the second half of the converter id (`family.engine`).",
        "- **Install**: `default` needs nothing beyond the base install; `extra x` needs that optional extra",
        "  of `intomd-converters`; `planned` names an extra that does not exist yet.",
        "- **Status**: `Experimental` converters add an `experimental_converter` warning to every result and",
        "  are skipped when experimental converters are disabled; `Planned` converters are registered only so",
        "  capabilities can explain why the format is not handled; every other converter is `Beta` until the",
        "  first release.",
        "- **Fixtures** counts golden fixtures under `fixtures/` that exercise the converter; **Threshold** is the",
        "  minimum golden score from `fixtures/thresholds.toml` and `fixtures/<family>/thresholds.toml`.",
        "",
        "| Converter | Family | Engine | MIME types | Install | Status | Fixtures | Threshold | Page |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rs:
        status = f"{r.status} (behind `{r.flag}`)" if r.flag else r.status
        lines.append(
            f"| `{r.id}` | {r.family} | {r.engine} | {_mimes_cell(r.mimes)} | {r.install} | {status} "
            f"| {r.fixtures} | {r.threshold:.2f} | {_page_link(r.package)} |"
        )
    flagged = sorted({r.flag for r in rs if r.flag})
    if flagged:
        lines += [
            "",
            "Converters behind a flag are off by default; they are listed here as they behave with the flag set "
            f"({', '.join(f'`{f}=1`' for f in flagged)}).",
        ]
    lines += [
        "",
        f"{len(rs)} converters, {sum(r.fixtures for r in rs)} fixtures.",
        "",
        "## Fallback chains",
        "",
        "When a converter fails with a retryable error, the next converter in the chain for that MIME type is",
        "tried (`intomd.chains`).",
        "",
        "| MIME type | Chain |",
        "|---|---|",
    ]
    for mime, ids in sorted(builtin_chains().items()):
        lines.append(f"| `{mime}` | {' then '.join(f'`{i}`' for i in ids)} |")
    lines += ["", "## MIME types by converter", ""]
    for r in rs:
        if r.mimes:
            lines.append(f"- `{r.id}`: {', '.join(f'`{m}`' for m in r.mimes)}")
        else:
            lines.append(f"- `{r.id}`: none; it claims inputs by URL pattern")
    lines += [
        "",
        "To add a converter of your own, see [Writing a converter plugin](../plugins.md).",
    ]
    return "\n".join(lines) + "\n"


def render_nav() -> str:
    body = ["  - Converters:", "      - Converter matrix: converters/README.md"]
    for title, path in family_pages():
        safe = title.replace('"', "'")
        body.append(f'      - "{safe}": {path}')
    return "\n".join([NAV_BEGIN, *body, NAV_END])


def update_mkdocs(text: str) -> str:
    pattern = re.compile(re.escape(NAV_BEGIN) + r".*?" + re.escape(NAV_END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"{MKDOCS.name}: generated converters nav markers not found")
    return pattern.sub(lambda _m: render_nav(), text)


def main() -> int:
    TARGET.write_text(render(), encoding="utf-8", newline="\n")
    MKDOCS.write_text(update_mkdocs(MKDOCS.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(rows())} converters) and the converters nav in mkdocs.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
