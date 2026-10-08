#!/usr/bin/env bash
# intomd backup (docs/spec/part4.md 4.9.9). Works while the stack is running.
#
#   deploy/backup.sh [--no-blobs] [--out DIR] [--keep N]
#
# Writes DIR/intomd-<UTC timestamp>.tar.gz (mode 600; DIR mode 700) containing:
#   app.tar          consistent SQLite snapshot (sqlite3 online backup API), keys.json and, unless
#                    --no-blobs, the blob store; with its own manifest.json of SHA-256 sums (stackctl.py)
#   caddy_data.tar   Caddy's certificates and ACME account
#   env              the operator env file (holds every secret: keep backups private)
#   SHA256SUMS       checksums of the three files above
# Then deletes all but the newest N backups (default INTOMD_BACKUP_KEEP or 14).
# DIR defaults to INTOMD_BACKUP_DIR, else deploy/backups. The last line printed is the tarball path.
set -euo pipefail

# shellcheck source=deploy/lib.sh
. "$(dirname "$0")/lib.sh"

BLOBS_FLAG=() OUT="" KEEP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-blobs) BLOBS_FLAG=(--no-blobs); shift ;;
    --out) OUT="${2:?--out needs a directory}"; shift 2 ;;
    --keep) KEEP="${2:?--keep needs a number}"; shift 2 ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
OUT="${OUT:-$(cfg INTOMD_BACKUP_DIR "$DEPLOY_DIR/backups")}"
KEEP="${KEEP:-$(cfg INTOMD_BACKUP_KEEP 14)}"
[[ "$KEEP" =~ ^[1-9][0-9]{0,3}$ ]] || die "--keep must be a positive number, got: $KEEP"

require_docker
[ -f "$ENV_FILE" ] || die "no env file at $ENV_FILE (run bootstrap.sh first)"

mkdir -p "$OUT"
chmod 700 "$OUT" 2>/dev/null || true
TS="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

log "snapshotting database, keys and blobs"
stackctl backup ${BLOBS_FLAG[@]+"${BLOBS_FLAG[@]}"} >"$WORK/app.tar" || die "application data backup failed"

log "archiving Caddy data"
compose run --rm --no-deps -T --entrypoint tar caddy -cf - -C /data . >"$WORK/caddy_data.tar" ||
  die "Caddy data backup failed"

cp "$ENV_FILE" "$WORK/env"
(cd "$WORK" && sha256sum app.tar caddy_data.tar env >SHA256SUMS)

DEST="$OUT/intomd-$TS.tar.gz"
(umask 077 && tar -czf "$DEST.partial" -C "$WORK" SHA256SUMS app.tar caddy_data.tar env)
mv "$DEST.partial" "$DEST"
chmod 600 "$DEST" 2>/dev/null || true

# Retention: newest first by name (timestamps sort lexically).
old="$(find "$OUT" -maxdepth 1 -name 'intomd-*.tar.gz' -type f | sort -r | tail -n +"$((KEEP + 1))")"
if [ -n "$old" ]; then
  printf '%s\n' "$old" | while IFS= read -r f; do rm -f -- "$f"; done
  log "pruned $(printf '%s\n' "$old" | wc -l | tr -d ' ') old backup(s), keeping $KEEP"
fi

log "backup written ($(du -h "$DEST" | cut -f1))"
printf '%s\n' "$DEST"
