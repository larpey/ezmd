"""The `ccgov` corpus: modern everyday files from Common Crawl, .gov, .mil and .edu hosts, every document type.

Govdocs1 (tools/bench/corpora.py) is a 2009 crawl with no OOXML, no EPUB, no subtitles, no notebooks. This corpus
is the same idea from the current web: Common Crawl's columnar index lists every capture of a monthly crawl with
its detected MIME type and its byte range in a public WARC file, so a manifest of government and university
documents by type is one query, and the files come down by HTTP range request, one per capture, with no site
crawled. Images, audio and video are not in Common Crawl at all; those come from other sources.

Layout under `EZMD_CCGOV` (default `<cache>/corpora/ccgov`):

    manifest.<crawl>.jsonl   one capture per content digest (url, tld, mime, digest, warc, offset, length, ...)
    pulled.jsonl             append-only log of files on disk (resume state): digest, path, bytes, url, tld, mime
    files/<mime slug>/<dd>/<digest>.<ext>   the payloads, named by digest, with the publisher's extension

`build_manifest` needs duckdb and the index slices (`cc-index/table/cc-main/warc/crawl=.../subset=warc/`) that
hold the three top-level domains, downloaded once; `pull` needs nothing but the network. Common Crawl throttles
with HTTP 403; the puller backs off globally and resumes from `pulled.jsonl`.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import http.client
import json
import os
import re
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from tools.bench.config import cache_dir
from tools.bench.schema import Doc

DATA_URL = "https://data.commoncrawl.org/"
USER_AGENT = "ezmd-bench/1 (https://github.com/larpey/ezmd)"
TLDS = ("gov", "mil", "edu")
HTML_CAP = 60_000
PDF_CAP = 80_000
"""HTML and PDF are most of the crawl; every other document type is taken in full."""
_EXT = re.compile(r"^[a-z0-9]{1,8}$")
_MIME_EXT = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "application/json": "json",
    "application/xml": "xml",
    "text/csv": "csv",
}


def ccgov_root() -> Path:
    return Path(os.environ.get("EZMD_CCGOV", cache_dir() / "corpora" / "ccgov"))


def mime_slug(mime: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", mime.lower()).strip("-")[:80] or "unknown"


def url_extension(url: str) -> str | None:
    path = url.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1]
    if "." not in path:
        return None
    ext = path.rsplit(".", 1)[1].lower()
    return ext if _EXT.match(ext) else None


def file_path(root: Path, row: dict[str, Any]) -> Path:
    ext = url_extension(str(row["url"])) or _MIME_EXT.get(str(row["mime"]))
    name = str(row["digest"]) + (f".{ext}" if ext else "")
    return root / "files" / mime_slug(str(row["mime"])) / name[:2] / name


def _sql(template: str, **values: str) -> str:
    """Fill `$NAME` placeholders with this harness's own paths and names (no user input reaches the query)."""
    for name, value in values.items():
        template = template.replace(f"${name}", value.replace("'", "''"))
    return template


def build_manifest(index_dir: Path, crawl: str, root: Path) -> Path:
    """One capture per content digest from the downloaded index slices, document types in full, HTML and PDF as
    seeded samples, ordered rarest type first so a pull stopped early still has the variety."""
    import duckdb  # type: ignore[import-not-found]  # only for the manifest step

    out = root / f"manifest.{crawl}.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect()
    slices = str(index_dir / "*.parquet").replace("\\", "/")
    c.execute(
        _sql(
            """
        create table cap as
        select url, url_host_tld as tld, content_mime_detected as mime, content_digest as digest,
               warc_filename as warc, warc_record_offset as "offset", warc_record_length as length,
               fetch_time, '$CRAWL' as crawl
        from read_parquet('$SLICES')
        where url_host_tld in ('gov', 'mil', 'edu') and fetch_status = 200 and content_truncated is null
          and content_mime_detected is not null and content_digest is not null
        """,
            CRAWL=crawl,
            SLICES=slices,
        )
    )
    c.execute(
        """
        create table uniq as select * exclude (rn) from (
          select *, row_number() over (
            partition by digest order by (tld = 'gov') desc, (tld = 'mil') desc, length(url)) rn from cap
        ) where rn = 1
        """
    )
    c.execute(
        _sql(
            """
        create table manifest as
        select u.*, c.n as mime_total,
          case when u.mime in ('text/html', 'application/xhtml+xml') then $HTML_CAP
               when u.mime = 'application/pdf' then $PDF_CAP else 2000000000 end as cap,
          row_number() over (partition by u.mime order by hash(u.digest)) as pick
        from uniq u join (select mime, count(*) n from uniq group by 1) c using (mime)
        """,
            HTML_CAP=str(HTML_CAP),
            PDF_CAP=str(PDF_CAP),
        )
    )
    c.execute("delete from manifest where pick > cap")
    target = str(out).replace("\\", "/")
    c.execute(
        _sql(
            """
        copy (select url, tld, mime, digest, warc, "offset", length, fetch_time, crawl, mime_total
              from manifest order by mime_total asc, pick asc) to '$TARGET' (format json)
        """,
            TARGET=target,
        )
    )
    return out


def read_manifests(root: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(root.glob("manifest.*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def read_pulled(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "pulled.jsonl"
    out: dict[str, dict[str, Any]] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rec = json.loads(line)
                    out[rec["digest"]] = rec
    return out


def split_record(raw: bytes) -> bytes:
    """The HTTP body of one gzipped WARC response record: WARC headers, blank line, HTTP headers, blank line."""
    data = gzip.decompress(raw)
    _, _, rest = data.partition(b"\r\n\r\n")
    _, _, body = rest.partition(b"\r\n\r\n")
    return body.removesuffix(b"\r\n\r\n")  # the WARC record terminator is not part of the payload


def cc_digest(body: bytes) -> str:
    return base64.b32encode(hashlib.sha1(body).digest()).decode("ascii")  # noqa: S324 - Common Crawl's own digest


RATE_PER_SECOND = 10.0
RATE_MIN = 1.0
"""Requests per second across all workers, adapted as Common Crawl answers: a 403 cuts the rate by a fifth
and pauses everyone two seconds; five hundred clean requests raise it a tenth, up to the start value. The
first pulls at a fixed 18 to 30 per second were refused for minutes at a time."""


class Throttle:
    """A token bucket every worker draws from, with an additive-increase, multiplicative-decrease rate."""

    def __init__(self, rate: float = RATE_PER_SECOND) -> None:
        self._until = 0.0
        self._lock = threading.Lock()
        self._ceiling = rate
        self.rate = rate
        self._next = time.monotonic()
        self._clean = 0
        self.refusals = 0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(self._next, now, self._until)
            self._next = slot + 1.0 / self.rate
        delay = slot - now
        if delay > 0:
            time.sleep(delay)

    def refuse(self, attempt: int) -> None:
        with self._lock:
            self.refusals += 1
            self._clean = 0
            self.rate = max(RATE_MIN, self.rate * 0.8)
            self._until = max(self._until, time.monotonic() + 2.0 + attempt)

    def success(self) -> None:
        with self._lock:
            self._clean += 1
            if self._clean >= 500:
                self._clean = 0
                self.rate = min(self._ceiling, self.rate * 1.1)


_local = threading.local()
DATA_HOST = "data.commoncrawl.org"
REQUEST_TIMEOUT = 20.0
"""A fresh connection to data.commoncrawl.org sometimes hangs before the first byte; dropping it after 20 s and
reconnecting costs far less than waiting (the range itself arrives in well under a second)."""


def _connection(fresh: bool = False) -> http.client.HTTPSConnection:
    """One keep-alive connection per thread: a new TLS handshake per range request is what wedged the first
    pull (eight threads, thousands of short-lived connections)."""
    conn = getattr(_local, "conn", None)
    if conn is None or fresh:
        if conn is not None:
            conn.close()
        conn = http.client.HTTPSConnection(DATA_HOST, timeout=REQUEST_TIMEOUT)
        _local.conn = conn
    return conn


def fetch_record(row: dict[str, Any], throttle: Throttle, attempts: int = 6) -> bytes:
    path = "/" + str(row["warc"])
    start, length = int(row["offset"]), int(row["length"])
    headers = {"User-Agent": USER_AGENT, "Range": f"bytes={start}-{start + length - 1}"}
    fresh = False
    for attempt in range(attempts):
        throttle.wait()
        conn = _connection(fresh)
        fresh = True
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except (http.client.HTTPException, TimeoutError, OSError):
            time.sleep(1 + attempt)
            continue
        if resp.status in (200, 206):
            throttle.success()
            return data
        if resp.status in (403, 429, 503):
            throttle.refuse(attempt)
            continue
        raise RuntimeError(f"HTTP {resp.status} for {path} bytes={start}-{start + length - 1}")
    raise RuntimeError(f"gave up after {attempts} attempts: {path}")


def pull(root: Path, workers: int = 6, limit: int | None = None, log_every: int = 200) -> dict[str, int]:
    """Download every manifest row not yet in `pulled.jsonl`. A file named STOP in the root stops the run
    cleanly between files. Returns counts."""
    done = read_pulled(root)
    todo = [r for r in read_manifests(root) if r["digest"] not in done]
    if limit is not None:
        todo = todo[:limit]
    log_path = root / "pulled.jsonl"
    fail_path = root / "failed.jsonl"
    lock = threading.Lock()
    throttle = Throttle()
    counts = {"pulled": 0, "failed": 0, "mismatch": 0, "skipped": len(done), "refusals": 0}
    stop = root / "STOP"
    t0 = time.monotonic()

    def one(row: dict[str, Any]) -> None:
        if stop.exists():
            return
        dest = file_path(root, row)
        try:
            body = split_record(fetch_record(row, throttle))
        except Exception as exc:  # logged; the row is retried on the next run
            with lock, fail_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({"digest": row["digest"], "error": f"{type(exc).__name__}: {exc}"[:300]}) + "\n")
                counts["failed"] += 1
            return
        ok = cc_digest(body) == row["digest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        rec = {
            "digest": row["digest"],
            "path": dest.relative_to(root).as_posix(),
            "bytes": len(body),
            "url": row["url"],
            "tld": row["tld"],
            "mime": row["mime"],
            "crawl": row["crawl"],
            "digest_ok": ok,
        }
        with lock, log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec) + "\n")
            counts["pulled"] += 1
            counts["mismatch"] += 0 if ok else 1
            n = counts["pulled"]
        if n % log_every == 0:
            rate = n / (time.monotonic() - t0)
            failed, refused = counts["failed"], throttle.refusals
            limit = throttle.rate
            msg = f"ccgov: {n} pulled, {failed} failed, {refused} refusals, {rate:.1f}/s, limit {limit:.1f}/s"
            print(msg, flush=True)
            with lock:
                counts["refusals"] = refused

    with ThreadPoolExecutor(workers) as pool:
        for i in range(0, len(todo), 2000):  # bounded batches: the manifest has hundreds of thousands of rows
            if stop.exists():
                break
            list(pool.map(one, todo[i : i + 2000]))
    print(f"ccgov: {counts}", flush=True)
    return counts


def ccgov(sample: int | None = None) -> list[Doc]:
    """Every pulled file; category = the MIME slug Common Crawl detected, so a mislabelled file is part of the
    variety just as in govdocs1."""
    from tools.bench.corpora import _sample

    root = ccgov_root()
    docs = []
    for rec in read_pulled(root).values():
        path = root / str(rec["path"])
        if path.is_file():
            meta = {k: rec[k] for k in ("url", "tld", "mime", "crawl", "bytes")}
            docs.append(Doc("ccgov", str(rec["digest"]), path, mime_slug(str(rec["mime"])), meta))
    if not docs:
        raise FileNotFoundError(f"ccgov: nothing pulled under {root}; run `python -m tools.bench fetch --only ccgov`")
    docs.sort(key=lambda d: d.id)
    return _sample(docs, sample)


def fetch_ccgov() -> None:
    """`fetch --only ccgov`: build the manifest when an index directory is given (`EZMD_CC_INDEX`, with the
    crawl name in `EZMD_CC_CRAWL`) and no manifest exists yet, then pull. `EZMD_CCGOV_WORKERS` sets the threads."""
    root = ccgov_root()
    index_dir = os.environ.get("EZMD_CC_INDEX")
    if index_dir and not list(root.glob("manifest.*.jsonl")):
        crawl = os.environ.get("EZMD_CC_CRAWL", "CC-MAIN-2026-43")
        print(f"ccgov: manifest from {index_dir} ({crawl}) ...", flush=True)
        build_manifest(Path(index_dir), crawl, root)
    pull(root, workers=int(os.environ.get("EZMD_CCGOV_WORKERS", "6")))
