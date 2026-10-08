"""Signatures-only (compressed) mode and symbol outlines (docs/spec/part2.md 8c steps 7 and 13).

Python goes through the stdlib `ast`: imports, the leading comment block, the module docstring, module-level
constants and type aliases, class and function signatures with decorators and docstrings; bodies become `...`.
Other languages use the spec's regex heuristic: lines starting with a declaration keyword plus the two lines
that follow. (Tree-sitter grammars are the Phase 2 upgrade; see docs/decisions/P1-T03-code.md.)
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

__all__ = ["Symbol", "outline", "signatures"]

_DECL = re.compile(
    r"^(?:import|from|export|def|class|fn|func|pub|struct|interface|type|enum|package|module|use|#include)\b"
)
_FOLLOW = 2
_ELLIPSIS = "..."


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    kind: str
    line: int


def signatures(text: str, language: str | None) -> str:
    """Compressed view of `text`. Python falls back to the regex heuristic when it does not parse."""
    if language == "python":
        try:
            return _python_signatures(text)
        except (SyntaxError, ValueError, RecursionError):
            pass
    return _regex_signatures(text)


def outline(text: str, language: str | None) -> list[Symbol]:
    """Top-level definitions (and methods of top-level classes for Python)."""
    if language == "python":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            tree = None
        if tree is not None:
            out: list[Symbol] = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    out.append(Symbol(node.name, "class", node.lineno))
                    out.extend(
                        Symbol(f"{node.name}.{sub.name}", "method", sub.lineno)
                        for sub in node.body
                        if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef)
                    )
                elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    out.append(Symbol(node.name, "function", node.lineno))
            return out
    syms: list[Symbol] = []
    for i, line in enumerate(text.split("\n"), start=1):
        m = re.match(
            r"^(?:export\s+)?(?:default\s+)?(?:pub(?:\([a-z]+\))?\s+)?(?:async\s+)?"
            r"(def|class|fn|func|function|struct|interface|type|enum|trait|impl)\s+([A-Za-z_][A-Za-z0-9_]*)",
            line,
        )
        if m:
            syms.append(Symbol(m.group(2), m.group(1), i))
    return syms


def _regex_signatures(text: str) -> str:
    lines = text.split("\n")
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _DECL.match(line):
            keep.update(range(i, min(len(lines), i + 1 + _FOLLOW)))
    return _join(lines, sorted(keep))


def _join(lines: list[str], kept: list[int]) -> str:
    out: list[str] = []
    prev = -1
    for i in kept:
        if prev >= 0 and i != prev + 1:
            out.append(_ELLIPSIS)
        out.append(lines[i])
        prev = i
    if kept and kept[-1] != len(lines) - 1 and any(s.strip() for s in lines[kept[-1] + 1 :]):
        out.append(_ELLIPSIS)
    return "\n".join(out).rstrip("\n")


def _python_signatures(text: str) -> str:
    tree = ast.parse(text)
    lines = text.split("\n")
    out: list[str] = []
    out.extend(_leading_comments(lines))
    _emit_body(tree.body, lines, out, top=True)
    return "\n".join(out).rstrip("\n")


def _leading_comments(lines: list[str]) -> list[str]:
    head: list[str] = []
    for line in lines:
        if line.startswith("#"):
            head.append(line)
        else:
            break
    return head


def _segment(lines: list[str], node: ast.stmt) -> list[str]:
    end = node.end_lineno or node.lineno
    return lines[node.lineno - 1 : end]


def _kind(node: ast.stmt, top: bool) -> str | None:
    if isinstance(node, ast.Import | ast.ImportFrom):
        return "import" if top else None
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return "def"
    if isinstance(node, ast.Assign | ast.AnnAssign | ast.TypeAlias) and _is_constant_like(node, top):
        return "const"
    return None


def _emit_body(body: list[ast.stmt], lines: list[str], out: list[str], *, top: bool) -> None:
    """Emit the kept statements of one body. A blank line separates groups of different kinds and precedes
    every definition, so the compressed view keeps the source's visual structure."""
    prev: str | None = "start" if top and out else None
    for idx, node in enumerate(body):
        kind = "doc" if idx == 0 and _is_docstring(node) else _kind(node, top)
        if kind is None:
            continue
        if prev is not None and (kind != prev or kind == "def"):
            out.append("")
        prev = kind
        if kind == "def" and isinstance(node, ast.ClassDef):
            _emit_class(node, lines, out)
        elif kind == "def" and isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _emit_def(node, lines, out)
        else:
            out.extend(_segment(lines, node))


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _is_constant_like(node: ast.Assign | ast.AnnAssign | ast.TypeAlias, top: bool) -> bool:
    if isinstance(node, ast.TypeAlias):
        return True
    if isinstance(node, ast.AnnAssign):
        return True  # annotated fields and constants are type information
    names = [t.id for t in node.targets if isinstance(t, ast.Name)]
    if not names:
        return False
    if all(n.isupper() or n == "__all__" for n in names):
        return True
    return top and _is_type_alias_value(node.value)


def _is_type_alias_value(value: ast.expr) -> bool:
    """`Foo = dict[str, int]`, `Bar = Union[A, B]`, `T = TypeVar("T")`."""
    if isinstance(value, ast.Subscript):
        return True
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return value.func.id in ("TypeVar", "NewType", "ParamSpec", "TypeVarTuple", "NamedTuple", "TypedDict")
    return False


def _header(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, lines: list[str]) -> list[str]:
    start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    first = node.body[0]
    if first.lineno == node.lineno:  # one-liner: `def f(): return 1`
        line = lines[node.lineno - 1]
        cut = line[: first.col_offset].rstrip()
        return [*lines[start - 1 : node.lineno - 1], cut]
    header = lines[start - 1 : first.lineno - 1]
    while header and (not header[-1].strip() or header[-1].lstrip().startswith("#")):
        header.pop()
    return header


def _body_indent(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, lines: list[str]) -> str:
    first = node.body[0]
    if first.lineno == node.lineno:
        return " " * (node.col_offset + 4)
    src = lines[first.lineno - 1]
    return src[: len(src) - len(src.lstrip())]


def _emit_def(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str], out: list[str]) -> None:
    header = _header(node, lines)
    indent = _body_indent(node, lines)
    if node.body[0].lineno == node.lineno:
        out.extend([*header[:-1], f"{header[-1]} {_ELLIPSIS}"])
        return
    out.extend(header)
    if _is_docstring(node.body[0]):
        out.extend(_segment(lines, node.body[0]))
    out.append(f"{indent}{_ELLIPSIS}")


def _emit_class(node: ast.ClassDef, lines: list[str], out: list[str]) -> None:
    header = _header(node, lines)
    indent = _body_indent(node, lines)
    if node.body[0].lineno == node.lineno:
        out.extend([*header[:-1], f"{header[-1]} {_ELLIPSIS}"])
        return
    out.extend(header)
    before = len(out)
    _emit_body(node.body, lines, out, top=False)
    if len(out) == before:
        out.append(f"{indent}{_ELLIPSIS}")
