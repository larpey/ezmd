# ezmd developer entry points. Every gate CI runs is reachable from here.
# Requires: uv, pnpm (corepack), docker (for up/smoke/images). Use a POSIX shell (Git Bash on Windows).
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

COMPOSE := docker compose -f deploy/docker-compose.yml
TMPDIR ?= /tmp
HAS_PNPM := $(shell test -f pnpm-lock.yaml && command -v pnpm >/dev/null 2>&1 && echo yes)

.PHONY: help gates lint fmt typecheck test golden licenses audit up down smoke images linux-gates

help:  ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

gates: lint typecheck test golden licenses audit  ## every CI gate, in CI order
	@echo "all gates passed"

lint:  ## ruff check + format check, pnpm lint
	uv run ruff check .
	uv run ruff format --check .
ifeq ($(HAS_PNPM),yes)
	pnpm -r lint
endif

fmt:  ## apply ruff fixes and formatting
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## mypy (strict on core) + pnpm typecheck
	uv run mypy --strict packages/core/src
	uv run mypy apps/api/src packages/converters/src packages/mcp/src
ifeq ($(HAS_PNPM),yes)
	pnpm -r typecheck
endif

test:  ## unit tests (python + typescript)
	uv run pytest packages apps tests -q
ifeq ($(HAS_PNPM),yes)
	pnpm -r test
endif

golden:  ## fixture (golden) tests
	uv run pytest fixtures -q

licenses:  ## license allowlist for the default dependency trees
	uv run python tools/license_check.py
ifeq ($(HAS_PNPM),yes)
	pnpm licenses list --prod --json > $(TMPDIR)/ezmd-nodelic.json
	if [ -f tools/license_check.mjs ]; then node tools/license_check.mjs < $(TMPDIR)/ezmd-nodelic.json; \
	else uv run python tools/license_check.py --skip-python --pnpm-json $(TMPDIR)/ezmd-nodelic.json; fi
endif

audit:  ## pip-audit on the locked default tree, pnpm audit
	uv export --frozen --no-dev --all-packages --format requirements-txt --no-emit-workspace > $(TMPDIR)/ezmd-req.txt
	uv run pip-audit --strict --disable-pip -r $(TMPDIR)/ezmd-req.txt $$(uv run --no-project python -c "import tomllib,datetime as d; t=tomllib.load(open('tools/audit_ignore.toml','rb')); print(' '.join('--ignore-vuln '+e['id'] for e in t.get('pip',[]) if d.date.fromisoformat(str(e['expires']))>=d.date.today()))")
ifeq ($(HAS_PNPM),yes)
	pnpm audit --audit-level=high --prod
endif

images:  ## build all runtime images locally
	for t in api worker fetch-node; do docker build -f deploy/Dockerfile --target $$t -t ghcr.io/larpey/ezmd-$$t:dev .; done

up:  ## build and start the compose stack
	$(COMPOSE) up -d --build --wait

down:  ## stop the compose stack (keeps volumes)
	$(COMPOSE) down

smoke:  ## bring the stack up and run the end-to-end smoke test
	bash deploy/smoke.sh

linux-gates:  ## run the Python gates in a throwaway Linux container (for Windows/macOS hosts)
	bash tools/linux_gates.sh
