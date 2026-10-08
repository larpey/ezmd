# P1-core-renderer decisions: core changes requested by the Phase 1 converter families

No new dependencies. No new warning codes. IR schema stays `"1.1"`; every IR change is additive.

## IR (packages/core/src/intomd/ir.py)

1. `Document.sidecar_extra: dict[str, list[dict[str, str | int | float | bool | None]]]` (default `{}`).
   Written verbatim by the sidecar under each key. Keys in `RESERVED_SIDECAR_KEYS` (every built-in sidecar
   key plus `children`, `adapter_trace`, `engine_trace` from Part 3 section 13) raise `ValueError` in
   `finalize()` and again at render time (children are checked too, since they may not be finalized
   by the same code path). Excluded from the sidecar `document` dump to avoid duplication.
2. `InlineSpan.change: "insert" | "delete" | None`, `change_author`, `change_id`: inline tracked changes.
   `drop` mode shows the accepted text for inline changes (dropping inserted text would lose content;
   anchored `TrackedChange` blocks keep their existing `drop` behavior).
3. `Metadata.slides: int | None` and `Metadata.sheets: list[str]` (Part 3 section 13). The frontmatter
   prefers them over counting `Slide` blocks / the legacy `extra["sheets"]` comma string.
4. `Document.counts().links` counts inline links (`InlineSpan.href`; consecutive spans with the same href
   count once) as well as `Link` blocks. Helpers `block_spans()` and `inline_link_count()` are exported.

## Renderer

5. **Children.** `render/children.py` flattens `Document.children` into the parent block list before
   rendering, so numbering, anchors, footnotes, page markers, chunking, compact and txt all work unchanged.
   Child block ids are prefixed (`c1-`, `c1.2-`) so nothing collides; a synthetic section heading (attr
   `intomd_child_section`) carries the child path and is exempt from source-number and punctuation
   stripping. The child title H1 (and a matching `role="title"` paragraph) is consumed by the section
   heading, per the task brief; Part 2 step 28 says "blocks shifted down one level", which we read as the
   child's H2 sitting one level below the path heading. Child heading levels map to
   `min(6, depth + max(level, 2) - 1)` so they always nest under their section. Page markers restart at a
   child section, and a child's own source type decides page vs slide/sheet markers. `rag` never merges
   short sections across children (Part 3 section 17 rule 2 amended so chunks stay self-contained per
   child). Unreferenced child footnotes still go to the document end like any unreferenced footnote.
   `truncated` is also set when any child Document is truncated.
6. **Frontmatter `source_type: archive`.** The Part 3 enum is amended with `archive` for
   `SourceType.ARCHIVE`, as it was with `text` and `markdown` (D-0017 item 5). Should be appended to
   `DECISIONS.md` by the orchestrator (this branch does not own it).
7. **Preamble footnotes** are flushed at the first heading of any level (they used to fall through to the
   document end because the preamble sat at level 1).
8. **Definition lists** (`ListBlock.attrs["kind"] = "definition"`): `**term**` plus definitions as lazy
   continuation lines indented four spaces, no blank line between term and definitions. A blank line would
   turn four-space-indented text into a CommonMark indented code block; continuation lines are inert.
9. **Hidden text.** `removed_hidden_elements` `detail["hidden_text"]` (each capped at 10 KB again by the
   renderer) is passed to the scanner only. Hidden findings carry `hidden: true` (every finding now has the
   key), severity raised one level (Part 3 18 phase 1) and double weight (Part 3 18 scoring). Both rules
   are applied as written, so any hidden match at low severity or above makes risk `high`.
10. **`counts.removed_nonprinting`** sums `invisible_chars`, else `control + invisible + surrogates`, else
    0, never the warning `count` (web counts elements there). Consequence: the text family's Markdown
    converter, which reports only `count`, now contributes 0 (its fixtures have none). Change request: it
    should add the same `detail` keys as `text.plain`.
11. **`counts.furniture_removed`** adds the `count` of `removed_running_header_footer` warnings.
12. **Token budget** counts page 1's head blocks against `max_tokens`; when they alone exceed it, Contents
    is dropped on that page. The trailing truncation note is still outside the budget.
13. **Table cells.** Pipe and KV cells already used inline Markdown; they now skip line-start escaping
    (`#REF!` verbatim). Minimal HTML tables keep plain-text cells: Part 3 15 rule 3 says "cells plain text"
    and allows only structural tags, so no `<code>`/`<strong>` there. `Table.attrs["header_synthesized"]`
    triggers the synthesized-header note.
14. **Hidden sheets/slides** get ` (hidden)`; slide notes go under a `Notes` heading one level below the
    slide (unnumbered, no HeadingInfo, so not in Contents and not a chunk boundary). The orientation line
    reports `N slides` and omits the page count when slides exist.

## Detection and registry

15. Magika labels `ipynb`, `sqlite`, `parquet` and extensions `.sqlite`, `.sqlite3`, `.db`, `.parquet`
    map to `application/x-ipynb+json`, `application/vnd.sqlite3`, `application/vnd.apache.parquet`
    (libmagic's `application/x-sqlite3` is an alias). Only the notebook mime is textual.
16. OOXML macro/template/slideshow variants (`.docm .dotx .dotm .xlsm .xltx .xltm .pptm .potx .potm .ppsx
    .ppsm`) have explicit extension mimes and share a family with the base type (`detect.same_family`),
    so the pipeline no longer warns `misnamed_file` / `content_type_mismatch` for them. `text/rtf` and
    `application/x-rtf` alias to `application/rtf`.
17. When no converter is available but `Unavailable` registrations would have claimed the mime (their
    `mimes`, or the mime's chain names them), `ConverterRegistry.convert` raises `ConversionError` whose
    `user_message` gives the reason, the code in parentheses and the extra to install (or the code's
    suggestion), with `code` set to the reason's warning code when the reason is or contains one.

## Fixture harness

18. `meta.toml` `requires = ["docs"]` (probe map `docs -> docling`, `data -> pyarrow`, `7z -> py7zr`;
    unknown extras skip with a reason) and `requires_modules = ["pyarrow"]`. The pytest plugin skips and
    `intomd-score` prints `SKIP <reason>` (not a failure). Layout stays `fixtures/<family>/<name>`.

## Goldens

No `fixtures/text` golden changed (all four fixtures pass unchanged; `plain-utf8-bom` still reports
`removed_nonprinting: 1` through `detail.invisible`).
