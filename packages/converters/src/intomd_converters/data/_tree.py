"""Render parsed nested data (JSON, YAML, TOML, XML-as-tree) as IR blocks.

Layout rules (docs/spec/part2.md 10c step 3, adapted):
- a mapping's scalar members (and short lists of scalars) form a two-column Key/Value `Table`;
- each nested member gets a `Heading` one level down and is rendered recursively;
- an array of objects is a records `Table` (nested objects flattened by dot path to `schema_depth`, deeper
  values as compact JSON), sampled to head + tail rows beyond `max_rows` with `rows_sampled`;
- an array of scalars is a bullet `ListBlock`; anything else is pretty-printed JSON in a `Code` block;
- below H6 the remaining subtree is a `Code` block, so nothing is dropped.

Before rendering, `clip()` copies the value iteratively with a depth cap (`depth_truncated`) and a node budget
(`size_cap`), which also neutralizes YAML alias bombs and self-referencing anchors.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from intomd.context import ConvertContext
from intomd.core.textclean import CleanStats, clean_text
from intomd.ir import (
    Block,
    CodeBlock,
    ColumnType,
    Heading,
    InlineSpan,
    ListBlock,
    ListItem,
    Paragraph,
    Table,
    Warning,
    WarningKind,
)
from intomd_converters.data._common import (
    ELLIPSIS,
    CellValue,
    DataOptions,
    RawNumber,
    cell_value,
    columns_truncated_warning,
    display_text,
    is_scalar,
    kv_table,
    make_table,
    mark_sampled,
    merge_types,
    prov,
    rows_sampled_warning,
    sample_indexes,
    scalar_text,
    to_json,
    value_type,
)

MAX_HEADING_LEVEL = 6
OTHER_KEYS = "Other keys"
INLINE_LIST_ITEMS = 10
INLINE_LIST_CHARS = 120

PathFn = Callable[[str, str], str]
IndexFn = Callable[[str, int], str]


def pointer_child(parent: str, key: str) -> str:
    """JSON pointer (RFC 6901) of `key` under `parent`; the root pointer is shown as "/"."""
    token = key.replace("~", "~0").replace("/", "~1")
    return ("" if parent == "/" else parent) + "/" + token


def pointer_index(parent: str, index: int) -> str:
    return ("" if parent == "/" else parent) + f"/{index}"


@dataclass(slots=True)
class ClipResult:
    value: Any
    depth: int
    nodes: int
    depth_cut: int
    node_cut: bool


def _leaf(value: object) -> object:
    if is_scalar(value):
        return value
    if isinstance(value, dt.datetime) and value.utcoffset() == dt.timedelta(0):
        return value.replace(tzinfo=None).isoformat() + "Z"
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, bytes | bytearray):
        return f"<binary {len(value)} bytes>"
    return str(value)


def clip(value: object, *, max_depth: int, max_nodes: int) -> ClipResult:
    """Iterative deep copy into plain dict/list/scalar values with a depth cap and a node budget."""
    holder: list[Any] = [None]
    stack: list[tuple[object, Any, Any, int]] = [(value, holder, 0, 1)]
    nodes = depth = depth_cut = 0
    node_cut = False
    while stack:
        src, parent, key, level = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            parent[key] = ELLIPSIS
            node_cut = True
            continue
        if isinstance(src, dict):
            if level > max_depth:
                parent[key] = ELLIPSIS
                depth_cut += 1
                continue
            depth = max(depth, level)
            dst_map: dict[str, Any] = {str(k): None for k in src}
            parent[key] = dst_map
            stack.extend((v, dst_map, str(k), level + 1) for k, v in reversed(list(src.items())))
        elif isinstance(src, list | tuple):
            if level > max_depth:
                parent[key] = ELLIPSIS
                depth_cut += 1
                continue
            depth = max(depth, level)
            dst_list: list[Any] = [None] * len(src)
            parent[key] = dst_list
            stack.extend((v, dst_list, i, level + 1) for i, v in reversed(list(enumerate(src))))
        else:
            parent[key] = _leaf(src)
    return ClipResult(holder[0], depth, nodes, depth_cut, node_cut)


def clip_warnings(res: ClipResult, opts: DataOptions) -> list[Warning]:
    out: list[Warning] = []
    if res.depth_cut:
        out.append(
            Warning(
                kind=WarningKind.DEPTH_TRUNCATED,
                message=f"Values nested deeper than {opts.max_depth} levels were replaced with {ELLIPSIS}.",
                count=res.depth_cut,
                detail={"max_depth": opts.max_depth},
            )
        )
    if res.node_cut:
        out.append(
            Warning(
                kind=WarningKind.SIZE_CAP,
                message=f"Only the first {opts.max_nodes:,} values were converted; the rest were replaced with "
                f"{ELLIPSIS}. Raise data.max_nodes to include more.",
                detail={"max_nodes": opts.max_nodes},
            )
        )
    return out


SHARED_KEYS = 0.6
"""Arrays of objects are records when the keys every item has make up over 60% of all keys (10c step 2)."""


def is_records(value: object, min_items: int = 1) -> bool:
    if not isinstance(value, list) or not value or len(value) < min_items:
        return False
    if not all(isinstance(v, dict) for v in value):
        return False
    keysets = [set(v) for v in value]
    union: set[str] = set().union(*keysets)
    if not union:
        return False
    common = set.intersection(*keysets)
    return len(common) == len(union) or len(common) / len(union) > SHARED_KEYS


def _inline(value: object) -> bool:
    if is_scalar(value):
        return True
    if isinstance(value, dict | list) and not value:
        return True
    if isinstance(value, list) and len(value) <= INLINE_LIST_ITEMS and all(is_scalar(v) for v in value):
        return len(to_json(value)) <= INLINE_LIST_CHARS
    return False


def flatten(record: dict[str, Any], depth: int, prefix: str = "", level: int = 1) -> dict[str, Any]:
    """Dot-path flatten of nested objects up to `depth` levels; deeper values stay as containers."""
    out: dict[str, Any] = {}
    for k, v in record.items():
        name = f"{prefix}{k}"
        if isinstance(v, dict) and v and level < depth:
            out.update(flatten(v, depth, name + ".", level + 1))
        else:
            out[name] = v
    return out


@dataclass(slots=True)
class TreeBuilder:
    source: str
    opts: DataOptions
    ctx: ConvertContext
    child_path: PathFn = pointer_child
    index_path: IndexFn = pointer_index
    blocks: list[Block] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    stats: CleanStats = field(default_factory=CleanStats)
    typed_strings: bool = False
    """Type string values like CSV cells (XML, where every value is text)."""
    min_records: int = 1
    """Smallest array of objects rendered as a records table (XML: over 5 repeats, 10c step 9)."""
    _ticks: int = 0

    def _tick(self) -> None:
        self._ticks += 1
        if self._ticks % 500 == 0:
            self.ctx.check_deadline()

    def heading(self, level: int, text: str, path: str) -> None:
        self.blocks.append(
            Heading(
                level=level,
                spans=[InlineSpan(text=clean_text(text, self.stats) or "(empty key)")],
                provenance=prov(self.source, path),
            )
        )

    def paragraph(self, text: str, path: str) -> None:
        self.blocks.append(Paragraph(spans=[InlineSpan(text=text)], provenance=prov(self.source, path)))

    def code(self, value: object, path: str) -> None:
        text = clean_text(to_json(value, indent=2, max_depth=self.opts.max_depth), self.stats)
        self.blocks.append(CodeBlock(code=text, language="json", provenance=prov(self.source, path)))

    def emit(self, value: object, path: str, level: int, name: str = "") -> None:
        """Render `value` (already clipped) whose child headings start at `level`. `name` is the key the value
        sits under; it titles the items of an array of objects that is not rendered as a table."""
        self._tick()
        if isinstance(value, dict):
            if not value:
                self.paragraph("(empty object)", path)
            elif level > MAX_HEADING_LEVEL and not all(_inline(v) for v in value.values()):
                self.code(value, path)
            else:
                self.mapping(value, path, level)
        elif isinstance(value, list):
            if not value:
                self.paragraph("(empty list)", path)
            elif is_records(value, self.min_records):
                self.records(value, path)
            elif all(is_scalar(v) for v in value):
                self.scalar_list(value, path)
            elif all(isinstance(v, dict) for v in value) and level <= MAX_HEADING_LEVEL:
                for i, item in enumerate(value):
                    child = self.index_path(path, i)
                    self.heading(level, f"{name or 'item'} {i + 1}", child)
                    self.emit(item, child, level + 1)
            else:
                self.code(value, path)
        else:
            self.paragraph(cell_value(value, self.stats).text, path)

    def mapping(self, value: dict[str, Any], path: str, level: int) -> None:
        """Members in source order: each run of consecutive inline members becomes one Key/Value table at
        its position, each nested member a heading followed by its content. A run that follows a nested
        section gets its own heading at the nested members' level (the key for a single member, "Other keys"
        for several), so it is never attributed to the section above it."""
        run: list[tuple[str, str, CellValue]] = []
        nested = False

        def flush() -> None:
            if not run:
                return
            if nested:
                if len(run) == 1:
                    self.heading(level, run[0][0], self.child_path(path, run[0][1]))
                else:
                    self.heading(level, OTHER_KEYS, path)
            rows = [(k, cv) for k, _raw, cv in run]
            self.blocks.append(kv_table(rows, prov(self.source, path)))
            run.clear()

        for k, v in value.items():
            if _inline(v):
                run.append((clean_text(k, self.stats), k, cell_value(v, self.stats)))
                continue
            flush()
            nested = True
            child = self.child_path(path, k)
            self.heading(level, k, child)
            self.emit(v, child, level + 1, name=k)
        flush()

    def scalar_list(self, value: list[Any], path: str) -> None:
        keep, omitted = sample_indexes(len(value), self.opts)
        items = [
            ListItem(
                spans=[InlineSpan(text=cell_value(value[i], self.stats).text)],
                provenance=prov(self.source, self.index_path(path, i)),
            )
            for i in keep
        ]
        block = ListBlock(items=items, provenance=prov(self.source, path))
        self.blocks.append(block)
        if omitted:
            head = self.opts.head_rows
            block.attrs = {"rows_total": str(len(value)), "rows_omitted": str(omitted), "omitted_after_row": str(head)}
            self.paragraph(
                f"(Sample: items 1 to {head:,} and the last {len(keep) - head:,} of {len(value):,}; "
                f"{omitted:,} items omitted after item {head:,}.)",
                path,
            )
            self.warnings.append(rows_sampled_warning(f"The list at {path}", len(value), omitted, self.opts))

    def records(self, value: list[dict[str, Any]], path: str) -> None:
        keep, omitted = sample_indexes(len(value), self.opts)
        flat = [flatten(value[i], self.opts.schema_depth) for i in keep]
        columns: dict[str, None] = {}
        for row in flat:
            for k in row:
                columns.setdefault(k, None)
        names = list(columns)
        if len(names) > self.opts.max_cols:
            self.warnings.append(columns_truncated_warning(f"The table at {path}", len(names), self.opts.max_cols))
            names = names[: self.opts.max_cols]
        rows: list[list[CellValue]] = []
        types: list[list[ColumnType | None]] = [[] for _ in names]
        for n, row in enumerate(flat):
            if n % 1000 == 0:
                self.ctx.check_deadline()
            cells: list[CellValue] = []
            for c, col in enumerate(names):
                if col not in row:
                    cells.append(CellValue(""))
                    continue
                v = row[col]
                types[c].append(value_type(v, typed_strings=self.typed_strings) if is_scalar(v) else "text")
                cells.append(cell_value(v, self.stats, max_depth=self.opts.max_depth))
            rows.append(cells)
        header = [clean_text(n, self.stats) for n in names]
        table = make_table(header, rows, prov(self.source, path), column_types=[merge_types(t) for t in types])
        self.blocks.append(table)
        if omitted:
            self.blocks.append(mark_sampled(table, total=len(value), omitted=omitted, after_row=self.opts.head_rows))
            self.warnings.append(rows_sampled_warning(f"The array at {path}", len(value), omitted, self.opts))


def describe(value: object) -> str:
    if isinstance(value, dict):
        return f"object with {len(value):,} keys"
    if isinstance(value, list):
        if is_records(value):
            return f"array of {len(value):,} records"
        return f"array of {len(value):,} items"
    return "scalar value"


# ---------------------------------------------------------------------------
# Schema summary (10c step 2): per generalized path, types, count, null rate, examples
# ---------------------------------------------------------------------------

SCHEMA_EXAMPLES = 3
SCHEMA_EXAMPLE_CHARS = 40


def json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, RawNumber):
        return "integer" if value.lstrip("-+").isdigit() else "number"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


@dataclass(slots=True)
class _PathStats:
    count: int = 0
    nulls: int = 0
    types: dict[str, None] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)


def schema_table(value: object, source: str, opts: DataOptions, stats: CleanStats) -> tuple[Table, int]:
    """Schema `Table` (Path, Types, Count, Null %, Examples) over generalized JSON pointers (`*` stands for
    every array index), walking at most `schema_sample` values per path. Returns the table and the number
    of paths left out beyond `schema_max_paths`."""
    paths: dict[str, _PathStats] = {}
    stack: list[tuple[object, str]] = [(value, "/")]
    while stack:
        node, path = stack.pop()
        st = paths.setdefault(path, _PathStats())
        if st.count >= opts.schema_sample:
            continue
        st.count += 1
        st.types.setdefault(json_type(node), None)
        if node is None:
            st.nulls += 1
        elif is_scalar(node) and len(st.examples) < SCHEMA_EXAMPLES:
            text = scalar_text(node)
            if len(text) > SCHEMA_EXAMPLE_CHARS:
                text = text[: SCHEMA_EXAMPLE_CHARS - 1] + ELLIPSIS
            if text not in st.examples:
                st.examples.append(text)
        if isinstance(node, dict):
            stack.extend((v, pointer_child(path, str(k))) for k, v in reversed(list(node.items())))
        elif isinstance(node, list):
            stack.extend((v, pointer_child(path, "*")) for v in reversed(node))
    items = list(paths.items())
    shown, left = items[: opts.schema_max_paths], max(0, len(items) - opts.schema_max_paths)
    rows = [
        [
            display_text(p, stats),
            CellValue(", ".join(st.types)),
            CellValue(str(st.count)),
            CellValue(f"{100 * st.nulls / st.count:.0f}"),
            display_text(", ".join(st.examples), stats),
        ]
        for p, st in shown
    ]
    table = make_table(
        ["Path", "Types", "Count", "Null %", "Examples"],
        rows,
        prov(source, "/"),
        column_types=["text", "text", "int", "int", "text"],
    )
    return table, left


def emit_schema_and_data(builder: TreeBuilder, value: object, *, data_level: int = 3) -> None:
    """`## Schema` with the schema table, then `## Data` with the value rendered below it (10c step 3)."""
    source = builder.source
    builder.heading(2, "Schema", "/")
    table, left = schema_table(value, source, builder.opts, builder.stats)
    builder.blocks.append(table)
    if left:
        builder.paragraph(f"({left:,} more paths not shown; raise data.schema_max_paths to list them.)", "/")
    builder.heading(2, "Data", "/")
    builder.emit(value, "/", data_level)
