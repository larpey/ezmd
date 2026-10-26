"""The `media` corpus: images, audio, video and EPUB from public collections, the types Common Crawl never holds.

- Wikimedia Commons: files by MIME type through the public API (`list=allimages&aimime=`), every image, audio
  and video type ezmd will meet: WebP, SVG, TIFF, PNG, JPEG, GIF, BMP, DjVu; Ogg, FLAC, WAV, MIDI, MP3, Opus;
  WebM and Ogg video. Licences vary by file (all free licences or public domain); kept in the cache only.
- Project Gutenberg: EPUB (with images) of a seeded sample of the catalogue, public domain.
- LibriVox (archive.org `librivoxaudio`): one MP3 chapter per recording, public domain.
- NASA image and video library (images-api.nasa.gov): audio and video assets, public domain.

Layout under `EZMD_MEDIA` (default `<cache>/corpora/media`): `files/<source>/<ext>/<name>` and `pulled.jsonl`,
the resume log (source, id, path, bytes, url, mime). Every fetcher is resumable and polite (one UA, a few
workers, back-off on 429 and 503).
"""

from __future__ import annotations

import csv
import io
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from tools.bench.config import cache_dir
from tools.bench.schema import Doc

USER_AGENT = "ezmd-bench/1 (https://github.com/larpey/ezmd; benchmark corpus, cache only)"
SEED = 20261013
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_MIMES = {
    "image/webp": 3000,
    "image/svg+xml": 3000,
    "image/tiff": 2000,
    "image/png": 3000,
    "image/jpeg": 3000,
    "image/gif": 2000,
    "image/vnd.djvu": 300,
    "application/ogg": 300,
    "audio/flac": 100,
    "audio/x-flac": 100,
    "audio/wav": 150,
    "audio/midi": 200,
    "audio/mpeg": 300,
    "audio/webm": 100,
    "video/webm": 200,
}
IMAGE_MAX_BYTES = 20 * 2**20
AV_MAX_BYTES = 60 * 2**20
GUTENBERG_CATALOG = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
GUTENBERG_EPUBS = 1000
LIBRIVOX_ITEMS = 300
NASA_PER_TYPE = 200
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def media_root() -> Path:
    return Path(os.environ.get("EZMD_MEDIA", cache_dir() / "corpora" / "media"))


def _get(url: str, timeout: float = 120, attempts: int = 6) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - https API URLs
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https URLs from the APIs above
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503, 502, 500) and attempt < attempts - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(url)


def _json(url: str) -> Any:
    return json.loads(_get(url, timeout=60).decode("utf-8"))


class Log:
    """`pulled.jsonl`: one line per file on disk, keyed by (source, id)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "pulled.jsonl"
        self._lock = threading.Lock()
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.records[(rec["source"], rec["id"])] = rec

    def has(self, source: str, item_id: str) -> bool:
        return (source, item_id) in self.records

    def count(self, source: str, mime: str | None = None) -> int:
        return sum(1 for r in self.records.values() if r["source"] == source and (mime is None or r["mime"] == mime))

    def save(self, source: str, item_id: str, url: str, mime: str, data: bytes, ext: str) -> Path:
        name = _SAFE.sub("_", item_id)[:120] + (f".{ext}" if ext and not item_id.lower().endswith(f".{ext}") else "")
        dest = self.root / "files" / source / (ext or "bin") / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        rec = {
            "source": source,
            "id": item_id,
            "path": dest.relative_to(self.root).as_posix(),
            "bytes": len(data),
            "url": url,
            "mime": mime,
        }
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.records[(source, item_id)] = rec
        return dest


def _parallel(jobs: list[Any], work: Callable[[Any], None], workers: int, label: str) -> None:
    done = 0
    failed = 0
    lock = threading.Lock()

    def one(job: Any) -> None:
        nonlocal done, failed
        try:
            work(job)
        except Exception as exc:  # one bad item never stops a corpus pull
            with lock:
                failed += 1
            print(f"{label}: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            return
        with lock:
            done += 1
            if done % 200 == 0:
                print(f"{label}: {done} pulled, {failed} failed", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))
    print(f"{label}: done, {done} pulled, {failed} failed", flush=True)


def _ext(url: str, mime: str) -> str:
    tail = url.split("?", 1)[0].rsplit("/", 1)[-1]
    ext = tail.rsplit(".", 1)[1].lower() if "." in tail else ""
    return ext if re.fullmatch(r"[a-z0-9]{1,6}", ext or "") else mime.split("/")[-1].split("+")[0]


def commons_listing(mime: str, want: int) -> Iterator[dict[str, Any]]:
    """Files of one MIME type through CirrusSearch (`filemime:`; the `allimages` MIME filter is disabled on
    Commons), oldest-indexed first, with URL, size, MIME and sha1 from `imageinfo`; stops after `want` usable
    entries. Search offsets stop at 10,000, which bounds one type at that many candidates."""
    limit = IMAGE_MAX_BYTES if mime.startswith("image/") else AV_MAX_BYTES
    offset = 0
    seen = 0
    while seen < want and offset < 10_000:
        params = {
            "action": "query",
            "list": "search",
            "srnamespace": "6",
            "srsearch": f"filemime:{mime}",
            "srlimit": "50",
            "sroffset": str(offset),
            "srprop": "",
            "format": "json",
        }
        data = _json(COMMONS_API + "?" + urllib.parse.urlencode(params))
        hits = data.get("query", {}).get("search", [])
        if not hits:
            return
        offset += len(hits)
        titles = "|".join(str(h["title"]) for h in hits)
        info = _json(
            COMMONS_API
            + "?"
            + urllib.parse.urlencode(
                {
                    "action": "query",
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime|sha1",
                    "titles": titles,
                    "format": "json",
                }
            )
        )
        for page in info.get("query", {}).get("pages", {}).values():
            for ii in page.get("imageinfo", []):
                if int(ii.get("size", 0)) <= limit and ii.get("mime") == mime:
                    seen += 1
                    yield {"name": str(page["title"]).removeprefix("File:"), "url": ii["url"], "sha1": ii.get("sha1")}
                    if seen >= want:
                        return
        time.sleep(0.5)


def fetch_commons(root: Path | None = None, mimes: dict[str, int] | None = None) -> None:
    root = root or media_root()
    log = Log(root)
    for mime, want in (mimes or COMMONS_MIMES).items():
        have = log.count("commons", mime)
        if have >= want:
            continue
        jobs = [img for img in commons_listing(mime, want) if not log.has("commons", str(img["name"]))]

        def work(img: dict[str, Any], mime: str = mime) -> None:
            data = _get(str(img["url"]), timeout=300)
            log.save("commons", str(img["name"]), str(img["url"]), mime, data, _ext(str(img["url"]), mime))

        print(f"commons {mime}: {have} on disk, {len(jobs)} to pull", flush=True)
        _parallel(jobs, work, workers=4, label=f"commons {mime}")


def fetch_gutenberg(root: Path | None = None, count: int = GUTENBERG_EPUBS) -> None:
    """A seeded sample of the catalogue's text entries as EPUB with images (falls back to the plain EPUB)."""
    root = root or media_root()
    log = Log(root)
    rows = list(csv.DictReader(io.StringIO(_get(GUTENBERG_CATALOG).decode("utf-8"))))
    ids = sorted(int(r["Text#"]) for r in rows if r.get("Type") == "Text" and r.get("Text#", "").isdigit())
    picked = sorted(random.Random(SEED).sample(ids, min(count, len(ids))))
    todo = [i for i in picked if not log.has("gutenberg", str(i))]
    print(f"gutenberg: {len(picked) - len(todo)} on disk, {len(todo)} to pull", flush=True)
    for i in todo:
        for url in (
            f"https://www.gutenberg.org/cache/epub/{i}/pg{i}-images.epub",
            f"https://www.gutenberg.org/cache/epub/{i}/pg{i}.epub",
        ):
            try:
                data = _get(url, timeout=300)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            log.save("gutenberg", str(i), url, "application/epub+zip", data, "epub")
            break
        time.sleep(1.5)  # Project Gutenberg asks automated clients to go slowly
    print("gutenberg: done", flush=True)


def fetch_librivox(root: Path | None = None, count: int = LIBRIVOX_ITEMS) -> None:
    """One MP3 (the smallest 64 kb/s chapter) from each of `count` LibriVox recordings on archive.org."""
    root = root or media_root()
    log = Log(root)
    query = urllib.parse.urlencode(
        {
            "q": "collection:librivoxaudio AND mediatype:audio",
            "fl[]": "identifier",
            "rows": str(count * 2),
            "output": "json",
            "sort[]": "downloads desc",
        }
    )
    ids = [d["identifier"] for d in _json(f"https://archive.org/advancedsearch.php?{query}")["response"]["docs"]]
    ids = sorted(random.Random(SEED).sample(ids, min(count, len(ids))))
    todo = [i for i in ids if not log.has("librivox", i)]

    def work(item: str) -> None:
        meta = _json(f"https://archive.org/metadata/{item}")
        files = [f for f in meta.get("files", []) if str(f.get("name", "")).lower().endswith(".mp3") and f.get("size")]
        files.sort(key=lambda f: int(f["size"]))
        if not files:
            return
        url = f"https://archive.org/download/{item}/{urllib.parse.quote(str(files[0]['name']))}"
        log.save("librivox", item, url, "audio/mpeg", _get(url, timeout=600), "mp3")

    print(f"librivox: {len(ids) - len(todo)} on disk, {len(todo)} to pull", flush=True)
    _parallel(todo, work, workers=3, label="librivox")


def fetch_nasa(root: Path | None = None, per_type: int = NASA_PER_TYPE) -> None:
    """NASA's image and video library: `per_type` audio and video assets (the smallest rendition of each)."""
    root = root or media_root()
    log = Log(root)
    for media_type, exts in (("audio", (".mp3", ".wav", ".m4a")), ("video", (".mp4", ".webm", ".mov"))):
        items: list[dict[str, Any]] = []
        page = 1
        while len(items) < per_type * 2 and page <= 20:
            data = _json(f"https://images-api.nasa.gov/search?media_type={media_type}&page={page}&page_size=100")
            batch = data.get("collection", {}).get("items", [])
            if not batch:
                break
            items.extend(batch)
            page += 1
            time.sleep(0.5)
        chosen = sorted(
            random.Random(SEED).sample(items, min(per_type, len(items))), key=lambda it: it["data"][0]["nasa_id"]
        )
        todo = [it for it in chosen if not log.has("nasa", str(it["data"][0]["nasa_id"]))]

        def work(item: dict[str, Any], exts: tuple[str, ...] = exts, media_type: str = media_type) -> None:
            nasa_id = str(item["data"][0]["nasa_id"])
            assets = _json(str(item["href"]))
            urls = [u for u in assets if str(u).lower().endswith(exts)]
            if not urls:
                return
            # The smallest rendition: "~small", "~mobile", "~orig" in NASA's naming, else the shortest name.
            urls.sort(key=lambda u: ("small" not in u and "mobile" not in u, len(u)))
            url = str(urls[0]).replace("http://", "https://")
            ext = url.rsplit(".", 1)[-1].lower()
            log.save("nasa", nasa_id, url, f"{media_type}/{ext}", _get(url, timeout=900), ext)

        print(f"nasa {media_type}: {len(chosen) - len(todo)} on disk, {len(todo)} to pull", flush=True)
        _parallel(todo, work, workers=3, label=f"nasa {media_type}")


def media(sample: int | None = None) -> list[Doc]:
    """Every pulled file; category = `<source>-<mime>`."""
    from tools.bench.corpora import _sample

    root = media_root()
    log = Log(root)
    docs = []
    for rec in log.records.values():
        path = root / str(rec["path"])
        if path.is_file():
            category = f"{rec['source']}-{str(rec['mime']).replace('/', '-')}"
            docs.append(
                Doc("media", f"{rec['source']}__{_SAFE.sub('_', str(rec['id']))[:100]}", path, category, dict(rec))
            )
    if not docs:
        raise FileNotFoundError(f"media: nothing pulled under {root}; run `python -m tools.bench fetch --only media`")
    docs.sort(key=lambda d: d.id)
    return _sample(docs, sample)


def fetch_media() -> None:
    """`fetch --only media`: every source in turn; `EZMD_MEDIA_SOURCES` narrows it (comma-separated)."""
    wanted = os.environ.get("EZMD_MEDIA_SOURCES", "commons,gutenberg,librivox,nasa").split(",")
    fetchers: dict[str, Callable[[], None]] = {
        "commons": fetch_commons,
        "gutenberg": fetch_gutenberg,
        "librivox": fetch_librivox,
        "nasa": fetch_nasa,
    }
    for name in wanted:
        name = name.strip()
        if name in fetchers:
            print(f"media: {name} ...", flush=True)
            fetchers[name]()
