#!/usr/bin/env bash
# Integration stack for tests/integration, `tests/security -m network` and the Playwright suite
# (P1-T15; docs/spec/part4.md 4.14.3). Used by .github/workflows/integration.yml and locally.
#
#   tests/integration/stack.sh up        bootstrap the core compose stack plus the fixture server, built
#                                        from this checkout (deploy/bootstrap.sh --plain-http --build)
#   tests/integration/stack.sh private   phase 2: recreate the app services with
#                                        INTOMD_ALLOW_PRIVATE_NETWORKS=true (URL jobs may fetch the in-network
#                                        fixture server) and a roomier anonymous creation limit for the browser
#                                        suite. Run the SSRF and rate-limit tests before this step.
#   tests/integration/stack.sh env       print KEY=VALUE lines for the test runners (>> "$GITHUB_ENV")
#   tests/integration/stack.sh logs      compose logs for every service
#   tests/integration/stack.sh down      docker compose down -v
#
# Environment (optional): INTOMD_IT_DIR (state dir; default $RUNNER_TEMP/intomd-it or /tmp/intomd-it),
# COMPOSE_PROJECT_NAME (default intomd-it, so a developer's own `intomd` stack is untouched),
# INTOMD_PLAIN_PORT (default 8080).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${INTOMD_IT_DIR:-${RUNNER_TEMP:-/tmp}/intomd-it}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-intomd-it}"
export INTOMD_COMPOSE_FILES="${INTOMD_COMPOSE_FILES:-../tests/integration/compose.fixtures.yml}"
export INTOMD_ENV_FILE="${INTOMD_ENV_FILE:-$STATE_DIR/intomd.env}"
mkdir -p "$STATE_DIR"

# shellcheck source=deploy/lib.sh
. "$HERE/../../deploy/lib.sh"

KEY_FILE="$STATE_DIR/owner.key"

up() {
  if [ ! -f "$ENV_FILE" ]; then
    (umask 077 && cp "$DEPLOY_DIR/env.example" "$ENV_FILE")
  fi
  # The browser suite converts two files on one page and re-reads results often; the creation limit
  # stays at the default 20 per 60 s so the 21st anonymous request gets 429 (4.14.3).
  env_set INTOMD_ANON_RATELIMIT_MAX 20
  env_set INTOMD_ANON_RATELIMIT_WINDOW_S 60
  env_set INTOMD_ANON_CONCURRENCY 4
  env_set INTOMD_ANON_RESULT_RATELIMIT_MAX 2000
  env_set INTOMD_ANON_SSE_MAX 50
  env_set INTOMD_ALLOW_PRIVATE_NETWORKS false
  bash "$DEPLOY_DIR/bootstrap.sh" --plain-http --build --key-out "$KEY_FILE"
}

private() {
  env_set INTOMD_ALLOW_PRIVATE_NETWORKS true
  env_set INTOMD_ANON_RATELIMIT_MAX 200
  compose up -d --no-build --wait --wait-timeout "${INTOMD_WAIT_TIMEOUT_S:-300}"
  wait_ready 120 || die "$(stack_url)/readyz did not answer 200 after enabling private networks"
}

print_env() {
  printf 'INTOMD_BASE_URL=%s\n' "$(stack_url)"
  printf 'PLAYWRIGHT_BASE_URL=%s\n' "$(stack_url)"
  printf 'INTOMD_API_KEY_FILE=%s\n' "$(native_path "$KEY_FILE")"
  printf 'INTOMD_FIXTURE_ORIGIN=%s\n' "http://web.fixtures.example:8000"
  printf 'INTOMD_NETWORK_TESTS=1\n'
}

case "${1:-}" in
  up) up ;;
  private) private ;;
  env) print_env ;;
  logs) compose logs --no-color ;;
  down) compose down -v --remove-orphans ;;
  *) sed -n '2,18p' "$0"; exit 64 ;;
esac
