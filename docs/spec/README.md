# ezmd: autonomous build handoff

**Read this page first, then read Parts 1 through 4 in order before writing any code.**

This document is the complete specification for building ezmd, an open-source, Apache-2.0, self-hostable "convert anything to Markdown for AI users" tool with a free public instance. It was produced from a research pass over the 2026 landscape (document parsers, web extractors, media fetching and transcription, OCR, LLM-oriented Markdown structure, use cases by profession, competitive products, hosting and legal posture). The research report and notes are not required to build; everything needed is in this file.

## How to use this document

1. You are operating autonomously. The human will not answer questions during the build. Part 1, section 2 defines exactly when you may stop and ask (spending money, first publish of a package name, store submissions, destructive actions). For everything else, decide, record the decision in `DECISIONS.md`, and continue.
2. Start at Part 1, section 9 (Phase 0). Create the repo, then follow `ROADMAP.md` (Part 4, section 17) task by task. Keep `STATUS.md` current after every task.
3. Use the agent council pattern from Part 1 for architectural decisions and for any converter that fails its fixture threshold. Use the Red team pattern before Phase 4 ships.
4. Parts 2 and 3 are reference material for the converters and the media/output pipeline. Read the relevant section before implementing each task.
5. When every phase gate in Part 4 passes, write the final completion report described in Part 4, section 17, and stop.

## Structure

- **Part 1**: Mission, definition of done, operating rules for autonomous Claude Code, `CLAUDE.md` text, the intermediate representation (IR) code, converter interface and registry code, renderer and profile interfaces, job system and REST API contract, security baseline, and Phase 0 foundation tasks.
- **Part 2**: Every converter family (PDF, Office, Google Workspace, ebooks and text, web pages, sites, social and forums, code, communication, data, notes apps, specialized, cross-cutting) with libraries, fallback chains, build steps, IR output, failure modes, fixtures, thresholds, options, and phase.
- **Part 3**: Media acquisition (URL classification, captions-first, per-platform fallback chains, the Raspberry Pi residential fetch node, legal policy as code), transcription (ASR engines, diarization, post-processing, browser-side ASR), OCR and screen recordings, and the exact Markdown output specification (frontmatter, body grammar, tables, transcripts, the four profiles, prompt-injection handling, exports, token counting, renderer fixtures).
- **Part 4**: Interfaces (web UI, CLI, Python library, MCP server, TS SDK, browser extension, iOS Shortcut and Android share target, integrations), deployment files, public instance runbook, abuse prevention, security hardening, legal pages, test strategy, CI workflows, documentation, the phased roadmap with gates, launch checklist, definition of done, and risk register.

## Reconciliation notes (apply these where parts touch)

- Part 1 ships `DEFAULT_CHAINS` with only text entries. Part 2 populates it per family. Part 1's renderer emits an `ezmd-unrendered` fence for any block type it does not yet handle; Part 3 completes the renderer so that fence never appears in a passing fixture.
- Part 4 introduces `client: ios-shortcut` on `POST /v1/convert` (Shortcuts cannot solve Turnstile) and the input kinds `transcript_segments`, `captions_json3`, and `media_upload` for browser-side Whisper and extension uploads. Add these to the request schema and `InputRef` kinds defined in Part 1 and the classifier in Part 3.
- Part 3 makes the `agent` profile's `untrusted_content_id` deterministic by default (hash of content hash plus source) with an opt-in random salt, so byte-identical output stays cacheable. Part 1's renderer skeleton must follow Part 3 here.
- Part 2's warning code list (section 13.6) is the canonical list; Part 1's `WarningKind` enum and `docs/warnings.md` must mirror it, and Part 3's media and OCR warnings extend it.
- Where Part 2 and Part 3 both mention OCR for scanned pages, Part 3 owns the pipeline; Part 2 converters call it.
- Lengths: Parts 2 through 4 are longer than their targets because they carry per-converter build steps. Treat that detail as the plan, not as optional reading.

---

