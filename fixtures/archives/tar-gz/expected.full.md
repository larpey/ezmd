---
title: "input.tar.gz"
source: "input.tar.gz"
source_type: archive
converter: archives.archive
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 108
tokens: {o200k_base: 297, cl100k_base: 294, claude_approx: 321}
content_hash: "sha256:9f422c4a06bdf331eb833ea32250b69ed4888c5fb08b23a04f80890823f93e23"
source_hash: "sha256:5b6cd0dd32bd83c9bec5e63bd32ec6da18c5cc85927aa3726ea8e1eb7de72f42"
truncated: false
warnings: [archive_entry_skipped]
injection_risk: none
extra:
  archive_bytes_extracted: 177
  archive_compressed_bytes: 298
  archive_converted: 2
  archive_directories: 0
  archive_entries: 3
  archive_files: 2
  archive_format: tar.gz
  archive_links: 1
  archive_other: 0
  archive_rejected: 0
---
# input.tar.gz {#doc}

Archive input.tar.gz: 3 entries (2 files, 0 directories, 1 link, 0 other entries, 0 rejected); 2 converted. Links are listed but never followed, even when they point inside the archive.

- kit/
    - README.md
    - data/
        - notes.txt
    - latest.txt

**Table 1**
Columns: Path, Size, Modified, Type, Converted

| Path | Size | Modified | Type | Converted |
|---|---:|---|---|---|
| kit/README.md | 112 | 2024-05-01 12:00 | text/markdown | converted (text.markdown_passthrough) |
| kit/data/notes.txt | 65 | 2024-05-01 12:00 | text/plain | converted (text.plain) |
| kit/latest.txt |  | 2024-05-01 12:00 | symlink | skipped (symlink to data/notes.txt; links are never followed) |

## 1 kit/README.md: Survey Kit {#sec-1}

This archive holds the field survey kit.

- `notes.txt`: raw notes
- `docs/method.md`: the method

## 2 kit/data/notes.txt {#sec-2}

Tuesday: 14 herons at the east marsh.

Wednesday: fog, no count.
