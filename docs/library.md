# Python library

The library is the product: the CLI, the API workers, and the MCP server all call it, so there is exactly one
conversion path. `import ezmd` is light; engines load on first use.

From a source checkout, run your code with `uv run python ...` (see [Install](install.md)). After the first
release: `pip install ezmd`.

## Convert

```python
import ezmd

result = ezmd.convert(
    "fixtures/office/docx-review/input.docx",
    profile="compact",
    on_progress=lambda p: print(p.stage, p.progress),
)
print(result.markdown)  # frontmatter plus body
for w in result.warnings:
    print(w.severity, w.kind, w.message)
```

`source` may be a path (`str` or `Path`), an `http(s)` URL (fetched through the SSRF guard), `bytes`, a
binary file object, or an `ezmd.inputs.InputRef`. For bytes and file objects, pass `filename=` so
detection has a name to go on; `mime=` overrides detection.

## The result

`ezmd.Result` keeps the intermediate representation, so other profiles and formats render without
converting again.

| Member | What it is |
|---|---|
| `markdown`, `body`, `frontmatter` | The rendered output (frontmatter plus body), the body alone, and the frontmatter as a dict |
| `sidecar` | The JSON sidecar as a dict, or `None` for profiles without one (`compact`) |
| `warnings` | A list of `ezmd.ir.Warning` (`kind`, `severity`, `message`, `page`, `block_id`, `count`, `detail`) |
| `ok` | `False` when any warning has severity `error` (the output may still be usable) |
| `tokens`, `truncated` | Token count and whether a token budget cut the output |
| `render(profile, format, **overrides)` | Render another profile (`full`, `compact`, `rag`, `agent`) or format (`md`, `json`, `txt`) |
| `chunks(chunk_tokens=400, overlap=0)` | RAG chunks (`ezmd.render.Chunk`: `id`, `text`, `breadcrumb`, `tokens`, pages, `block_ids`) |
| `save(path, sidecar=True)` | Write the Markdown to a file, or `<stem>.md` into an existing directory, plus `<stem>.ezmd.json` when the profile has a sidecar |
| `document` | The IR `Document` (see [Output format](output-format.md)) |

```python
rag = result.render("rag")
for chunk in result.chunks(chunk_tokens=300):
    print(chunk.id, chunk.tokens, chunk.breadcrumb)
result.save("out/report.md")  # or an existing directory: writes <stem>.md there
```

## Options

`ezmd.Options` (or a plain dict) mirrors the `options` object of `POST /v1/convert`:

```python
opts = ezmd.Options(max_pages=50, comments=False, render={"chunks.chunk_tokens": 600})
result = ezmd.convert("report.pdf", profile="rag", options=opts)
```

| Field | Default | Meaning |
|---|---|---|
| `max_pages` | 500 | Page cap for paged formats |
| `max_seconds` | 600 | Conversion deadline |
| `max_bytes` | 100 MiB | Input size cap |
| `tracked_changes`, `comments`, `formulas`, `extract_images` | `True` | What document converters keep |
| `experimental` | `True` | Allow experimental converters |
| `converter` | `None` | Force a converter id, e.g. `documents.docling_pdf` |
| `allow_private_networks` | `False` | Let URL fetches reach private and loopback addresses |
| `languages` | `[]` | Language hints |
| `extra` | `{}` | Converter options with dotted keys, e.g. `{"pdf.engine": "pdfium"}` |
| `render` | `{}` | Profile overrides with dotted keys, e.g. `{"chunks.chunk_tokens": 512}` |

Media options (`ocr`, `asr_model`, `diarize`, `max_duration_seconds`) are accepted now and take effect
when the media converters land (Phase 2).

## Many inputs, async

```python
for r in ezmd.convert_many(["a.pdf", "b.docx"], workers=4, return_exceptions=True, profile="compact"):
    print(r if isinstance(r, Exception) else r.frontmatter["title"])

result = await ezmd.convert_async("report.pdf")  # runs on a worker thread; never blocks the event loop
```

## Capabilities, plugins, and memory

- `ezmd.capabilities()` returns the registered converters (loaded or unavailable with the reason and
  the extra that would enable them), profiles, and formats; the same data as `ezmd capabilities`.
- `ezmd.register_converter(converter)` registers a converter object in-process. Packaged plugins use
  the `ezmd.converters` entry point instead; see [Writing a converter plugin](plugins.md).
- `ezmd.unload_models()` frees cached engine models.

## Errors

`convert` raises:

- `ezmd.registry.ConversionError` when no converter could produce a document (`.code` is a stable
  reason, `.user_message` is safe to show);
- `ezmd.inputs.InputTooLarge` when the input exceeds `max_bytes`;
- `ezmd.core.netguard.NetguardError` when a URL is blocked by the SSRF guard;
- `FileNotFoundError` for a missing path.

Losses that do not stop the conversion are warnings on the result, never exceptions. The codes are listed
in [Warning codes](warnings.md).
