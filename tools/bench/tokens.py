"""Exact Claude token counts of each tool's output, from Anthropic's token-counting endpoint.

    uv run python -m tools.bench tokens --corpus arxiv --date D [--tools a,b] [--model claude-sonnet-5-5]

The scorers count o200k_base tokens locally, which is OpenAI's tokenizer; a Claude agent pays in Claude tokens.
`/v1/messages/count_tokens` returns the exact count for a model and costs nothing. Each output is sent once as a
single user message (embedded base64 images replaced by a placeholder, as in the local count) and the count is
cached under `<run_dir>/tokens/claude/<tool>/<doc>.json` keyed by the sha256 of the text, so a rerun over the same
outputs makes no request. The count includes the few tokens of message framing; it is the same constant for every
tool. scoring/arxiv.py reads the cache and reports `arxiv-claude-tokens-per-page`.

The key comes from ANTHROPIC_API_KEY or the Windows Credential Manager (`keyring`: service `anthropic`, user
`api_key`). It is never printed or written anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.bench.schema import DocResult, read_results
from tools.bench.scoring.arxiv import strip_data_uris
from tools.bench.scoring.text import read_output

DEFAULT_MODEL = "claude-sonnet-5-5"
ENDPOINT = "https://api.anthropic.com/v1/messages/count_tokens"
API_VERSION = "2023-06-01"
RETRIES = 6


def api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import keyring

        found = keyring.get_password("anthropic", "api_key")
        return str(found) if found else None
    except Exception:  # no keyring backend on this platform
        return None


def count_remote(text: str, model: str, key: str) -> int:
    """One count_tokens call with retries on rate limits and server errors."""
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": text}]}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"},
    )
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (fixed https endpoint)
                return int(json.loads(resp.read())["input_tokens"])
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 529) and attempt + 1 < RETRIES:
                time.sleep(2**attempt)
                continue
            detail = exc.read()[:200].decode("utf-8", "replace")
            raise RuntimeError(f"count_tokens HTTP {exc.code}: {detail}") from None
    raise RuntimeError("count_tokens: retries exhausted")


def cache_path(run_dir: Path, tool: str, doc_id: str) -> Path:
    return run_dir / "tokens" / "claude" / tool / f"{doc_id}.json"


def cached_record(run_dir: Path, result: DocResult) -> dict[str, Any] | None:
    """`{"tokens", "model"}` of this output's cached count, when `tokens` has run and the output is unchanged;
    the model is part of the record because each model's tokenizer gives its own count."""
    path = cache_path(run_dir, result.tool, result.doc_id)
    if not path.exists() or not result.output:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    text = strip_data_uris(read_output(result, run_dir))
    if data.get("sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest() or not data.get("model"):
        return None
    return {"tokens": int(data["tokens"]), "model": str(data["model"])}


def cached_count(run_dir: Path, result: DocResult) -> int | None:
    record = cached_record(run_dir, result)
    return None if record is None else int(record["tokens"])


def count_run(
    run_dir: Path,
    tools: list[str] | None,
    *,
    model: str = DEFAULT_MODEL,
    counter: Callable[[str, str], int] | None = None,
) -> dict[str, int]:
    """Count every ok output of the run (cached), returning {tool: documents counted}. `counter(text, model)`
    replaces the API in tests."""
    if counter is None:
        key = api_key()
        if not key:
            raise SystemExit("no Anthropic API key: set ANTHROPIC_API_KEY or store it in keyring (anthropic/api_key)")

        def counter(text: str, model: str) -> int:
            return count_remote(text, model, key)

    counted: dict[str, int] = {}
    for result in read_results(run_dir / "results.jsonl"):
        if result.status != "ok" or not result.output or (tools is not None and result.tool not in tools):
            continue
        path = cache_path(run_dir, result.tool, result.doc_id)
        text = strip_data_uris(read_output(result, run_dir))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("sha256") == digest and cached.get("model") == model:
                counted[result.tool] = counted.get(result.tool, 0) + 1
                continue
        tokens = counter(text, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {"tokens": tokens, "model": model, "sha256": digest}
        path.write_text(json.dumps(record), encoding="utf-8")
        counted[result.tool] = counted.get(result.tool, 0) + 1
        print(f"{result.tool} {result.doc_id}: {tokens} tokens", flush=True)
    return counted


def main(run_dir: Path, tools: list[str] | None, *, model: str | None = None) -> int:
    if not (run_dir / "results.jsonl").exists():
        print(f"no results under {run_dir}", file=sys.stderr)
        return 1
    counted = count_run(run_dir, tools, model=model or DEFAULT_MODEL)
    for tool, n in sorted(counted.items()):
        print(f"{tool}: {n} documents counted")
    return 0
