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
