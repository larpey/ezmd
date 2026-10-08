#!/usr/bin/env bash
# intomd compose smoke test (P0-T11).
#
#   deploy/smoke.sh                       build + start deploy/docker-compose.yml, test, leave it running
#   deploy/smoke.sh --down                same, then `docker compose down -v`
#   deploy/smoke.sh --no-build            start without rebuilding images
#   deploy/smoke.sh --remote https://host test an existing instance (no bring-up, no container checks)
#
# Checks: /readyz, upload of a small text file to /v1/convert, job polling until `done`,
# Markdown result contains the expected heading, JSON result parses, and (local mode) the
# worker-default container has no route to the internet and every app container runs as
# uid 10001 with a read-only root filesystem and no capabilities. Exits non-zero on any failure.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")
REMOTE=""
BUILD="--build"
DOWN=0
TIMEOUT_S="${SMOKE_TIMEOUT_S:-180}"

while [ $# -gt 0 ]; do
  case "$1" in
    --remote) REMOTE="${2:?--remote needs a URL}"; shift 2 ;;
    --no-build) BUILD=""; shift ;;
    --down) DOWN=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
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
  if [ ! -f "$HERE/.env" ]; then
    if [ -f "$HERE/env.example" ]; then cp "$HERE/env.example" "$HERE/.env"; else : > "$HERE/.env"; fi
    # Local smoke: plain HTTP on :8080, no ACME, fresh Redis password.
    sed -i.bak -e 's/^INTOMD_DOMAIN=.*/INTOMD_DOMAIN=/' -e 's/^INTOMD_ACME_EMAIL=.*/INTOMD_ACME_EMAIL=/' "$HERE/.env" && rm -f "$HERE/.env.bak"
    echo "INTOMD_REDIS_PASSWORD=$("$PY" -c 'import secrets; print(secrets.token_hex(24))')" >> "$HERE/.env"
    echo "created $HERE/.env for the smoke run"
  fi
  # shellcheck disable=SC2086
  "${COMPOSE[@]}" up -d $BUILD --wait --wait-timeout "$TIMEOUT_S" || {
    "${COMPOSE[@]}" ps; "${COMPOSE[@]}" logs --no-color --tail 80; fail "compose up did not become healthy"; }
  BASE="http://localhost:${INTOMD_PLAIN_PORT:-8080}"
else
  BASE="${REMOTE%/}"
fi
CURL=(curl -sS --max-time 30 -k)

# 1. readiness
deadline=$(( $(date +%s) + TIMEOUT_S ))
until [ "$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE/readyz" 2>/dev/null || true)" = "200" ]; do
  [ "$(date +%s)" -lt "$deadline" ] || fail "$BASE/readyz not 200 after ${TIMEOUT_S}s"
  sleep 2
done
ok "readyz $BASE"

# 2. convert a small text file
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"; cleanup' EXIT
HEADING="intomd smoke test"
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
