# Roadmap

ezmd ships in phases. Each phase is usable on its own; later phases add inputs, not breaking changes.

## Now: 0.1 (Phase 1)

The permissive core: the CLI, the Python library, the MCP server, the self-hosted API with its web UI and
Docker Compose stack, and the TypeScript SDK. Converters for PDF, Office, web pages, data files, code,
email, ebooks, archives, SEC EDGAR filings, and text. See the [converter matrix](converters/README.md).

Known gaps in 0.1: scanned and image-only PDFs get no text (OCR is Phase 2), and the default PDF engine
still splits some paragraphs on dense layouts. Install `ezmd[docs]` for layout analysis on PDFs.

## Next: media (Phase 2)

Audio, video, images, and screen recordings convert locally: speech recognition with speaker labels and
sparse timestamps, OCR for scanned documents and images, and in-browser Whisper in the web UI.

Figures on demand: a figure in a PDF becomes a placeholder in the Markdown that carries its caption and a stable
id, the cropped image goes in the ledger with its page and position, and the MCP server gets a tool that returns
one image when an agent asks for it. A model then pays for the two figures it needs instead of an image of every
page, which is what uploading the PDF itself costs (the [benchmark](benchmarks.md) measures that at about 3,000
Claude tokens a page against 1,100 to 1,700 for the converted text).

## Then: social, chat, and fetching (Phase 3)

Chat exports and social threads, URL fetch chains, a residential fetch node for sites that block data
center traffic, a browser extension, and a mobile share sheet.

## Then: the public instance (Phase 4)

A free hosted instance with abuse protection, rate limits, and published retention.

## Later: profession-specific features (Phase 5)

Features for specific professions and integrations with the tools they use, ordered by demand.

## Maybe: a native core

A Rust core for the text-layer engine (word reconstruction, heading planning, rendering) with Python bindings,
so the Python package keeps working and a single static binary, a WebAssembly build and embedding in other
languages become possible. Not a speed project: the parsing already happens in C++ (pdfium), and a whole paper
converts in about a second on a CPU. It starts when one of these happens: users ask for a CLI without a Python
install, the API needs thousands of documents a minute and the per-process cost dominates, or a profile shows
the Python reconstruction code is the bottleneck on large documents. Until then the converter fixes the
[benchmark](benchmarks.md) points at come first.

Dates are not promised. The [changelog](changelog.md) records what has shipped.
