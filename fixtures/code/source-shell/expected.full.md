---
title: "input.sh"
source: "input.sh"
source_type: code
converter: code.source_file
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 64
tokens: {o200k_base: 191, cl100k_base: 188, claude_approx: 206}
content_hash: "sha256:4154153bca58d4d93cca38c1fde5cb8acabfe63b65fd263b7769c7095bd4aad9"
source_hash: "sha256:8bec98acc54768a22d0807e29d8344b54a6900ab3b2560978f290c0d0f069379"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 515, encoding: utf-8, language: bash, lines: 24, shebang: bash, tokens: 169}
---
# input.sh {#doc}

File: `input.sh`

```bash
#!/usr/bin/env bash
# backup.sh: rotate nightly database dumps (intomd fixture).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/app}"
KEEP_DAYS=14

log() {
  printf "%s %s" "$(date -u +%FT%TZ)" "$*" >&2
}

rotate() {
  find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$KEEP_DAYS" -print -delete
}

cat <<'EOF' > /tmp/backup-banner.txt
Nightly backup: do not interrupt.
EOF

case "${1:-run}" in
  run) log starting; rotate ;;
  dry-run) log dry run only ;;
  *) echo "usage: $0 [run|dry-run]"; exit 2 ;;
esac
```
