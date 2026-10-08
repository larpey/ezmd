# syntax=docker/dockerfile:1.7
#
# ezmd images. One multi-stage file, build from the repo root:
#   docker build -f deploy/Dockerfile --target api        -t ghcr.io/larpey/ezmd-api .
#   docker build -f deploy/Dockerfile --target worker     -t ghcr.io/larpey/ezmd-worker .
#   docker build -f deploy/Dockerfile --target fetch-node -t ghcr.io/larpey/ezmd-fetch-node .
#
# Base images are pinned by multi-arch index digest; Renovate bumps them (docker:pinDigests).
# All runtime images run as uid/gid 10001 and work with a read-only root filesystem
# (bytecode is compiled at build time, scratch goes to the /tmp tmpfs).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ARG NODE_IMAGE=node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------------------------
# web: build apps/web/dist. Until the pnpm workspace exists the stage emits a placeholder page,
# unless EZMD_REQUIRE_WEB=1 (CI sets it once apps/web lands), in which case it fails.
# ---------------------------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS web
ARG EZMD_REQUIRE_WEB=0
ENV PNPM_HOME=/pnpm CI=true
RUN corepack enable
WORKDIR /src
RUN --mount=type=bind,target=/ctx \
    --mount=type=cache,id=ezmd-pnpm-store,target=/pnpm/store \
    set -eu; \
    mkdir -p /out; \
    if [ -f /ctx/pnpm-lock.yaml ] && [ -f /ctx/apps/web/package.json ]; then \
      for p in package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc apps/web apps/extension packages/sdk-ts docs/api; do \
        if [ -e "/ctx/$p" ]; then mkdir -p "$(dirname "$p")"; cp -a "/ctx/$p" "$p"; fi; \
      done; \
      pnpm config set store-dir /pnpm/store; \
      pnpm install --frozen-lockfile; \
      pnpm --filter "./apps/web..." build; \
      cp -a apps/web/dist/. /out/; \
    elif [ "$EZMD_REQUIRE_WEB" = "1" ]; then \
      echo "apps/web or pnpm-lock.yaml missing and EZMD_REQUIRE_WEB=1" >&2; exit 1; \
    else \
      echo "WARNING: apps/web not present yet; shipping a placeholder UI" >&2; \
      printf '<!doctype html><meta charset="utf-8"><title>ezmd</title><p>ezmd API is running. The web UI was not built into this image.</p>\n' > /out/index.html; \
    fi

# ---------------------------------------------------------------------------------------------
# py-base: shared runtime base (non-root user, state dirs, env).
# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS py-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/app/.venv/bin:$PATH \
    HOME=/tmp \
    EZMD_TMP=/tmp \
    EZMD_DATA_DIR=/var/lib/ezmd \
    EZMD_BLOB_FS_ROOT=/var/lib/ezmd-blobs \
    EZMD_CACHE_DIR=/var/lib/ezmd/cache \
    EZMD_MODEL_DIR=/opt/ezmd/models
RUN groupadd --system --gid 10001 ezmd \
 && useradd --system --uid 10001 --gid 10001 --home-dir /var/lib/ezmd --no-create-home --shell /usr/sbin/nologin ezmd \
 && mkdir -p /app /var/lib/ezmd/cache /var/lib/ezmd-blobs /opt/ezmd/models \
 && chown -R 10001:10001 /var/lib/ezmd /var/lib/ezmd-blobs
WORKDIR /app

# ---------------------------------------------------------------------------------------------
# py-build: resolve the locked, non-dev dependency set into /app/.venv.
# ---------------------------------------------------------------------------------------------
FROM py-base AS py-build
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
# Third-party dependencies first (cached layer), workspace members afterwards.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/README.md packages/core/
COPY packages/converters/pyproject.toml packages/converters/README.md packages/converters/
COPY packages/mcp/pyproject.toml packages/mcp/README.md packages/mcp/
COPY apps/api/pyproject.toml apps/api/README.md apps/api/
COPY apps/fetch-node/pyproject.toml apps/fetch-node/README.md apps/fetch-node/
ARG UV_SYNC_ARGS="--all-packages"
RUN --mount=type=cache,id=ezmd-uv,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace ${UV_SYNC_ARGS}
COPY packages packages
COPY apps/api apps/api
COPY apps/fetch-node apps/fetch-node
RUN --mount=type=cache,id=ezmd-uv,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable ${UV_SYNC_ARGS}
# Strip debug symbols from extension modules (uvloop alone ships ~14 MB of them). Libraries
# vendored by auditwheel (*.libs/) are left alone: patchelf'd ELF files do not survive strip.
RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils \
 && rm -rf /var/lib/apt/lists/* \
 && find /app/.venv -type f -name '*.so*' -not -path '*.libs/*' -exec strip --strip-unneeded {} + \
 && find /app/.venv/lib/python3.12/site-packages/numpy -depth -type d -name tests -exec rm -rf {} +
# numpy's own test suite (about 20 MB) is never imported at runtime (P1-T14 image budget, D-0012).
# Pre-bake: magika ships its model in the wheel; prove it loads offline so first use never downloads.
RUN /app/.venv/bin/python -c "import magika; magika.Magika()"

# Worker venv: the shared venv plus converter extras (docs/spec/part4.md 4.9.1). Default `data`
# (pyarrow, Apache-2.0) so Parquet converts in the stock image. `docs` (Docling + torch) is opt-in:
# the universal lock resolves the CUDA torch wheels on Linux (several GB), see docs/selfhost.md.
# Never put `nonfree` or `7z` here: the published image must stay on the default license allowlist.
FROM py-build AS py-build-worker
ARG EZMD_WORKER_EXTRAS="data"
RUN --mount=type=cache,id=ezmd-uv,target=/root/.cache/uv \
    set -eu; \
    extras=""; \
    for e in ${EZMD_WORKER_EXTRAS}; do \
      case "$e" in nonfree|7z) echo "extra '$e' is not allowed in the worker image" >&2; exit 1 ;; esac; \
      extras="$extras --extra $e"; \
    done; \
    if [ -n "$extras" ]; then \
      uv sync --frozen --no-dev --no-editable ${UV_SYNC_ARGS} $extras; \
      rm -rf /app/.venv/lib/python3.12/site-packages/pyarrow/tests; \
      find /app/.venv -type f -name '*.so' -not -path '*.libs/*' -exec strip --strip-unneeded {} +; \
    fi

FROM py-build AS py-build-fetch
RUN --mount=type=cache,id=ezmd-uv,target=/root/.cache/uv \
    rm -rf /app/.venv \
 && uv sync --frozen --no-dev --no-editable --package ezmd-fetch-node \
 && find /app/.venv -type f -name '*.so*' -not -path '*.libs/*' -exec strip --strip-unneeded {} +

# ---------------------------------------------------------------------------------------------
# runtime-common: OCI labels + libmagic (detection by content, Part 1 section 5.1).
# ---------------------------------------------------------------------------------------------
FROM py-base AS runtime-common
ARG EZMD_VERSION=0.0.0-dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/larpey/ezmd" \
      org.opencontainers.image.version="${EZMD_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="ezmd contributors" \
      io.modelcontextprotocol.server.name="io.github.larpey/ezmd"
# pip/ensurepip are not needed at runtime (the venv is built by uv) and only add attack surface.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/lib/python3.12/site-packages/pip-* \
           /usr/local/lib/python3.12/ensurepip /usr/local/bin/pip /usr/local/bin/pip3*

# ---------------------------------------------------------------------------------------------
# api: FastAPI + built web UI. No torch, no converters' heavy extras.
# ---------------------------------------------------------------------------------------------
FROM runtime-common AS api
LABEL org.opencontainers.image.title="ezmd-api" \
      org.opencontainers.image.description="ezmd HTTP API and web UI"
COPY --from=py-build --chown=0:0 /app/.venv /app/.venv
COPY --from=web --chown=0:0 /out /app/apps/web/dist
ENV EZMD_WEB_DIST=/app/apps/web/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"]
CMD ["uvicorn", "ezmd_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]

# ---------------------------------------------------------------------------------------------
# worker: RQ worker for the default and fetch queues. Adds pandoc (separate GPL executable, not
# linked; see docs/licenses.md) and iptables for the optional egress allowlist. ffmpeg arrives
# with the worker-media target (Phase 2). bubblewrap is deliberately NOT installed: inside this
# container (no caps, seccomp denies mount) it cannot create namespaces, and
# ezmd.core.sandbox would pick it up from PATH and fail every external command.
# EZMD_WORKER_APT_PACKAGES adds Debian packages, e.g. "libreoffice-core-nogui libreoffice-writer-nogui
# libreoffice-calc-nogui libreoffice-impress-nogui" for legacy .doc/.ppt/.xls (about +500 MB).
# ---------------------------------------------------------------------------------------------
FROM runtime-common AS worker
ARG EZMD_WORKER_APT_PACKAGES=""
LABEL org.opencontainers.image.title="ezmd-worker" \
      org.opencontainers.image.description="ezmd sandboxed conversion worker"
RUN apt-get update \
 && apt-get install -y --no-install-recommends pandoc-data pandoc iptables tini ${EZMD_WORKER_APT_PACKAGES} \
 && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*
COPY --from=py-build-worker --chown=0:0 /app/.venv /app/.venv
COPY --chown=0:0 --chmod=0755 deploy/egress-allowlist.sh /usr/local/bin/egress-allowlist.sh
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import os,sys,redis; sys.exit(0 if redis.Redis.from_url(os.environ['EZMD_REDIS_URL'], socket_timeout=3).ping() else 1)"]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/egress-allowlist.sh"]
CMD ["python", "-m", "ezmd_api.worker", "--queues", "default"]

# ---------------------------------------------------------------------------------------------
# fetch-node: residential fetcher for the Raspberry Pi (Phase 3 fills in yt-dlp and Deno).
# ---------------------------------------------------------------------------------------------
FROM runtime-common AS fetch-node
LABEL org.opencontainers.image.title="ezmd-fetch-node" \
      org.opencontainers.image.description="ezmd residential fetch node"
COPY --from=py-build-fetch --chown=0:0 /app/.venv /app/.venv
USER 10001:10001
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=5 \
  CMD ["python", "-c", "import ezmd_fetch_node"]
CMD ["python", "-c", "import ezmd_fetch_node, sys; print('ezmd fetch-node: not implemented until Phase 3', file=sys.stderr); sys.exit(1)"]
