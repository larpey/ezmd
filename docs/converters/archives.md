# Archives

Package `ezmd_converters.archives`, converter family `archives` (spec: docs/spec/part2.md section 12 steps
27-28, docs/spec/part1.md 8.2).

| Converter | Formats | Status | Engine |
|---|---|---|---|
| `archives.archive` | zip; tar, tar.gz/tgz, tar.bz2, tar.xz; single-file `.gz`/`.bz2`/`.xz`; 7z with the `7z` extra | Stable | stdlib `zipfile`, `tarfile`, `gzip`, `bz2`, `lzma`; `py7zr` (LGPL-2.1-or-later) only with `pip install 'ezmd[7z]'` |
| `archives.sevenzip` | listed as unavailable when py7zr is missing | Unavailable entry | capabilities shows the reason and the `7z` extra |

Formats are detected by magic bytes. Plain zips have no pinned chain on purpose: zip-based documents (EPUB,
DOCX, XLSX, PPTX, ODF, iWork, notebooks) are recognized by their extension or by their first member
(`mimetype`, `[Content_Types].xml`), and the archive converter steps aside for their own converters.

## Output

The archive's Document contains:

1. A summary paragraph with separate counts of files, directory entries, links, other entries (devices,
   FIFOs), and rejected entries, plus the number converted. The same counts are in `metadata.extra`
   (`archive_files`, `archive_directories`, `archive_links`, `archive_other`, `archive_rejected`, and
   `archive_entries` as their sum).
2. The directory tree as a nested list, including the members of nested archives under the archive's node.
3. A table with one row per entry (directories appear in the tree only): path, size, modified time, type,
   and what happened to it (`converted (<converter id>)`, `rejected (traversal path)`,
   `skipped (symlink to <target>; links are never followed)`, `encrypted`, `not extracted`,
   `not converted`, ...). Links are skipped conservatively even when their target is inside the archive.

Each convertible member is converted through the registry (`options.ctx.convert_child`) and attached to
`Document.children` (not inlined into the parent's blocks). Child blocks carry provenance
`source = "<archive>!<member path>"` and `path = <member path>` (an inner converter's own path is kept after
a `!`). Archives inside the archive are opened in-process and become child Documents with their own listing
and children (`outer.zip!inner.zip!file.txt`). Metadata `extra` records `archive_format`, `archive_entries`,
`archive_files`, `archive_converted`, `archive_bytes_extracted`, and `archive_compressed_bytes`.

## Limits (part1 8.2, binding)

| Limit | Default | Override |
|---|---|---|
| Total uncompressed bytes, shared by every nested archive | 500 MB | `EZMD_ARCHIVE_MAX_BYTES`, or `specialized.archive_max_total` in `ConvertOptions.extra` |
| One member held in memory | 100 MB (never above the total) | `specialized.archive_max_entry` |
| Entries | 10,000 | `specialized.archive_max_entries` |
| Nesting depth | 3 (the top archive is level 1) | `specialized.archive_max_depth` |
| Compression ratio per entry | 100:1, checked once a member has produced more than 1 MiB | fixed |

How they are enforced:

- Declared sizes are checked first: a zip whose declared total exceeds the budget, or with any entry over
  100:1, is listed but nothing is extracted (`archive_bomb_suspected`).
- Declared sizes lie, so every read counts the bytes actually produced, chunk by chunk (64 KiB), and stops
  as soon as the total, per-entry, or ratio cap is crossed. Tar streams are wrapped in a counting reader
  over the decompressor, so headers inside a compressed stream cannot hide a bomb.
- A zip whose end-of-central-directory record announces more than ten times the entry limit is refused
  before its directory is parsed. Beyond 10,000 entries the rest are dropped with `archive_truncated`
  (`detail.reason = "max_entries"`).
- Nested archives are charged to the parent's budget. An archive at depth 3 that contains another archive
  lists it as `not opened (nesting limit)` with `archive_truncated` (`detail.reason = "max_depth"`).
- Member paths are normalized (backslashes count as separators). Absolute paths, drive letters, and any
  `..` component are rejected (`archive_path_rejected`); symlinks, hard links, devices, and FIFOs are
  skipped (`archive_entry_skipped`). Nothing is ever written to disk: members are read into memory and
  handed to child conversions as in-memory inputs.
- Encrypted zip entries (and password-protected 7z archives) are listed with `archive_encrypted` and not
  extracted unless `specialized.archive_password` is set (ZipCrypto only; AES zips stay listed).
- Child conversions share the parent's deadline (part2 13.5); the converter checks it at every entry.

## Warnings

`archive_bomb_suspected` (error; `detail.reason` is `max_total`, `ratio`, `max_entries`, or `max_entry`,
plus `bytes_extracted`), `archive_truncated` (entries or depth cap, corrupt tail), `archive_path_rejected`,
`archive_entry_skipped`, `archive_encrypted`, `attachment_unconverted` (members no converter could read,
with examples), `extra_required` (7z without the extra). Warnings raised inside nested archives are also
copied to the top-level Document so they are visible in the result.

## Known limitations

- The Markdown renderers do not render `Document.children` yet, so the rendered output shows the listing
  only; converted members are in the JSON/IR result (requested as a core change).
- `.jar`/`.war`/`.apk`/`.ipa` manifests, `.iso` refusal, RAR (`rarfile` + `unrar`), and Notion/Slack export
  routing are not implemented yet; such files are treated as plain zips or left to other converters.
- The ratio cap is 100:1 per entry after the first 1 MiB; a legitimate, extremely repetitive file larger than
  that (for example a sparse disk image) is reported as a bomb.
- 7z solid archives are extracted in one pass; when any cap trips, nothing from that archive is converted.
- Modified times from zip entries are local times without a zone; they are shown as recorded.
