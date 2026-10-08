#!/usr/bin/env bash
# ezmd compose smoke test (P0-T11).
#
#   deploy/smoke.sh                       build + start deploy/docker-compose.yml, test, leave it running
#   deploy/smoke.sh --down                same, then `docker compose down -v`
#   deploy/smoke.sh --no-build            start without rebuilding images
#   deploy/smoke.sh --no-up               test the running stack (no compose up)
#   deploy/smoke.sh --remote https://host test an existing instance (no bring-up, no container checks)
#
# Checks: /readyz, the web UI at / (200 HTML), upload of a small text file to /v1/convert, job polling until `done`,
# Markdown result contains the expected heading, JSON result parses, and (local mode) the
# worker-default container has no route to the internet and every app container runs as
# uid 10001 with a read-only root filesystem and no capabilities. Exits non-zero on any failure.
# The env file is EZMD_ENV_FILE (default deploy/.env; created for the run when missing), extra
# compose files come from EZMD_COMPOSE_FILES (deploy/lib.sh). SMOKE_API_KEY, when set, is sent as
# X-API-Key. The last line on success is `SMOKE_JOB=<id>`.
set -euo pipefail

# shellcheck source=deploy/lib.sh
. "$(dirname "$0")/lib.sh"
HERE="$DEPLOY_DIR"
COMPOSE=(compose)
REMOTE=""
BUILD="--build"
UP=1
DOWN=0
TIMEOUT_S="${SMOKE_TIMEOUT_S:-180}"

while [ $# -gt 0 ]; do
  case "$1" in
    --remote) REMOTE="${2:?--remote needs a URL}"; shift 2 ;;
    --no-build) BUILD=""; shift ;;
    --no-up) UP=0; BUILD=""; shift ;;
    --down) DOWN=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 64 ;;
  esac
done

fail() {
  echo "SMOKE FAIL: $*" >&2
  if [ -z "$REMOTE" ]; then
    "${COMPOSE[@]}" ps >&2 || true
    "${COMPOSE[@]}" logs --no-color --tail 60 api worker-default >&2 || true
  fi
  exit 1
}
ok() { echo "ok   $*"; }

PY=""
for cand in python3 python; do   # probe: on Windows `python3` may be a Store stub that only prints
  if "$cand" -c 'import json, secrets' >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || fail "python3 is required on the host for JSON parsing"
command -v curl >/dev/null || fail "curl is required"

# json_get <json> <dotted.path> [<fallback.path>...]: prints the first path that exists.
json_get() {
  "$PY" - "$@" <<'PY'
import json, sys
doc = json.loads(sys.argv[1])
for path in sys.argv[2:]:
    cur = doc
    try:
        for part in path.split("."):
            cur = cur[part]
    except (KeyError, TypeError):
        continue
    print(cur if not isinstance(cur, (dict, list)) else json.dumps(cur))
    sys.exit(0)
sys.exit(1)
PY
}

cleanup() {
  if [ "$DOWN" = 1 ] && [ -z "$REMOTE" ]; then "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

if [ -z "$REMOTE" ]; then
  if [ ! -f "$ENV_FILE" ]; then
    (umask 077 && if [ -f "$HERE/env.example" ]; then cp "$HERE/env.example" "$ENV_FILE"; else : > "$ENV_FILE"; fi)
    # Local smoke: plain HTTP on :8080, no ACME, fresh Redis password.
    env_set EZMD_DOMAIN ""
    env_set EZMD_ACME_EMAIL ""
    env_set EZMD_REDIS_PASSWORD "$(rand_hex 24)"
    echo "created $ENV_FILE for the smoke run"
  fi
  if [ "$UP" = 1 ]; then
    # shellcheck disable=SC2086
    "${COMPOSE[@]}" up -d $BUILD --wait --wait-timeout "$TIMEOUT_S" || {
      "${COMPOSE[@]}" ps; "${COMPOSE[@]}" logs --no-color --tail 80; fail "compose up did not become healthy"; }
  fi
  BASE="$(stack_url)"
  read -r -a RESOLVE <<<"$(stack_curl_args)"
else
  BASE="${REMOTE%/}"
  RESOLVE=()
fi
CURL=(curl -sS --max-time 30 -k ${RESOLVE[@]+"${RESOLVE[@]}"})
if [ -n "${SMOKE_API_KEY:-}" ]; then CURL+=(-H "X-API-Key: $SMOKE_API_KEY"); fi

# 1. readiness
deadline=$(( $(date +%s) + TIMEOUT_S ))
until [ "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE/readyz" 2>/dev/null || true)" = "200" ]; do
  [ "$(date +%s)" -lt "$deadline" ] || fail "$BASE/readyz not 200 after ${TIMEOUT_S}s"
  sleep 2
done
ok "readyz $BASE"

# 1b. the web UI is served at /
ui="$("${CURL[@]}" -o /dev/null -w '%{http_code} %{content_type}' "$BASE/")" || fail "GET / failed"
case "$ui" in
  "200 text/html"*) ok "web UI at /" ;;
  *) fail "GET / returned '$ui'; expected 200 text/html (is EZMD_WEB_DIST pointing at the built UI?)" ;;
esac

# 2. convert a small text file
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"; cleanup' EXIT
HEADING="ezmd smoke test"
# A nonce paragraph keeps each run from being deduplicated onto an earlier job.
printf '%s\n=================\n\nThis file checks the compose stack end to end.\n\nRun %s.\n' \
  "$HEADING" "$(date +%s)-$$" > "$TMPD/smoke.txt"
# Relative upload path: native Windows curl (Git Bash) cannot open MSYS paths like /tmp/...
resp="$(cd "$TMPD" && "${CURL[@]}" -w '\n%{http_code}' -F "file=@smoke.txt;type=text/plain" "$BASE/v1/convert")" \
  || fail "POST /v1/convert failed"
code="${resp##*$'\n'}"; body="${resp%$'\n'*}"
case "$code" in 200|201|202) ;; *) fail "POST /v1/convert returned $code: $body" ;; esac
JOB="$(json_get "$body" job.id id job_id)" || fail "no job id in convert response: $body"
ok "convert accepted job $JOB ($code)"

# 3. poll until done
state=""
while :; do
  jb="$("${CURL[@]}" "$BASE/v1/jobs/$JOB")" || fail "GET /v1/jobs/$JOB failed"
  state="$(json_get "$jb" job.state state)" || fail "no state in job response: $jb"
  case "$state" in
    done) break ;;
    failed|expired|needs_user_action) fail "job ended in state $state: $jb" ;;
  esac
  [ "$(date +%s)" -lt "$deadline" ] || fail "job $JOB still $state after ${TIMEOUT_S}s"
  sleep 1
done
ok "job $JOB done"

# 4. results
md="$("${CURL[@]}" -f "$BASE/v1/jobs/$JOB/result?format=md")" || fail "GET result format=md failed"
printf '%s\n' "$md" | grep -Eq "^#{1,2} ${HEADING}( \{#[^}]*\})?\$" || fail "Markdown lacks heading '# $HEADING':
$md"
ok "markdown has heading"
js="$("${CURL[@]}" -f "$BASE/v1/jobs/$JOB/result?format=json")" || fail "GET result format=json failed"
printf '%s' "$js" | "$PY" -c 'import json,sys; json.load(sys.stdin)' || fail "format=json is not valid JSON"
ok "json result parses"

# 5. container properties (local only)
if [ -z "$REMOTE" ]; then
  if "${COMPOSE[@]}" exec -T worker-default python -c \
      "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)" >/dev/null 2>&1; then
    fail "worker-default reached 1.1.1.1:443; it must have no internet route"
  fi
  if "${COMPOSE[@]}" exec -T worker-default python -c \
      "import socket; socket.create_connection(('8.8.8.8', 53), timeout=5)" >/dev/null 2>&1; then
    fail "worker-default reached 8.8.8.8:53; it must have no internet route"
  fi
  ok "worker-default has no internet route"
  for svc in api worker-default worker-fetch; do
    cid="$("${COMPOSE[@]}" ps -q "$svc")"
    [ -n "$cid" ] || fail "service $svc is not running"
    props="$(docker inspect --format '{{.Config.User}}|{{.HostConfig.ReadonlyRootfs}}|{{json .HostConfig.CapDrop}}' "$cid")"
    case "$props" in
      10001:10001\|true\|*ALL*) ok "$svc runs as 10001, read-only, caps dropped" ;;
      *) fail "$svc hardening mismatch: $props" ;;
    esac
  done
fi

echo "SMOKE PASS ($BASE)"
echo "SMOKE_JOB=$JOB"
