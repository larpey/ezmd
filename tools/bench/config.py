"""Benchmark paths and the competitor manifest (tools/bench/competitors.toml)."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent
MANIFEST = BENCH_DIR / "competitors.toml"
RESULTS_DIR = ROOT / "bench" / "results"
WORKER = BENCH_DIR / "adapters" / "worker.py"


def cache_dir() -> Path:
    """Everything large (venvs, model weights, corpora, raw outputs) lives here, outside git."""
    return Path(os.environ.get("EZMD_BENCH_CACHE", Path.home() / ".cache" / "ezmd-bench"))


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    kind: str
    adapter: str
    formats: tuple[str, ...]
    license: str
    requirements: tuple[str, ...] = ()
    torch: bool = False
    version: str = ""
    url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def venv(self) -> Path:
        """`venv = "<dir>"` in the manifest points a tool at another environment (e.g. a candidate build)."""
        return cache_dir() / "venvs" / str(self.extra.get("venv", self.name))

    @property
    def python(self) -> Path:
        return venv_python(self.venv)

    def supports(self, suffix: str) -> bool:
        ext = suffix.lower().lstrip(".")
        return "*" in self.formats or ext in self.formats


def load_tools(path: Path | None = None) -> dict[str, Tool]:
    path = path or Path(os.environ.get("EZMD_BENCH_MANIFEST", MANIFEST))
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tools: dict[str, Tool] = {}
    for name, spec in data["tools"].items():
        known = {"kind", "adapter", "formats", "license", "requirements", "torch", "version", "url"}
        tools[name] = Tool(
            name=name,
            kind=spec["kind"],
            adapter=spec["adapter"],
            formats=tuple(spec.get("formats", ())),
            license=spec.get("license", ""),
            requirements=tuple(spec.get("requirements", ())),
            torch=bool(spec.get("torch", False)),
            version=spec.get("version", ""),
            url=spec.get("url", ""),
            extra={k: v for k, v in spec.items() if k not in known},
        )
    return tools
