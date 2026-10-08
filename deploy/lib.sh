# shellcheck shell=bash
# Shared helpers for bootstrap.sh, backup.sh, restore.sh, upgrade.sh and smoke.sh. Source it; do not run it.
#
# Environment (all optional):
#   EZMD_ENV_FILE        operator env file (default deploy/.env); passed to compose as --env-file and
#                          to every container through `env_file:`
#   EZMD_COMPOSE_FILES   extra compose files, space separated, relative to deploy/ (e.g. docker-compose.gpu.yml)
#   COMPOSE_PROFILES       compose profiles (read by docker compose itself)
#   COMPOSE_PROJECT_NAME   compose project name (default "ezmd", from docker-compose.yml)

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Git Bash on Windows rewrites Unix-looking arguments for native programs (docker.exe); paths are
# converted explicitly with native_path instead.
export MSYS_NO_PATHCONV=1

log() { printf '==> %s\n' "$*" >&2; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

# native_path <path>: the path as the docker CLI expects it (C:/... under Git Bash, unchanged elsewhere).
native_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}

abs_path() {
  case "$1" in
    /* | [A-Za-z]:[/\\]*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$(pwd)" "$1" ;;
  esac
}

ENV_FILE="$(abs_path "${EZMD_ENV_FILE:-$DEPLOY_DIR/.env}")"
EZMD_ENV_FILE="$(native_path "$ENV_FILE")"
export EZMD_ENV_FILE

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker is not installed (https://docs.docker.com/engine/install/)"
  docker compose version >/dev/null 2>&1 || die "the docker compose v2 plugin is required"
  docker info >/dev/null 2>&1 || die "cannot talk to the Docker daemon (is it running, and may this user use it?)"
}

# compose <args...>: docker compose with this stack's files and env file.
compose() {
  local args=(-f "$(native_path "$DEPLOY_DIR/docker-compose.yml")")
  local f
  for f in ${EZMD_COMPOSE_FILES:-}; do
    args+=(-f "$(native_path "$DEPLOY_DIR/$f")")
  done
  if [ -f "$ENV_FILE" ]; then args+=(--env-file "$EZMD_ENV_FILE"); fi
  docker compose "${args[@]}" "$@"
}

# env_get <KEY>: the last value of KEY in the env file (empty when absent). Surrounding quotes are removed.
env_get() {
  [ -f "$ENV_FILE" ] || return 0
  awk -v k="$1" '
    index($0, k "=") == 1 { v = substr($0, length(k) + 2) }
    END {
      if (v ~ /^".*"$/ || v ~ /^'"'"'.*'"'"'$/) v = substr(v, 2, length(v) - 2)
      printf "%s", v
    }' "$ENV_FILE"
}

# cfg <KEY> <default>: the value compose would interpolate: shell environment, then env file, then default.
cfg() {
  local key="$1" default="${2:-}" value=""
  if [ -n "${!key+x}" ]; then value="${!key}"; else value="$(env_get "$key")"; fi
  printf '%s\n' "${value:-$default}"
}

# env_set <KEY> <VALUE>: replace KEY's line in the env file (or append it), keeping the file's mode.
env_set() {
  local key="$1" value="$2" tmp
  case "$value" in *$'\n'* | *\\*) die "refusing to write a multi-line or backslash value for $key" ;; esac
  tmp="$(mktemp)"
  awk -v k="$1" -v v="$value" '
    index($0, k "=") == 1 { if (!done) print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }' "$ENV_FILE" >"$tmp"
  cat "$tmp" >"$ENV_FILE"
  rm -f "$tmp"
}

# rand_hex <bytes>: a random hex string from the kernel CSPRNG.
rand_hex() {
  od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'
}

# stack_url: the base URL of the local stack, as Caddy serves it.
stack_url() {
  local domain
  domain="$(cfg EZMD_DOMAIN "")"
  if [ -z "$domain" ]; then
    printf 'http://localhost:%s\n' "$(cfg EZMD_PLAIN_PORT 8080)"
  else
    printf 'https://%s:%s\n' "$domain" "$(cfg EZMD_HTTPS_PORT 443)"
  fi
}

# stack_curl_args: curl flags that reach the local Caddy for a real domain without DNS.
stack_curl_args() {
  local domain
  domain="$(cfg EZMD_DOMAIN "")"
  if [ -n "$domain" ] && [ "$domain" != localhost ]; then
    printf -- '--resolve %s:%s:127.0.0.1\n' "$domain" "$(cfg EZMD_HTTPS_PORT 443)"
  fi
}

# wait_ready <seconds>: poll <stack_url>/readyz until it answers 200.
wait_ready() {
  local deadline url code
  local -a extra=()
  deadline=$(($(date +%s) + $1))
  url="$(stack_url)"
  read -r -a extra <<<"$(stack_curl_args)"
  while :; do
    code="$(curl -sS -k --max-time 10 ${extra[@]+"${extra[@]}"} -o /dev/null -w '%{http_code}' "$url/readyz" 2>/dev/null || true)"
    [ "$code" = 200 ] && return 0
    [ "$(date +%s)" -lt "$deadline" ] || return 1
    sleep 2
  done
}

# stackctl <args...>: run deploy/stackctl.py inside a one-off api container (stdin and stdout pass through).
# The script travels base64-encoded in argv, so no bind mount or host path translation is needed.
stackctl() {
  local b64
  b64="$(base64 <"$DEPLOY_DIR/stackctl.py" | tr -d '\n\r')"
  compose run --rm --no-deps -T api python -c \
    'import base64,sys; s=base64.b64decode(sys.argv[1]); sys.argv=["stackctl",*sys.argv[2:]]; exec(compile(s,"stackctl.py","exec"),{"__name__":"__main__"})' \
    "$b64" "$@"
}

# app_services: every running-state service except redis (what restore and upgrade stop and start).
app_services() {
  compose config --services | grep -vx redis
}
