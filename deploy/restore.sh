#!/usr/bin/env bash
# intomd restore (docs/spec/part4.md 4.9.9).
#
#   deploy/restore.sh [--with-env] [--verify-only] [--no-smoke] <backup.tar.gz>
#
# 1. verify: SHA256SUMS of the outer archive, then every file against app.tar's manifest (nothing
#    is changed when either check fails)
# 2. stop every service except redis
# 3. restore the database, keys.json and blobs (stackctl.py restore) and Caddy's data volume
# 4. --with-env: also replace the env file with the backed-up one (the current file is kept as
#    <env file>.pre-restore). Without it the current env file stays; the key pepper must match the
#    backup's, or API keys from the backup stop working (a warning is printed when they differ).
# 5. start the stack, wait for health, run the smoke test (unless --no-smoke)
# Works on a fresh volume set (after `docker compose down -v`, or on a new host with the same env file).
set -euo pipefail

# shellcheck source=deploy/lib.sh
. "$(dirname "$0")/lib.sh"

WITH_ENV=0 VERIFY_ONLY=0 SMOKE=1 ARCHIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --with-env) WITH_ENV=1; shift ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    --no-smoke) SMOKE=0; shift ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$ARCHIVE" ] || die "only one backup file may be given"; ARCHIVE="$1"; shift ;;
  esac
done
[ -n "$ARCHIVE" ] || die "usage: restore.sh [--with-env] [--verify-only] [--no-smoke] <backup.tar.gz>"
[ -f "$ARCHIVE" ] || die "no such file: $ARCHIVE"

require_docker
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 1. verify ----------------------------------------------------------------------------------------
log "verifying $ARCHIVE"
listing="$(tar -tzf "$ARCHIVE")" || die "not a readable .tar.gz: $ARCHIVE"
for name in $listing; do
  case "$name" in
    SHA256SUMS | app.tar | caddy_data.tar | env | ./) ;;
    *) die "unexpected entry in backup: $name" ;;
  esac
done
tar -xzf "$ARCHIVE" -C "$WORK" SHA256SUMS app.tar caddy_data.tar env || die "backup is incomplete"
(cd "$WORK" && sha256sum -c --quiet SHA256SUMS) || die "checksum mismatch in $ARCHIVE"

if [ "$WITH_ENV" = 1 ]; then
  if [ -f "$ENV_FILE" ]; then
    cp -p "$ENV_FILE" "$ENV_FILE.pre-restore"
    log "current env file saved as $ENV_FILE.pre-restore"
  fi
  (umask 077 && cp "$WORK/env" "$ENV_FILE")
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  log "env file restored"
elif [ ! -f "$ENV_FILE" ]; then
  die "no env file at $ENV_FILE; rerun with --with-env to restore the backed-up one"
else
  backed_pepper="$(ENV_FILE="$WORK/env" env_get INTOMD_KEY_PEPPER)"
  if [ "$backed_pepper" != "$(env_get INTOMD_KEY_PEPPER)" ]; then
    warn "INTOMD_KEY_PEPPER differs from the backup's; restored API keys will not validate (use --with-env)"
  fi
fi

# The image must exist before stackctl can verify app.tar; it runs with the current INTOMD_VERSION.
stackctl verify <"$WORK/app.tar" || die "app.tar failed verification"
if [ "$VERIFY_ONLY" = 1 ]; then
  log "backup verified; nothing changed (--verify-only)"
  exit 0
fi

# 2. stop --------------------------------------------------------------------------------------------
log "stopping the application services"
SERVICES=()
while IFS= read -r svc; do SERVICES+=("$svc"); done < <(app_services)
compose stop "${SERVICES[@]}"

# 3. restore -----------------------------------------------------------------------------------------
log "restoring database, keys and blobs"
stackctl restore <"$WORK/app.tar" || die "restore of application data failed; the stack is stopped"

log "restoring Caddy data"
compose run --rm --no-deps -T --entrypoint sh caddy -c \
  'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -xf - -o -C /data' <"$WORK/caddy_data.tar" ||
  die "restore of Caddy data failed; the stack is stopped"

# 4. start -------------------------------------------------------------------------------------------
log "starting the stack"
compose up -d --no-build --wait --wait-timeout "${INTOMD_WAIT_TIMEOUT_S:-300}" ||
  { compose ps >&2; die "the stack did not become healthy after the restore"; }
wait_ready 120 || die "$(stack_url)/readyz did not answer 200 after the restore"

if [ "$SMOKE" = 1 ]; then
  bash "$DEPLOY_DIR/smoke.sh" --no-up
fi
log "restored from $ARCHIVE: database, keys.json, blobs, Caddy data$([ "$WITH_ENV" = 1 ] && echo ', env file')"
