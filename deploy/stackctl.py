"""deploy/stackctl.py: data operations that backup.sh, restore.sh, upgrade.sh and bootstrap.sh run in the api image.

The scripts ship this file into a one-off `api` container (deploy/lib.sh `stackctl`), so it sees exactly the
volumes, environment and Python packages the API sees. It never runs on the host.

    stackctl backup [--no-blobs]  tar of a consistent SQLite snapshot, keys.json and blobs, to stdout
    stackctl verify               read such a tar from stdin, check every checksum, change nothing
    stackctl restore              read such a tar from stdin, verify it fully, then replace the data
    stackctl migrate              Alembic upgrade; adopts a matching create_all database, refuses drift
    stackctl has-keys             exit 0 when INTOMD_KEYS_FILE exists, 1 when it does not

Progress and errors go to stderr; stdout carries only tar data. Archive members are validated before
anything is written to the live paths (regular files and directories only, no absolute paths, no `..`).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath
from typing import IO, Any

FORMAT = 1
MANIFEST = "manifest.json"
DB_MEMBER = "db/intomd.db"
KEYS_MEMBER = "keys/keys.json"
BLOB_PREFIX = "blobs/"
STAGING = ".intomd-restore-staging"
CHUNK = 1 << 20


def say(message: str) -> None:
    print(f"stackctl: {message}", file=sys.stderr, flush=True)


def fail(message: str, code: int = 2) -> None:
    say(f"error: {message}")
    raise SystemExit(code)


class Paths:
    """Live data locations, resolved the way the API resolves them."""

    def __init__(self) -> None:
        from intomd_api.settings import Settings

        settings = Settings()
        url = settings.resolved_database_url
        if not url.startswith("sqlite:///"):
            fail("the database is not SQLite; back it up with that database's own tools (pg_dump)")
        self.db = Path(url.removeprefix("sqlite:///"))
        self.url = url
        self.keys: Path | None = settings.keys_file
        self.blobs: Path | None = settings.resolved_blob_root if settings.blob_backend == "fs" else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _alembic_revision(db: Path) -> str | None:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return str(row[0]) if row else None


def _app_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("intomd-api")
    except PackageNotFoundError:
        return "unknown"


def _snapshot_db(src: Path, dest: Path) -> None:
    """Consistent online copy through SQLite's backup API (safe while the API and workers write)."""
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
        ok = target.execute("PRAGMA integrity_check").fetchone()
        if not ok or ok[0] != "ok":
            fail(f"integrity_check on the snapshot failed: {ok}")
    finally:
        target.close()
        source.close()


def _iter_blob_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != STAGING and not (Path(dirpath) / d).is_symlink())
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_file() and not path.is_symlink():
                yield path


def _add_file(tar: tarfile.TarFile, name: str, path: Path, files: dict[str, dict[str, Any]]) -> None:
    info = tarfile.TarInfo(name)
    info.size = path.stat().st_size
    info.mtime = int(path.stat().st_mtime)
    info.mode = 0o600
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        reader = _HashingReader(fh, digest)
        tar.addfile(info, reader)
    files[name] = {"sha256": digest.hexdigest(), "size": info.size}


class _HashingReader(io.RawIOBase):
    def __init__(self, inner: IO[bytes], digest: Any) -> None:
        self.inner = inner
        self.digest = digest

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        data = self.inner.read(size)
        self.digest.update(data)
        return data


def cmd_backup(args: list[str]) -> int:
    include_blobs = "--no-blobs" not in args
    paths = Paths()
    files: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="intomd-backup-") as tmp:
        snapshot = Path(tmp) / "intomd.db"
        revision = None
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|", format=tarfile.PAX_FORMAT) as tar:
            if paths.db.is_file():
                _snapshot_db(paths.db, snapshot)
                revision = _alembic_revision(snapshot)
                _add_file(tar, DB_MEMBER, snapshot, files)
                say(f"database snapshot {snapshot.stat().st_size} bytes (alembic {revision or 'unmanaged'})")
            else:
                say(f"no database at {paths.db} yet; nothing to snapshot")
            if paths.keys is not None and paths.keys.is_file():
                _add_file(tar, KEYS_MEMBER, paths.keys, files)
                say("keys file included")
            blob_count = 0
            if include_blobs and paths.blobs is not None and paths.blobs.is_dir():
                for path in _iter_blob_files(paths.blobs):
                    rel = path.relative_to(paths.blobs).as_posix()
                    _add_file(tar, BLOB_PREFIX + rel, path, files)
                    blob_count += 1
                say(f"{blob_count} blob files included")
            manifest = {
                "format": FORMAT,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "app_version": _app_version(),
                "alembic_revision": revision,
                "includes_blobs": include_blobs and paths.blobs is not None,
                "files": files,
            }
            data = json.dumps(manifest, indent=2, sort_keys=True).encode()
            info = tarfile.TarInfo(MANIFEST)
            info.size = len(data)
            info.mtime = int(time.time())
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    return 0


def _safe_member_name(name: str) -> str:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts or "\\" in name:
        fail(f"unsafe path in backup: {name!r}")
    clean = pure.as_posix()
    if clean != MANIFEST and clean not in (DB_MEMBER, KEYS_MEMBER) and not clean.startswith(BLOB_PREFIX):
        fail(f"unexpected member in backup: {name!r}")
    return clean


Sink = Callable[[str], Path | None]


def _read_archive(stream: IO[bytes], sink: Sink) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Read every member, hashing it and writing it where `sink` says (None = discard)."""
    seen: dict[str, dict[str, Any]] = {}
    manifest: dict[str, Any] | None = None
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            if member.isdir():
                continue
            if not member.isfile():
                fail(f"backup member {member.name!r} is not a regular file")
            name = _safe_member_name(member.name)
            fh = tar.extractfile(member)
            assert fh is not None
            if name == MANIFEST:
                manifest = json.loads(fh.read(1 << 24))
                continue
            if name in seen:
                fail(f"duplicate member in backup: {name}")
            digest = hashlib.sha256()
            size = 0
            dest = sink(name)
            out = None
            if dest is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                out = dest.open("wb")
            try:
                while chunk := fh.read(CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    if out is not None:
                        out.write(chunk)
            finally:
                if out is not None:
                    out.close()
            seen[name] = {"sha256": digest.hexdigest(), "size": size}
    if manifest is None:
        fail("backup has no manifest.json")
    assert manifest is not None
    if manifest.get("format") != FORMAT:
        fail(f"unsupported backup format {manifest.get('format')!r}")
    expected = manifest.get("files") or {}
    if set(expected) != set(seen):
        missing = sorted(set(expected) - set(seen))[:5]
        extra = sorted(set(seen) - set(expected))[:5]
        fail(f"backup contents do not match its manifest (missing {missing}, unlisted {extra})")
    for name, meta in expected.items():
        if meta != seen[name]:
            fail(f"checksum mismatch for {name}")
    return manifest, seen


def cmd_verify(_args: list[str]) -> int:
    manifest, seen = _read_archive(sys.stdin.buffer, lambda _name: None)
    say(f"backup OK: {len(seen)} files, created {manifest.get('created_at')}, app {manifest.get('app_version')}")
    return 0


def _clear_dir(root: Path, keep: str) -> None:
    for child in root.iterdir():
        if child.name == keep:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def cmd_restore(_args: list[str]) -> int:
    paths = Paths()
    db_stage = paths.db.parent / STAGING
    blob_stage = paths.blobs / STAGING if paths.blobs is not None else None
    for stage in (db_stage, blob_stage):
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True)

    def sink(name: str) -> Path | None:
        if name.startswith(BLOB_PREFIX):
            if blob_stage is None:
                return None
            return blob_stage / name.removeprefix(BLOB_PREFIX)
        return db_stage / name

    try:
        manifest, seen = _read_archive(sys.stdin.buffer, sink)
    except BaseException:
        for stage in (db_stage, blob_stage):
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
        raise
    say(f"backup verified: {len(seen)} files from {manifest.get('created_at')}")

    if DB_MEMBER in seen:
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(paths.db) + suffix).unlink(missing_ok=True)
        os.replace(db_stage / DB_MEMBER, paths.db)
        say(f"database restored to {paths.db}")
    if KEYS_MEMBER in seen:
        if paths.keys is None:
            say("warning: backup has a keys file but INTOMD_KEYS_FILE is not set; left it out")
        else:
            paths.keys.parent.mkdir(parents=True, exist_ok=True)
            os.replace(db_stage / KEYS_MEMBER, paths.keys)
            os.chmod(paths.keys, 0o600)
            say(f"keys file restored to {paths.keys}")
    shutil.rmtree(db_stage, ignore_errors=True)

    if blob_stage is not None and paths.blobs is not None:
        if manifest.get("includes_blobs"):
            _clear_dir(paths.blobs, keep=STAGING)
            for child in blob_stage.iterdir():
                os.replace(child, paths.blobs / child.name)
            count = sum(1 for name in seen if name.startswith(BLOB_PREFIX))
            say(f"{count} blob files restored to {paths.blobs}")
        else:
            say("backup has no blobs; existing blobs left as they are")
        shutil.rmtree(blob_stage, ignore_errors=True)
    return 0


def cmd_migrate(_args: list[str]) -> int:
    from intomd_api.migrate import SchemaDrift, ensure_schema

    paths = Paths()
    paths.db.parent.mkdir(parents=True, exist_ok=True)
    try:
        action = ensure_schema(paths.url)
    except SchemaDrift as exc:
        say(f"error: {exc}")
        return 1
    say(f"database {action}; at Alembic head ({_alembic_revision(paths.db)})")
    return 0


def cmd_has_keys(_args: list[str]) -> int:
    paths = Paths()
    return 0 if paths.keys is not None and paths.keys.is_file() else 1


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "backup": cmd_backup,
    "verify": cmd_verify,
    "restore": cmd_restore,
    "migrate": cmd_migrate,
    "has-keys": cmd_has_keys,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in COMMANDS:
        say(f"usage: stackctl {{{','.join(COMMANDS)}}} [args]")
        return 64
    return COMMANDS[argv[1]](argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
