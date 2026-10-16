# OmniDocBench end-to-end evaluation environment (tools/bench/scoring/omnidoc.py). Build context: a checkout of
# https://github.com/opendatalab/OmniDocBench at the commit pinned in tools/bench/fetch.py. Its pyproject pins
# Python <3.12 and exact dependency versions; datasets/pyarrow are pinned too because `evaluate` would otherwise
# pull a pyarrow that needs NumPy 2 (the toolkit pins numpy 1.24.4). CDM (TeX Live, ImageMagick) is not installed.
FROM python:3.11.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml /tmp/p/pyproject.toml
RUN python -c "import tomllib;print('\n'.join(tomllib.load(open('/tmp/p/pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt "datasets==2.21.0" "pyarrow==17.0.0"
ENV HF_HOME=/hf
WORKDIR /eval
