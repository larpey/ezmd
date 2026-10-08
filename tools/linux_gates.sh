#!/usr/bin/env bash
# Run the Python quality gates inside a throwaway Linux container (mirrors CI's ubuntu job).
# Useful from Windows or macOS hosts: POSIX-only code paths (resource limits, process groups,
# bubblewrap probing, libmagic) are exercised the way they are in production.
#
# Usage: tools/linux_gates.sh [pytest args...]
# Requires Docker. The repo is mounted read-write; the virtualenv lives in a named volume so it
# never collides with a host .venv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Git Bash on Windows rewrites Unix-looking arguments (-w /src) into Windows paths; turn that off and
# hand Docker a native path for the bind mount instead.
export MSYS_NO_PATHCONV=1
if command -v cygpath >/dev/null 2>&1; then ROOT="$(cygpath -m "$ROOT")"; fi
IMAGE="python:3.12-slim-bookworm"
UV_VERSION="0.12.23"
# One virtualenv volume per checkout, so parallel worktrees never share (and corrupt) a venv.
VENV_VOLUME="intomd-linux-venv-$(basename "$ROOT" | tr -c "A-Za-z0-9_.-" "_" | tr "A-Z" "a-z")"

exec docker run --rm \
  -v "$ROOT":/src \
  -v "$VENV_VOLUME":/venv \
  -v intomd-linux-uv-cache:/root/.cache/uv \
  -e UV_PROJECT_ENVIRONMENT=/venv \
  -e UV_LINK_MODE=copy \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -w /src \
  "$IMAGE" bash -euo pipefail -c '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq --no-install-recommends libmagic1 curl ca-certificates git >/dev/null
    pip install -q "uv=='"$UV_VERSION"'" >/dev/null
    uv sync --all-packages --frozen -q
    echo "== ruff";        uv run ruff check . && uv run ruff format --check .
    echo "== mypy";        uv run mypy --strict packages/core/src && uv run mypy apps/api/src packages/converters/src packages/mcp/src
    echo "== tests";       uv run pytest packages apps tests -q -p no:cacheprovider \
                             --cov=intomd --cov=intomd_api --cov=intomd_converters --cov-fail-under=80 "$@"
    echo "== fixtures";    uv run pytest fixtures -q -p no:cacheprovider
    echo "== licenses";    uv run python tools/license_check.py
    echo "== invisible";   python tools/check_invisible_chars.py
    echo "LINUX GATES PASS"
  ' bash "$@"
