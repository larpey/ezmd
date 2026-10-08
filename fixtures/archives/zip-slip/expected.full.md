---
title: "input.zip"
source: "input.zip"
source_type: archive
converter: archives.archive
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 75
tokens: {o200k_base: 226, cl100k_base: 224, claude_approx: 244}
content_hash: "sha256:33df32c20619ddb5b2f09d28250bdb1cba96c469f3fdd301fbbc34db171059df"
source_hash: "sha256:94627df82e6cb945169490dc96182ed1e7d7c26e7cc5e2a9b33287e009ab91f7"
truncated: false
warnings: [archive_path_rejected]
injection_risk: none
extra:
  archive_bytes_extracted: 43
  archive_compressed_bytes: 556
  archive_converted: 1
  archive_directories: 0
  archive_entries: 4
  archive_files: 1
  archive_format: zip
  archive_links: 0
  archive_other: 0
  archive_rejected: 3
---
# input.zip {#doc}

Archive input.zip: 4 entries (1 file, 0 directories, 0 links, 0 other entries, 3 rejected); 1 converted.

- ok.txt

**Table 1**
Columns: Path, Size, Modified, Type, Converted

| Path | Size | Modified | Type | Converted |
|---|---:|---|---|---|
| ok.txt | 43 | 2024-05-01 12:00 | text/plain | converted (text.plain) |
| ../../evil.txt | 18 | 2024-05-01 12:00 | file | rejected (traversal path) |
| /etc/cron.d/evil | 22 | 2024-05-01 12:00 | file | rejected (absolute path) |
| sub/../../escape.txt | 29 | 2024-05-01 12:00 | file | rejected (traversal path) |

## 1 ok.txt {#sec-1}

This file is safe and should be converted.
