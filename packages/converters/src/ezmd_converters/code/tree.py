"""Directory tree listing for repository packs (docs/spec/part2.md 8c step 5).

Directories first, then files, each sorted by name. Default-excluded directories are collapsed to one line
(`node_modules/ (excluded, 1,204 files)`); rule-excluded files carry their reason. Budget actions never
remove entries from the tree, so the reader always knows what exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["render_tree"]

_REASON_LABELS = {
    "secret_file": "excluded: secret file",
    "binary": "excluded: binary",
    "minified": "excluded: minified",
    "too_large": "excluded: too large",
}


@dataclass(slots=True)
class _Node:
    dirs: dict[str, _Node] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    """File name -> annotation ('' when packed)."""
    collapsed: int | None = None


def render_tree(root_name: str, files: list[tuple[str, str]], excluded_dirs: dict[str, int]) -> str:
    """`files` holds (path, annotation) pairs; `excluded_dirs` maps directory path -> file count."""
    root = _Node()
    for path, note in files:
        *dirs, name = path.split("/")
        node = root
        for d in dirs:
            node = node.dirs.setdefault(d, _Node())
        node.files[name] = note
    for path, count in excluded_dirs.items():
        node = root
        for d in path.split("/"):
            node = node.dirs.setdefault(d, _Node())
        node.collapsed = count
    lines = [f"{root_name}/"]
    _walk(root, "", lines)
    return "\n".join(lines)


def _walk(node: _Node, prefix: str, lines: list[str]) -> None:
    entries: list[tuple[str, _Node | None, str]] = [(n, node.dirs[n], "") for n in sorted(node.dirs)]
    entries.extend((n, None, node.files[n]) for n in sorted(node.files))
    for i, (name, child, note) in enumerate(entries):
        last = i == len(entries) - 1
        branch = "└── " if last else "├── "
        if child is None:
            label = _REASON_LABELS.get(note, note)
            lines.append(f"{prefix}{branch}{name}" + (f" ({label})" if label else ""))
            continue
        if child.collapsed is not None and not child.dirs and not child.files:
            noun = "file" if child.collapsed == 1 else "files"
            lines.append(f"{prefix}{branch}{name}/ (excluded, {child.collapsed:,} {noun})")
            continue
        lines.append(f"{prefix}{branch}{name}/")
        _walk(child, prefix + ("    " if last else "│   "), lines)
