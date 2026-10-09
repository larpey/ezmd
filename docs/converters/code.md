# Code converters

Family `code` (docs/spec/part2.md section 8). Phase 1 ships two converters; PRs, issues, diffs, OpenAPI,
Postman, SQL schemas, config files, logs, and stack traces are later Phase 1 tasks.

| Converter | Inputs | Status |
|---|---|---|
| `code.source_file` | One source file: Magika code mimes (`text/x-python`, `application/typescript`, `application/javascript`, `text/x-golang`, `application/x-rust`, `text/x-c`, `text/x-java`, shell, Ruby, PHP, Swift, and about 30 more), and `text/plain` files whose name is a known code extension or file name (`.rs`, `.kt`, `.cs`, `Dockerfile`, ...) | Stable |
| `code.repo_pack` | A zip or tar(.gz) of a repository, selected with `--converter code.repo_pack` (a local archive, even one named `*.repo.zip` or `*.repo.tar.gz`, goes to `archives.archive` unless you ask: the archive converter outranks repo_pack's 0.95 name score). A `https://github.com/<owner>/<repo>[/tree/<ref>[/<path>]]` URL makes the converter request the codeload tarball (`FetchRequired`); the pipeline fetches it through the SSRF guard and the converter packs the result | Stable |

Fallback chains: every code mime tries `code.source_file`, then `text.plain`. The family never claims
`text/plain`, `text/markdown`, or `application/zip`; for those it relies on confidence (0.95 for a code file
name detected as `text/plain`, above `text.plain`'s 0.9).

## What a repo pack contains

1. `# <repo>` (or `# <owner>/<repo> at <ref>` for GitHub) and a summary: files packed, source bytes, cl100k tokens,
   language mix by bytes, commit sha (from the tarball's pax header), and how many files were left out and why.
2. `## Directory tree`: directories first, then files, sorted. Default-excluded directories collapse to one line
   (`node_modules/ (excluded, 1,204 files)`); rule-excluded files keep their name with the reason
   (`.env (excluded: secret file)`, `logo.png (excluded: binary)`); files dropped by the token budget show
   `(omitted: token budget)`. Gitignored files are not listed (they are not part of the repository).
3. `## Files`: README first, then root manifests and config, then source by depth and path, then `docs/`, then
   tests. Sizes (`bytes` in the heading attrs and `extra.bytes`) are source bytes; `packed_bytes` is the size of
   the emitted text. Each file is a `###` heading with its path (plus `(signatures only)` when compressed) and one fenced
   code block with `filename`, `language`, and provenance `path` plus `line_start`/`line_end`.

Filtering, in order: nested `.gitignore` and `.ezmdignore` files (gitwildmatch via pathspec; the deepest
matching rule wins, so `!negations` work), default-excluded directories (`.git`, `node_modules`, `vendor`,
`dist`, `build`, `.venv`, `venv`, `__pycache__`, tool caches), include/exclude globs, credential files,
binaries (by extension or NUL bytes; UTF-16 with a BOM is text), files over `max_file_bytes`, `*.min.js`,
`*.min.css`, `*.map`. Lockfiles are kept but cut to 50 lines. A file with any line over 2,000 characters is
treated as minified and only its first 2,000 characters are kept.

Archive safety (docs/spec/part1.md 8.2): members are read into memory, never extracted; at most 10,000 entries;
total uncompressed size `EZMD_ARCHIVE_MAX_BYTES` (500 MB); a zip entry or a gzip stream expanding more than
100:1 aborts the conversion; symlinks, hard links, devices, absolute paths, drive letters, and `..` components
are skipped; encrypted zip entries are skipped; nested archives are treated as binary and never opened.

## Secrets

Every file's text is scanned before it enters the IR. Rules (Secretlint/detect-secrets style): AWS access key
ids and secret keys, GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`), Slack tokens and
webhooks, Stripe live keys, JWTs, PEM private key blocks (redacted whole, also when unterminated), passwords
in URLs (`scheme://user:pass@host`), `Authorization: Bearer|Basic|token` values, and generic assignments to
names ending in `key`, `secret`, `token`, `password`, `passwd`, or `pwd` whose value has high Shannon entropy
(quoted: 8+ characters, entropy 3.0; unquoted: 12+ characters mixing letters and digits, not a dotted name).
Placeholders (`changeme`, `${VAR}`, `<value>`, `xxx`) are left alone. Matches become `[REDACTED:<rule>]`; a
multi-line match (a PEM block) keeps its line breaks after the marker, so line numbers in the output, in
provenance, and in the reported locations all stay in source numbering.
Credential files (`.env`, `.env.*`, `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `credentials.json`,
`.netrc`, `.pgpass`, `.pypirc`, `.npmrc`/`.yarnrc` with an auth token) are excluded from packs entirely.
Redaction cannot be turned off.

## Options

Pass with `--opt extra.<key>=<value>` (the `code.` prefix, `extra.code.<key>`, also works).

| Key | Default | Applies to | Meaning |
|---|---|---|---|
| `signatures_only` (alias `compress`) | false | both | Python via `ast`: imports, leading comments, docstrings, constants and type aliases, class and function signatures with decorators; bodies become `...`. Other languages: lines starting with `import`, `from`, `export`, `def`, `class`, `fn`, `func`, `pub`, `struct`, `interface`, `type`, `enum`, `package`, `module`, `use`, `#include`, plus the two lines after |
| `outline` | auto (on above 500 lines) | source_file | Symbol list (`name (kind) line N`) before the code |
| `token_budget` | none | repo_pack | Budget actions in order: drop lockfiles, generated, and minified files; drop tests; compress files over 300 lines; truncate every file to its first N lines (N >= 40); drop files from the deepest directories |
| `max_file_bytes` | 524288 | repo_pack | Larger files are listed but not read |
| `respect_gitignore` | true | repo_pack | Apply `.gitignore` / `.ezmdignore` |
| `include`, `exclude` | none | repo_pack | Comma-separated gitwildmatch globs |
| `tests_first` | false | repo_pack | Put test files right after the root config |
| `subpath` | none | repo_pack | Pack only this subtree (ignore files above it still apply) |

## Warnings

`secret_redacted` (counts by rule, `file:line` locations, never the value; files the token budget dropped are not
reported), `secret_file_excluded`,
`token_budget_applied` (the actions taken), `archive_entry_skipped`, `archive_encrypted`, `archive_truncated`,
`removed_hidden_elements` (bidi overrides and zero-width characters, the Trojan Source vector),
`encoding_uncertain`, `extraction_empty`.

## Known limitations

- Local directory inputs are not supported yet: the core `InputRef` has no directory kind. Zip the repository
  (`git archive --format=zip -o repo.zip HEAD`) and convert it with `--converter code.repo_pack`, or pass a
  GitHub URL.
- A local `*.repo.zip` / `*.repo.tar.gz` name is not enough to pick `code.repo_pack`: `archives.archive`
  claims every zip and tar first, so pass `--converter code.repo_pack`.
- `text/plain` is pinned to `text.plain` by the text family's chain, so a code file Magika calls `text/plain`
  (Rust, Kotlin, C#, Lua, Dart) reaches `code.source_file` only when that chain lets other candidates in or
  with `--converter code.source_file`.
- GitHub `/tree/<ref>/<path>` URLs: refs containing `/` are read as `<ref>/<path>`; the subpath is lost after
  the pipeline fetch (it is not part of the codeload URL), so pass `--opt extra.subpath=<path>` too.
- Signatures-only mode is `ast` for Python and a keyword heuristic for everything else (tree-sitter grammars are
  the planned upgrade). Indented methods in non-Python languages are not kept by the heuristic.
- Binary detection uses extensions and NUL bytes, not Magika per member. UTF-16 without a BOM counts as binary.
- GitLab, Codeberg, Bitbucket, and `git@` URLs, `include_log`, `include_diff`, and `output=separate` are not
  implemented yet.
- Token counts use tiktoken `cl100k_base`; offline installs without the BPE cache fall back to estimates.
