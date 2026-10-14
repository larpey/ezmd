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

## Then: social, chat, and fetching (Phase 3)

Chat exports and social threads, URL fetch chains, a residential fetch node for sites that block data
center traffic, a browser extension, and a mobile share sheet.

## Then: the public instance (Phase 4)

A free hosted instance with abuse protection, rate limits, and published retention.

## Later: profession-specific features (Phase 5)

Features for specific professions and integrations with the tools they use, ordered by demand.

Dates are not promised. The [changelog](changelog.md) records what has shipped.
