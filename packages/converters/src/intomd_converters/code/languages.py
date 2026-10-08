"""Language identification for code fences (docs/spec/part2.md 8b step 8).

An extension map in the spirit of `identify` (MIT) plus Magika's label (through the detected mime) and
shebang sniffing for extensionless scripts. Only names used as Markdown fence info strings live here.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

# Extension -> fence language. Lowercase keys, leading dot.
EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".vue": "vue",
    ".svelte": "svelte",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".m": "objectivec",
    ".mm": "objectivec",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".groovy": "groovy",
    ".gradle": "groovy",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".vb": "vbnet",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".pl": "perl",
    ".pm": "perl",
    ".lua": "lua",
    ".r": "r",
    ".jl": "julia",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".lisp": "lisp",
    ".el": "elisp",
    ".zig": "zig",
    ".nim": "nim",
    ".sol": "solidity",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".asm": "asm",
    ".s": "asm",
    ".sql": "sql",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".tf": "hcl",
    ".hcl": "hcl",
    ".cmake": "cmake",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".svg": "xml",
    ".json": "json",
    ".jsonc": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".diff": "diff",
    ".patch": "diff",
    ".tex": "latex",
    ".v": "verilog",
    ".vhd": "vhdl",
    ".pas": "pascal",
    ".tcl": "tcl",
    ".lock": "text",
}

# Whole file names (lowercase) -> language.
FILENAME_LANGUAGES: dict[str, str] = {
    "dockerfile": "dockerfile",
    "containerfile": "dockerfile",
    "makefile": "makefile",
    "gnumakefile": "makefile",
    "cmakelists.txt": "cmake",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "vagrantfile": "ruby",
    "jenkinsfile": "groovy",
    "build": "python",
    "workspace": "python",
    ".gitignore": "gitignore",
    ".dockerignore": "gitignore",
    ".intomdignore": "gitignore",
    "go.mod": "go",
    "go.sum": "text",
}

# Detected mime -> language, for files whose name says nothing (Magika labels, part1 5.1).
MIME_LANGUAGES: dict[str, str] = {
    "text/x-python": "python",
    "application/typescript": "typescript",
    "text/x-typescript": "tsx",
    "application/javascript": "javascript",
    "text/javascript": "javascript",
    "text/x-golang": "go",
    "text/x-go": "go",
    "application/x-rust": "rust",
    "text/x-rust": "rust",
    "text/x-c": "c",
    "text/x-h": "cpp",
    "text/x-java": "java",
    "application/x-ruby": "ruby",
    "text/x-ruby": "ruby",
    "text/x-php": "php",
    "text/x-shellscript": "bash",
    "application/x-sh": "bash",
    "text/x-swift": "swift",
    "application/x-scala": "scala",
    "text/x-perl": "perl",
    "text/x-groovy": "groovy",
    "text/x-julia": "julia",
    "text/x-lisp": "lisp",
    "text/x-clojure": "clojure",
    "text/coffeescript": "coffeescript",
    "application/x-powershell": "powershell",
    "text/x-msdos-batch": "batch",
    "text/x-asm": "asm",
    "text/x-proto": "protobuf",
    "text/x-objcsrc": "objectivec",
    "text/x-r": "r",
    "text/x-matlab": "matlab",
    "text/x-pascal": "pascal",
    "text/x-erlang": "erlang",
    "text/zig": "zig",
    "application/x-tcl": "tcl",
    "text/x-verilog": "verilog",
    "text/x-vhdl": "vhdl",
    "text/x-cmake": "cmake",
    "text/x-makefile": "makefile",
    "text/x-dockerfile": "dockerfile",
    "text/x-hcl": "hcl",
    "text/vbscript": "vbnet",
}

CODE_MIMES: tuple[str, ...] = tuple(MIME_LANGUAGES)
"""Mimes the code family owns a chain for. Never text/plain or text/markdown (text family), never data or
markup formats (json, yaml, toml, xml, html, css: other families), never application/zip (archives)."""

_SHEBANG = re.compile(r"^#!\s*(?:/usr/bin/env\s+(?:-S\s+)?)?(?:\S*/)?([A-Za-z][A-Za-z0-9._+-]*)")
_SHEBANG_LANGUAGES: dict[str, str] = {
    "python": "python",
    "python3": "python",
    "python2": "python",
    "node": "javascript",
    "nodejs": "javascript",
    "deno": "typescript",
    "bun": "javascript",
    "bash": "bash",
    "sh": "bash",
    "dash": "bash",
    "zsh": "zsh",
    "ksh": "bash",
    "fish": "fish",
    "ruby": "ruby",
    "perl": "perl",
    "php": "php",
    "lua": "lua",
    "pwsh": "powershell",
    "rscript": "r",
    "tclsh": "tcl",
}


def shebang(text: str) -> str | None:
    """The interpreter named by a `#!` first line, or None."""
    first = text.split("\n", 1)[0]
    m = _SHEBANG.match(first)
    return m.group(1).lower() if m else None


def _shebang_language(text: str) -> str | None:
    interp = shebang(text)
    if interp is None:
        return None
    base = re.sub(r"[0-9.]+$", "", interp) or interp
    return _SHEBANG_LANGUAGES.get(interp) or _SHEBANG_LANGUAGES.get(base)


def language_for(name: str, text: str = "", mime: str | None = None) -> str | None:
    """Fence language from the file name, then the detected mime, then a shebang."""
    pure = PurePosixPath(name.replace("\\", "/"))
    lower = pure.name.lower()
    if lower in FILENAME_LANGUAGES:
        return FILENAME_LANGUAGES[lower]
    if lower.startswith("dockerfile.") or lower.endswith(".dockerfile"):
        return "dockerfile"
    lang = EXTENSION_LANGUAGES.get(pure.suffix.lower())
    if lang is not None:
        return lang
    if mime is not None and mime in MIME_LANGUAGES:
        return MIME_LANGUAGES[mime]
    return _shebang_language(text) if text else None


def is_code_name(name: str) -> bool:
    """True for names whose extension or file name maps to a programming language (not prose or data)."""
    lang = language_for(name)
    return lang is not None and lang not in _NON_CODE


_NON_CODE = frozenset(
    {"gitignore", "text", "markdown", "rst", "json", "yaml", "toml", "ini", "xml", "html", "latex", "diff"}
)
