# Converter matrix

Generated from the built-in converter registry by `tools/gen_converters_matrix.py`; do not edit.
`tests/test_converters_matrix.py` fails when this page is stale.

This page lists what the code declares. Whether an engine is installed on a given machine is a
runtime question: run `intomd capabilities` (or `GET /v1/capabilities`) to see each converter as
loaded or unavailable with the reason, and `intomd doctor` for system programs such as LibreOffice.

- **Engine** is the second half of the converter id (`family.engine`).
- **Install**: `default` needs nothing beyond the base install; `extra x` needs that optional extra
  of `intomd-converters`; `planned` names an extra that does not exist yet.
- **Status**: `Experimental` converters add an `experimental_converter` warning to every result and
  are skipped when experimental converters are disabled; `Planned` converters are registered only so
  capabilities can explain why the format is not handled; every other converter is `Beta` until the
  first release.
- **Fixtures** counts golden fixtures under `fixtures/` that exercise the converter; **Threshold** is the
  minimum golden score from `fixtures/thresholds.toml` and `fixtures/<family>/thresholds.toml`.

| Converter | Family | Engine | MIME types | Install | Status | Fixtures | Threshold | Page |
|---|---|---|---|---|---|---|---|---|
| `archives.archive` | archives | archive | `application/zip`, `application/x-zip-compressed`, `application/x-tar` and 6 more | default | Beta | 4 | 0.99 | [archives](archives.md) |
| `archives.sevenzip` | archives | sevenzip | `application/x-7z-compressed` | extra `7z` | Beta | 0 | 0.85 | [archives](archives.md) |
| `code.repo_pack` | code | repo_pack | `application/gzip`, `application/x-compressed-tar`, `application/x-gzip` and 3 more | default | Beta | 3 | 0.99 | [code](code.md) |
| `code.source_file` | code | source_file | `text/x-python`, `application/typescript`, `text/x-typescript` and 40 more | default | Beta | 5 | 0.99 | [code](code.md) |
| `data.connection_string` | data | connection_string | `text/x-uri`, `text/plain` | default | Beta | 1 | 1.00 | [data](data.md) |
| `data.csv` | data | csv | `text/csv`, `text/tab-separated-values` | default | Beta | 4 | 1.00 | [data](data.md) |
| `data.json` | data | json | `application/json`, `application/jsonl`, `application/x-ndjson` | default | Beta | 3 | 1.00 | [data](data.md) |
| `data.parquet` | data | parquet | `application/vnd.apache.parquet`, `application/x-parquet` | extra `data` | Beta | 1 | 1.00 | [data](data.md) |
| `data.sqlite` | data | sqlite | `application/vnd.sqlite3`, `application/x-sqlite3` | default | Beta | 1 | 1.00 | [data](data.md) |
| `data.toml` | data | toml | `application/toml` | default | Beta | 1 | 1.00 | [data](data.md) |
| `data.xml` | data | xml | `application/xml` | default | Beta | 2 | 1.00 | [data](data.md) |
| `data.yaml` | data | yaml | `application/yaml` | default | Beta | 1 | 1.00 | [data](data.md) |
| `documents.epub` | documents | epub | `application/epub+zip` | default | Beta | 2 | 0.95 | [ebooks](ebooks.md) |
| `documents.ipynb` | documents | ipynb | `application/x-ipynb+json`, `application/x-ipynb` | default | Beta | 1 | 0.95 | [ebooks](ebooks.md) |
| `specialized.edgar` | specialized | edgar | `text/html`, `application/xhtml+xml`, `application/json` and 3 more | default | Beta | 3 | 0.95 | [edgar](edgar.md) |
| `documents.docx` | documents | docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.ms-word.document.macroenabled.12`, `application/vnd.openxmlformats-officedocument.wordprocessingml.template` and 1 more | default | Beta | 3 | 0.95 | [office](office.md) |
| `documents.iwork` | documents | iwork | `application/vnd.apple.pages`, `application/vnd.apple.numbers`, `application/vnd.apple.keynote` | planned | Planned | 0 | 0.85 | [office](office.md) |
| `documents.libreoffice` | documents | libreoffice | `application/msword`, `application/vnd.ms-excel`, `application/vnd.ms-powerpoint` and 10 more | default | Beta | 0 | 0.85 | [office](office.md) |
| `documents.odf` | documents | odf | `application/vnd.oasis.opendocument.text`, `application/vnd.oasis.opendocument.text-template`, `application/vnd.oasis.opendocument.spreadsheet` and 3 more | default | Beta | 1 | 0.90 | [office](office.md) |
| `documents.pptx` | documents | pptx | `application/vnd.openxmlformats-officedocument.presentationml.presentation`, `application/vnd.ms-powerpoint.presentation.macroenabled.12`, `application/vnd.openxmlformats-officedocument.presentationml.template` and 1 more | default | Beta | 1 | 0.95 | [office](office.md) |
| `documents.rtf` | documents | rtf | `application/rtf`, `text/rtf` | default | Beta | 1 | 0.90 | [office](office.md) |
| `documents.xlsx` | documents | xlsx | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/vnd.ms-excel.sheet.macroenabled.12`, `application/vnd.openxmlformats-officedocument.spreadsheetml.template` | default | Beta | 1 | 0.95 | [office](office.md) |
| `documents.docling_pdf` | documents | docling_pdf | `application/pdf` | extra `docs` | Beta | 0 | 0.95 | [pdf](pdf.md) |
| `documents.pdfium_text` | documents | pdfium_text | `application/pdf` | default | Beta | 7 | 0.95 | [pdf](pdf.md) |
| `web.social_hn` | web | social_hn | `application/json`, `text/plain`, `text/x-uri` | default | Experimental (behind `INTOMD_ENABLE_SOCIAL`) | 0 | 0.85 | [social](social.md) |
| `web.social_reddit` | web | social_reddit | `application/json`, `text/plain`, `text/x-uri` | default | Experimental (behind `INTOMD_ENABLE_SOCIAL`) | 0 | 0.85 | [social](social.md) |
| `text.markdown_passthrough` | text | markdown_passthrough | `text/markdown` | default | Beta | 1 | 0.95 | [text](text.md) |
| `text.plain` | text | plain | `text/plain`, `text/*` | default | Beta | 3 | 0.95 | [text](text.md) |
| `web.html_raw` | web | html_raw | `text/html`, `application/xhtml+xml` | default | Beta | 1 | 0.90 | [web](web.md) |
| `web.rules` | web | rules | `text/html`, `application/xhtml+xml` | default | Beta | 2 | 0.95 | [web](web.md) |
| `web.trafilatura` | web | trafilatura | `text/html`, `application/xhtml+xml` | default | Beta | 9 | 0.95 | [web](web.md) |

Converters behind a flag are off by default; they are listed here as they behave with the flag set (`INTOMD_ENABLE_SOCIAL=1`).

31 converters, 62 fixtures.

## Fallback chains

When a converter fails with a retryable error, the next converter in the chain for that MIME type is
tried (`intomd.chains`).

| MIME type | Chain |
|---|---|
| `application/epub+zip` | `documents.epub` then `archives.archive` |
| `application/gzip` | `archives.archive` |
| `application/javascript` | `code.source_file` then `text.plain` |
| `application/json` | `data.json` |
| `application/jsonl` | `data.json` |
| `application/msword` | `documents.libreoffice` |
| `application/pdf` | `documents.docling_pdf` then `documents.pdfium_text` |
| `application/rtf` | `documents.libreoffice` then `documents.rtf` |
| `application/toml` | `data.toml` |
| `application/typescript` | `code.source_file` then `text.plain` |
| `application/vnd.apache.parquet` | `data.parquet` |
| `application/vnd.apple.keynote` | `documents.iwork` |
| `application/vnd.apple.numbers` | `documents.iwork` |
| `application/vnd.apple.pages` | `documents.iwork` |
| `application/vnd.ms-excel` | `documents.libreoffice` |
| `application/vnd.ms-excel.sheet.binary.macroenabled.12` | `documents.libreoffice` |
| `application/vnd.ms-excel.sheet.macroenabled.12` | `documents.xlsx` |
| `application/vnd.ms-powerpoint` | `documents.libreoffice` |
| `application/vnd.ms-powerpoint.presentation.macroenabled.12` | `documents.pptx` |
| `application/vnd.ms-word.document.macroenabled.12` | `documents.docx` |
| `application/vnd.ms-word.template.macroenabled.12` | `documents.docx` |
| `application/vnd.oasis.opendocument.presentation` | `documents.odf` then `documents.libreoffice` |
| `application/vnd.oasis.opendocument.presentation-template` | `documents.odf` then `documents.libreoffice` |
| `application/vnd.oasis.opendocument.spreadsheet` | `documents.odf` then `documents.libreoffice` |
| `application/vnd.oasis.opendocument.spreadsheet-template` | `documents.odf` then `documents.libreoffice` |
| `application/vnd.oasis.opendocument.text` | `documents.odf` then `documents.libreoffice` |
| `application/vnd.oasis.opendocument.text-template` | `documents.odf` then `documents.libreoffice` |
| `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `documents.pptx` |
| `application/vnd.openxmlformats-officedocument.presentationml.slideshow` | `documents.pptx` |
| `application/vnd.openxmlformats-officedocument.presentationml.template` | `documents.pptx` |
| `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `documents.xlsx` |
| `application/vnd.openxmlformats-officedocument.spreadsheetml.template` | `documents.xlsx` |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `documents.docx` |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.template` | `documents.docx` |
| `application/vnd.sqlite3` | `data.sqlite` |
| `application/vnd.wordperfect` | `documents.libreoffice` |
| `application/x-7z-compressed` | `archives.archive` |
| `application/x-bzip2` | `archives.archive` |
| `application/x-gzip` | `archives.archive` |
| `application/x-ipynb+json` | `documents.ipynb` |
| `application/x-ndjson` | `data.json` |
| `application/x-parquet` | `data.parquet` |
| `application/x-powershell` | `code.source_file` then `text.plain` |
| `application/x-ruby` | `code.source_file` then `text.plain` |
| `application/x-rust` | `code.source_file` then `text.plain` |
| `application/x-scala` | `code.source_file` then `text.plain` |
| `application/x-sh` | `code.source_file` then `text.plain` |
| `application/x-sqlite3` | `data.sqlite` |
| `application/x-tar` | `archives.archive` |
| `application/x-tcl` | `code.source_file` then `text.plain` |
| `application/x-xz` | `archives.archive` |
| `application/xhtml+xml` | `web.trafilatura` then `web.rules` then `web.html_raw` |
| `application/xml` | `data.xml` |
| `application/yaml` | `data.yaml` |
| `text/coffeescript` | `code.source_file` then `text.plain` |
| `text/csv` | `data.csv` |
| `text/html` | `web.trafilatura` then `web.rules` then `web.html_raw` |
| `text/javascript` | `code.source_file` then `text.plain` |
| `text/markdown` | `text.markdown_passthrough` then `text.plain` |
| `text/plain` | `text.plain` |
| `text/rtf` | `documents.libreoffice` then `documents.rtf` |
| `text/tab-separated-values` | `data.csv` |
| `text/vbscript` | `code.source_file` then `text.plain` |
| `text/x-asm` | `code.source_file` then `text.plain` |
| `text/x-c` | `code.source_file` then `text.plain` |
| `text/x-clojure` | `code.source_file` then `text.plain` |
| `text/x-cmake` | `code.source_file` then `text.plain` |
| `text/x-dockerfile` | `code.source_file` then `text.plain` |
| `text/x-erlang` | `code.source_file` then `text.plain` |
| `text/x-go` | `code.source_file` then `text.plain` |
| `text/x-golang` | `code.source_file` then `text.plain` |
| `text/x-groovy` | `code.source_file` then `text.plain` |
| `text/x-h` | `code.source_file` then `text.plain` |
| `text/x-hcl` | `code.source_file` then `text.plain` |
| `text/x-java` | `code.source_file` then `text.plain` |
| `text/x-julia` | `code.source_file` then `text.plain` |
| `text/x-lisp` | `code.source_file` then `text.plain` |
| `text/x-makefile` | `code.source_file` then `text.plain` |
| `text/x-matlab` | `code.source_file` then `text.plain` |
| `text/x-msdos-batch` | `code.source_file` then `text.plain` |
| `text/x-objcsrc` | `code.source_file` then `text.plain` |
| `text/x-pascal` | `code.source_file` then `text.plain` |
| `text/x-perl` | `code.source_file` then `text.plain` |
| `text/x-php` | `code.source_file` then `text.plain` |
| `text/x-proto` | `code.source_file` then `text.plain` |
| `text/x-python` | `code.source_file` then `text.plain` |
| `text/x-r` | `code.source_file` then `text.plain` |
| `text/x-ruby` | `code.source_file` then `text.plain` |
| `text/x-rust` | `code.source_file` then `text.plain` |
| `text/x-shellscript` | `code.source_file` then `text.plain` |
| `text/x-swift` | `code.source_file` then `text.plain` |
| `text/x-typescript` | `code.source_file` then `text.plain` |
| `text/x-verilog` | `code.source_file` then `text.plain` |
| `text/x-vhdl` | `code.source_file` then `text.plain` |
| `text/zig` | `code.source_file` then `text.plain` |

## MIME types by converter

- `archives.archive`: `application/zip`, `application/x-zip-compressed`, `application/x-tar`, `application/gzip`, `application/x-gzip`, `application/x-bzip2`, `application/x-xz`, `application/x-7z-compressed`, `application/x-compressed-tar`
- `archives.sevenzip`: `application/x-7z-compressed`
- `code.repo_pack`: `application/gzip`, `application/x-compressed-tar`, `application/x-gzip`, `application/x-tar`, `application/zip`, `text/x-uri`
- `code.source_file`: `text/x-python`, `application/typescript`, `text/x-typescript`, `application/javascript`, `text/javascript`, `text/x-golang`, `text/x-go`, `application/x-rust`, `text/x-rust`, `text/x-c`, `text/x-h`, `text/x-java`, `application/x-ruby`, `text/x-ruby`, `text/x-php`, `text/x-shellscript`, `application/x-sh`, `text/x-swift`, `application/x-scala`, `text/x-perl`, `text/x-groovy`, `text/x-julia`, `text/x-lisp`, `text/x-clojure`, `text/coffeescript`, `application/x-powershell`, `text/x-msdos-batch`, `text/x-asm`, `text/x-proto`, `text/x-objcsrc`, `text/x-r`, `text/x-matlab`, `text/x-pascal`, `text/x-erlang`, `text/zig`, `application/x-tcl`, `text/x-verilog`, `text/x-vhdl`, `text/x-cmake`, `text/x-makefile`, `text/x-dockerfile`, `text/x-hcl`, `text/vbscript`
- `data.connection_string`: `text/x-uri`, `text/plain`
- `data.csv`: `text/csv`, `text/tab-separated-values`
- `data.json`: `application/json`, `application/jsonl`, `application/x-ndjson`
- `data.parquet`: `application/vnd.apache.parquet`, `application/x-parquet`
- `data.sqlite`: `application/vnd.sqlite3`, `application/x-sqlite3`
- `data.toml`: `application/toml`
- `data.xml`: `application/xml`
- `data.yaml`: `application/yaml`
- `documents.epub`: `application/epub+zip`
- `documents.ipynb`: `application/x-ipynb+json`, `application/x-ipynb`
- `specialized.edgar`: `text/html`, `application/xhtml+xml`, `application/json`, `text/plain`, `text/x-uri`, `application/xml`
- `documents.docx`: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.ms-word.document.macroenabled.12`, `application/vnd.openxmlformats-officedocument.wordprocessingml.template`, `application/vnd.ms-word.template.macroenabled.12`
- `documents.iwork`: `application/vnd.apple.pages`, `application/vnd.apple.numbers`, `application/vnd.apple.keynote`
- `documents.libreoffice`: `application/msword`, `application/vnd.ms-excel`, `application/vnd.ms-powerpoint`, `application/vnd.ms-excel.sheet.binary.macroenabled.12`, `application/vnd.wordperfect`, `application/rtf`, `text/rtf`, `application/vnd.oasis.opendocument.text`, `application/vnd.oasis.opendocument.text-template`, `application/vnd.oasis.opendocument.spreadsheet`, `application/vnd.oasis.opendocument.spreadsheet-template`, `application/vnd.oasis.opendocument.presentation`, `application/vnd.oasis.opendocument.presentation-template`
- `documents.odf`: `application/vnd.oasis.opendocument.text`, `application/vnd.oasis.opendocument.text-template`, `application/vnd.oasis.opendocument.spreadsheet`, `application/vnd.oasis.opendocument.spreadsheet-template`, `application/vnd.oasis.opendocument.presentation`, `application/vnd.oasis.opendocument.presentation-template`
- `documents.pptx`: `application/vnd.openxmlformats-officedocument.presentationml.presentation`, `application/vnd.ms-powerpoint.presentation.macroenabled.12`, `application/vnd.openxmlformats-officedocument.presentationml.template`, `application/vnd.openxmlformats-officedocument.presentationml.slideshow`
- `documents.rtf`: `application/rtf`, `text/rtf`
- `documents.xlsx`: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/vnd.ms-excel.sheet.macroenabled.12`, `application/vnd.openxmlformats-officedocument.spreadsheetml.template`
- `documents.docling_pdf`: `application/pdf`
- `documents.pdfium_text`: `application/pdf`
- `web.social_hn`: `application/json`, `text/plain`, `text/x-uri`
- `web.social_reddit`: `application/json`, `text/plain`, `text/x-uri`
- `text.markdown_passthrough`: `text/markdown`
- `text.plain`: `text/plain`, `text/*`
- `web.html_raw`: `text/html`, `application/xhtml+xml`
- `web.rules`: `text/html`, `application/xhtml+xml`
- `web.trafilatura`: `text/html`, `application/xhtml+xml`

To add a converter of your own, see [Writing a converter plugin](../plugins.md).
