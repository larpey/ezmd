---
title: "input.zip"
source: "input.zip"
source_type: archive
converter: archives.archive
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 165
tokens: {o200k_base: 505, cl100k_base: 505, claude_approx: 545}
content_hash: "sha256:71356b81ff89214522f2aaf7eda0f963c9ce06c1db05e7fbc346d6b3ab019d8e"
source_hash: "sha256:49be156ab8f2082cea8a052a55d14dd38189114de27586bc67fabba9b469c7a0"
truncated: false
warnings: [archive_encrypted]
injection_risk: none
extra:
  archive_bytes_extracted: 3258
  archive_compressed_bytes: 1996
  archive_converted: 2
  archive_directories: 0
  archive_entries: 3
  archive_files: 3
  archive_format: zip
  archive_links: 0
  archive_other: 0
  archive_rejected: 0
---
# input.zip {#doc}

Archive input.zip: 3 entries (3 files, 0 directories, 0 links, 0 other entries, 0 rejected); 2 converted.

- README.txt
- bundle/
    - season.tar.gz
        - season/
            - report.docx
            - sites.csv
- private/
    - ringing-permits.txt

**Table 1**
Columns: Path, Size, Modified, Type, Converted

| Path | Size | Modified | Type | Converted |
|---|---:|---|---|---|
| README.txt | 64 | 2024-05-01 12:00 | text/plain | converted (text.plain) |
| bundle/season.tar.gz | 1528 | 2024-05-01 12:00 | archive | converted (archive) |
| private/ringing-permits.txt | 40 | 2024-05-01 12:00 | text/plain | encrypted |

## 1 README.txt {#sec-1}

Season bundle: the tarball holds the report and the site table.

## 2 bundle/season.tar.gz {#sec-2}

Archive season.tar.gz: 2 entries (2 files, 0 directories, 0 links, 0 other entries, 0 rejected); 2 converted.

- season/
    - report.docx
    - sites.csv

**Table 2**
Columns: Path, Size, Modified, Type, Converted

| Path | Size | Modified | Type | Converted |
|---|---:|---|---|---|
| season/report.docx | 1613 | 2024-05-01 12:00 | application/vnd.openxmlformats-officedocument.wordprocessingml.document | converted (documents.docx) |
| season/sites.csv | 53 | 2024-05-01 12:00 | text/csv | converted (data.csv) |

### 2.1 season/report.docx: Season Report {#sec-2-1}

Heron numbers rose at the east marsh for the third year.

The west reed bed was flooded in April.

### 2.2 season/sites.csv {#sec-2-2}

**Table 3**

| site | herons | egrets |
|---|---:|---:|
| east marsh | 14 | 3 |
| west reed bed | 6 | 9 |
