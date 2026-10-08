#!/usr/bin/env bash
# intomd upgrade (docs/spec/part4.md 4.9.9).
#
#   deploy/upgrade.sh <version> [--no-pull] [--build] [--no-backup] [--health-timeout S]
#
# 1. backup.sh (unless --no-backup)
# 2. set INTOMD_VERSION=<version> in the env file and pull that tag (--no-pull: use local images;
#    --build: build this checkout and tag it <version>)
# 3. database migrations with the new image (stackctl.py migrate)
# 4. `up -d --remove-orphans --wait`, then /readyz through Caddy
# 5. on any failure after step 2: put the previous INTOMD_VERSION back, restore the pre-upgrade
#    backup when migrations ran (they are forward-only), start the old version, exit 1
# 6. on success: prune dangling images
# Pin exact versions (1.4.2); patch releases are safe for Watchtower, minor ones go through this script.
set -euo pipefail

# shellcheck source=deploy/lib.sh
. "$(dirname "$0")/lib.sh"

NEW="" PULL=1 BUILD=0 BACKUP=1 HEALTH_S=180
while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull) PULL=0; shift ;;
    --build) BUILD=1; PULL=0; shift ;;
    --no-backup) BACKUP=0; shift ;;
    --health-timeout) HEALTH_S="${2:?--health-timeout needs seconds}"; shift 2 ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$NEW" ] || die "only one version may be given"; NEW="$1"; shift ;;
  esac
done
[ -n "$NEW" ] || die "usage: upgrade.sh <version> (see the GitHub releases for tags)"
NEW="${NEW#v}"
[[ "$NEW" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || die "not an image tag: $NEW"
[[ "$HEALTH_S" =~ ^[0-9]+$ ]] || die "--health-timeout must be a number of seconds"

require_docker
[ -f "$ENV_FILE" ] || die "no env file at $ENV_FILE (run bootstrap.sh first)"
PREV="$(env_get INTOMD_VERSION)"
PREV="${PREV:-latest}"
log "upgrading $PREV -> $NEW"

BACKUP_FILE=""
if [ "$BACKUP" = 1 ]; then
  BACKUP_FILE="$(bash "$DEPLOY_DIR/backup.sh" | tail -n 1)" || die "backup failed; nothing was changed"
  log "pre-upgrade backup: $BACKUP_FILE"
fi

MIGRATED=0
rollback() {
  warn "upgrade to $NEW failed: $1"
  warn "rolling back to $PREV"
  env_set INTOMD_VERSION "$PREV"
  if [ "$MIGRATED" = 1 ] && [ -n "$BACKUP_FILE" ]; then
    bash "$DEPLOY_DIR/restore.sh" --no-smoke "$BACKUP_FILE" || die "rollback restore failed; restore $BACKUP_FILE by hand"
  else
    compose up -d --no-build --remove-orphans --wait --wait-timeout "$HEALTH_S" ||
      die "the previous version $PREV did not come back healthy either; see docker compose logs"
  fi
  die "upgrade to $NEW rolled back; still running $PREV"
}

env_set INTOMD_VERSION "$NEW"
if [ "$PULL" = 1 ]; then
  compose pull --quiet || rollback "could not pull tag $NEW"
elif [ "$BUILD" = 1 ]; then
  compose build || rollback "build failed"
fi

# Never let `compose run`/`up` fall back to building from source for a tag that is not there.
for img in $(compose config --images); do
  docker image inspect "$img" >/dev/null 2>&1 || rollback "image $img is not available locally"
done

MIGRATED=1
stackctl migrate || rollback "database migration failed"

compose up -d --no-build --remove-orphans --wait --wait-timeout "$HEALTH_S" ||
  rollback "services did not become healthy within ${HEALTH_S}s"
wait_ready "$HEALTH_S" || rollback "$(stack_url)/readyz did not answer 200"

docker image prune -f >/dev/null 2>&1 || true
log "upgraded to $NEW"
