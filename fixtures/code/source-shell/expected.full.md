---
title: "input.sh"
source: "input.sh"
source_type: code
converter: code.source_file
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 64
tokens: {o200k_base: 190, cl100k_base: 187, claude_approx: 205}
content_hash: "sha256:5647f2437544f2eb15acfb9d7355591f19297750344847c430eacff6bafce7fc"
source_hash: "sha256:fe92131f08a1746e84898ad6d2e8a9c0ae968f7acc0aec3ab783797bba11eb0e"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 513, encoding: utf-8, language: bash, lines: 24, shebang: bash, tokens: 168}
---
# input.sh {#doc}

File: `input.sh`

```bash
#!/usr/bin/env bash
# backup.sh: rotate nightly database dumps (ezmd fixture).
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
