#!/usr/bin/env bash
# ezmd first-run bootstrap (docs/spec/part4.md 4.9.8, core profile). Safe to run again: existing
# secrets, keys and settings are kept; only missing ones are created.
#
#   deploy/bootstrap.sh --domain ezmd.example.com --email you@example.com
#   deploy/bootstrap.sh --domain localhost            # HTTPS with Caddy's internal CA
#   deploy/bootstrap.sh --plain-http                  # plain HTTP on EZMD_PLAIN_PORT (default 8080)
#
# Options:
#   --domain D       site address for Caddy (sets EZMD_DOMAIN and EZMD_PUBLIC_URL)
#   --email E        Let's Encrypt contact (EZMD_ACME_EMAIL)
#   --plain-http     no TLS: EZMD_DOMAIN empty, served on :8080
#   --version V      image tag to run (EZMD_VERSION), e.g. 1.2.0; default: keep the env file's value
#   --build          build the images from this checkout instead of pulling them
#   --no-smoke       skip the end-to-end smoke test at the end
#   --key-out PATH   where to write the owner API key created on first run (default: next to the env file)
#
# Steps: check Docker; create the env file from env.example (mode 600); generate any missing secret
# (key pepper, JWT secret, IP hash salt, Redis password, metrics token); pull or build the images;
# apply database migrations; create keys.json with an owner key via ezmd-admin; start the stack and
# wait for every healthcheck; run deploy/smoke.sh. Host hardening (firewall, sshd, unattended upgrades)
# is not done here: see docs/selfhost.md.
set -euo pipefail

# shellcheck source=deploy/lib.sh
. "$(dirname "$0")/lib.sh"

DOMAIN="" DOMAIN_SET=0 EMAIL="" EMAIL_SET=0 VERSION="" BUILD=0 SMOKE=1 KEY_OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="${2:?--domain needs a value}"; DOMAIN_SET=1; shift 2 ;;
    --email) EMAIL="${2:?--email needs a value}"; EMAIL_SET=1; shift 2 ;;
    --plain-http) DOMAIN=""; DOMAIN_SET=1; shift ;;
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    --build) BUILD=1; shift ;;
    --no-smoke) SMOKE=0; shift ;;
    --key-out) KEY_OUT="${2:?--key-out needs a path}"; shift 2 ;;
    -h | --help) sed -n '2,24p' "$0"; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done

if [ -n "$DOMAIN" ]; then
  [[ "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$ ]] || die "--domain is not a host name: $DOMAIN"
fi
if [ -n "$EMAIL" ]; then
  [[ "$EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+$ ]] || die "--email is not an email address: $EMAIL"
fi
if [ -n "$VERSION" ]; then
  [[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || die "--version is not an image tag: $VERSION"
fi

require_docker
command -v curl >/dev/null 2>&1 || die "curl is required"

# 1. env file ------------------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  log "creating $ENV_FILE from env.example"
  mkdir -p "$(dirname "$ENV_FILE")"
  (umask 077 && cp "$DEPLOY_DIR/env.example" "$ENV_FILE")
  # The template's example site address must not reach Let's Encrypt by accident.
  [ "$DOMAIN_SET" = 1 ] || { DOMAIN=""; DOMAIN_SET=1; warn "no --domain given: serving plain HTTP on :$(cfg EZMD_PLAIN_PORT 8080)"; }
  [ "$EMAIL_SET" = 1 ] || { EMAIL=""; EMAIL_SET=1; }
fi
chmod 600 "$ENV_FILE" 2>/dev/null || true

if [ "$DOMAIN_SET" = 1 ]; then
  env_set EZMD_DOMAIN "$DOMAIN"
  if [ -z "$DOMAIN" ]; then
    env_set EZMD_PUBLIC_URL "http://localhost:$(cfg EZMD_PLAIN_PORT 8080)"
  else
    env_set EZMD_PUBLIC_URL "https://$DOMAIN"
  fi
fi
[ "$EMAIL_SET" = 1 ] && env_set EZMD_ACME_EMAIL "$EMAIL"
[ -n "$VERSION" ] && env_set EZMD_VERSION "$VERSION"
if [ "$(env_get EZMD_DOMAIN)" = ezmd.example.com ]; then
  die "EZMD_DOMAIN is still the example value; pass --domain or --plain-http"
fi

# 2. secrets: generated once, never rotated by a re-run (rotating the pepper invalidates every API key)
ensure_secret() {
  local key="$1" bytes="$2"
  if [ -z "$(env_get "$key")" ]; then
    env_set "$key" "$(rand_hex "$bytes")"
    log "generated $key"
  fi
}
ensure_secret EZMD_KEY_PEPPER 32
ensure_secret EZMD_JWT_SECRET 32
ensure_secret EZMD_IP_HASH_SALT 16
ensure_secret EZMD_REDIS_PASSWORD 24
ensure_secret EZMD_METRICS_TOKEN 16
if [ -z "$(env_get EZMD_KEYS_FILE)" ]; then
  env_set EZMD_KEYS_FILE /var/lib/ezmd/keys.json
fi
[ -n "$(env_get EZMD_VERSION)" ] || env_set EZMD_VERSION latest
[ "$(env_get EZMD_VERSION)" = latest ] && warn "EZMD_VERSION=latest; pin a release (--version X.Y.Z) in production"

# 3. images --------------------------------------------------------------------------------------
if [ "$BUILD" = 1 ]; then
  log "building images from $(dirname "$DEPLOY_DIR")"
  compose build
else
  log "pulling images (tag $(env_get EZMD_VERSION))"
  if ! compose pull --quiet; then
    for img in $(compose config --images); do
      docker image inspect "$img" >/dev/null 2>&1 || die "pull failed and $img is not available locally; check EZMD_VERSION or rerun with --build"
    done
    warn "pull failed; using the images already present locally"
  fi
fi

# 4. database schema -----------------------------------------------------------------------------
log "applying database migrations"
stackctl migrate

# 5. API keys ------------------------------------------------------------------------------------
KEY_OUT="${KEY_OUT:-$(dirname "$ENV_FILE")/ezmd-owner.key}"
if stackctl has-keys; then
  log "keys file already present; leaving it alone"
else
  log "creating keys.json with an owner key"
  out="$(compose run --rm --no-deps -T api ezmd-admin keys create --store file --name owner --unlimited 2>/dev/null)" ||
    die "ezmd-admin keys create failed"
  key="$(printf '%s\n' "$out" | awk '$1 == "key:" { print $2 }')"
  [ -n "$key" ] || die "ezmd-admin printed no key"
  (umask 077 && printf '%s\n' "$key" >"$KEY_OUT")
  log "owner API key written to $KEY_OUT (mode 600); store it in a password manager and delete the file"
fi

# 6. start ---------------------------------------------------------------------------------------
log "starting the stack"
build_flag="--no-build"
[ "$BUILD" = 1 ] && build_flag="--build"
compose up -d "$build_flag" --remove-orphans --wait --wait-timeout "${EZMD_WAIT_TIMEOUT_S:-300}" ||
  { compose ps >&2; die "the stack did not become healthy; see: docker compose logs"; }
wait_ready 120 || die "$(stack_url)/readyz did not answer 200"

# 7. smoke ---------------------------------------------------------------------------------------
if [ "$SMOKE" = 1 ]; then
  log "smoke test"
  SMOKE_API_KEY="${SMOKE_API_KEY:-$(cat "${KEY_OUT:-/nonexistent}" 2>/dev/null || true)}" \
    bash "$DEPLOY_DIR/smoke.sh" --no-build --no-up
fi

log "ezmd is up at $(stack_url)"
echo "  env file:  $ENV_FILE (secrets, mode 600)"
echo "  API keys:  docker compose exec api ezmd-admin keys create --store file --name <who>"
echo "  backups:   $DEPLOY_DIR/backup.sh (schedule it daily; see docs/selfhost.md)"
echo "  upgrades:  $DEPLOY_DIR/upgrade.sh <version>"
