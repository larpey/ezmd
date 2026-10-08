# Writing a converter plugin

Third-party converters are ordinary Python packages that register through the `intomd.converters`
entry point group. intomd discovers them at startup; a plugin that fails to import is listed by
`intomd capabilities` as `broken.<name>` with its error and never takes the registry down.

## The Converter protocol

A converter is any object with these attributes and two methods (`intomd.registry.Converter`):

| Member | Meaning |
|---|---|
| `id` | Stable `family.engine` id, unique across all converters (for example `data.acme_csv`). |
| `family` | One of `documents`, `web`, `media`, `images`, `code`, `comms`, `data`, `notes`, `specialized`, `text`, `archives`. |
| `priority` | Tie-breaker when two converters return the same confidence; higher wins. |
| `experimental` | When true, every result gets an `experimental_converter` warning. |
| `requires_extras` | Pip extras the converter needs (informational; failed imports are reported). |
| `mimes` | Mime types it is designed for (shown by `capabilities`; wildcards allowed). |
| `can_handle(ref) -> float` | Confidence in [0, 1]. Must be cheap: use `ref.detected.mime`, `ref.display`, `ref.url`; no I/O. |
| `convert(ref, options) -> Document` | Return a finalized `Document` or raise `ConversionError`. |

Rules every converter follows:

- Return a `Document` (call `document.finalize()`) or raise `ConversionError` with a user-safe
  `user_message`. Never return an empty document silently: attach a warning such as
  `extraction_empty`.
- Give every block a `Provenance` with at least `source`; add lines, pages, or a bbox when known.
- Never shell out with `subprocess`; use `intomd.core.sandbox.run([...])`.
- Do not use the network unless `options.allow_network` is true.
- Check `options.deadline()` in long loops.

## Example

A 40-line CSV converter, `acme_csv.py`:

```python
"""acme_csv: a minimal CSV converter for intomd (example plugin)."""

from __future__ import annotations

import csv
import io

from intomd.inputs import InputRef
from intomd.ir import Document, InlineSpan, Metadata, Provenance, SourceType, Table, TableCell, Warning, WarningKind
from intomd.registry import ConversionError, ConvertOptions


class CsvTableConverter:
    id = "data.acme_csv"
    family = "data"
    priority = 10
    experimental = True  # results get an info-level experimental_converter warning
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/csv",)

    def can_handle(self, ref: InputRef) -> float:
        return 0.9 if ref.detected and ref.detected.mime == "text/csv" else 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        try:
            rows = list(csv.reader(io.StringIO(ref.read().decode("utf-8-sig"))))
        except (UnicodeDecodeError, csv.Error) as e:
            raise ConversionError(str(e), user_message="This CSV file could not be read.") from e
        meta = Metadata(source=ref.display, source_type=SourceType.DATA, mime="text/csv")
        doc = Document(metadata=meta)
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            doc.warnings.append(Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="No rows."))
            return doc.finalize()
        width = max(len(r) for r in rows)
        cells = [
            TableCell(spans=[InlineSpan(text=value)], row=i, col=j, is_header=i == 0)
            for i, row in enumerate(rows)
            for j, value in enumerate(row + [""] * (width - len(row)))
        ]
        prov = Provenance(source=ref.display, line_start=1, line_end=len(rows))
        doc.blocks.append(Table(cells=cells, n_rows=len(rows), n_cols=width, header_rows=1, provenance=prov))
        return doc.finalize()
```

Register it in the plugin's `pyproject.toml`. The entry point may name a class or a zero-argument
factory; the registry calls it once:

```toml
[project.entry-points."intomd.converters"]
acme_csv = "acme_csv:CsvTableConverter"
```

After `pip install` (or `uv pip install -e .`), check that it loaded and use it:

```sh
intomd capabilities
intomd convert trips.csv --profile compact
intomd convert trips.csv --converter data.acme_csv     # force it
```

### How the registry picks a converter

Every available converter's `can_handle` is called; those above 0 are tried in order of
confidence, then priority, then id, until one succeeds or one raises
`ConversionError(retryable_with_fallback=False)`. A mime type with a pinned chain in
`intomd.chains` (Phase 0 pins `text/plain` and `text/markdown`) only considers the converters in that
chain, so a plugin for those types runs only when forced with `--converter`. Built-in converters are
registered before plugins, and a plugin cannot reuse a built-in id.

## Fixtures

Converters are tested with golden fixtures under `fixtures/<family>/<name>/`: `input.<ext>` (or
`input.url` plus a frozen `input.html`), `expected.full.md`, `expected.sidecar.json`, and
`meta.toml`:

```toml
converter = "text.plain"          # required: the converter id this fixture exercises
threshold = 0.9                   # optional; only lower than the converter threshold, with threshold_reason
threshold_reason = "deliberately broken scan"
max_seconds = 30                  # hard failure when exceeded
hand_edited = false               # true when the golden was hand-edited after review
notes = "what this fixture tests"
expected_errors = []              # error-severity warning codes that are expected (others are hard failures)

[provenance]                       # required (part4 4.14.7)
origin = "self-generated"         # self-generated | public-domain | cc0 | cc-by
license = "CC0-1.0"
source = ""                       # URL when not self-generated
```

`fixtures/thresholds.toml` holds `default = 0.85` and per-converter thresholds under `[converters]`.
Fixtures must be public domain, CC0, CC-BY, or self-generated, with `[provenance]` filled in.

```sh
uv run intomd-golden fixtures/data/trips --write     # generate expected outputs, then review them
uv run intomd-score fixtures/data/trips              # score the converter against the golden
uv run pytest fixtures -q -k acme_csv
```

Planned: a plugin template repository and the contract test kit as a published package (Phase 1).
