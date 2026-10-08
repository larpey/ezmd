"""ezmd_api.blobs: blob storage for uploads, cached IR, rendered results, and attachments.

Keys are always `jobs/{job_id}/...` built from ids and fixed names, never from user filenames, so a
job purge is a prefix delete (docs/spec/part1.md section 8.4).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Protocol

from ezmd_api.settings import Settings

_KEY_RE = re.compile(r"^jobs/job_[0-9A-Za-z]{22}(/[A-Za-z0-9][A-Za-z0-9._-]{0,127}){0,8}/?$")


class BlobKeyError(ValueError):
    pass


def check_key(key: str) -> str:
    if not _KEY_RE.match(key) or ".." in key.split("/"):
        raise BlobKeyError("invalid blob key")
    return key


def job_prefix(job_id: str) -> str:
    return check_key(f"jobs/{job_id}/")


class BlobStore(Protocol):
    def put_bytes(self, key: str, data: bytes) -> None: ...
    def put_file(self, key: str, src: Path) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def download(self, key: str, dest: Path) -> None: ...
    def exists(self, key: str) -> bool: ...
    def delete_prefix(self, prefix: str) -> int: ...
    def list_prefix(self, prefix: str) -> list[str]: ...


class LocalBlobStore:
    """Filesystem store under `root`. Every resolved path is checked to stay inside `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        check_key(key)
        root = self.root.resolve()
        p = (root / key).resolve()
        if p != root and root not in p.parents:
            raise BlobKeyError("blob key escapes the store root")
        return p

    def put_bytes(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def put_file(self, key: str, src: Path) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, p)

    def get_bytes(self, key: str) -> bytes:
        p = self._path(key)
        try:
            return p.read_bytes()
        except FileNotFoundError as e:
            raise KeyError(key) from e

    def download(self, key: str, dest: Path) -> None:
        p = self._path(key)
        if not p.is_file():
            raise KeyError(key)
        shutil.copyfile(p, dest)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete_prefix(self, prefix: str) -> int:
        p = self._path(prefix)
        if not p.exists():
            return 0
        count = sum(1 for f in p.rglob("*") if f.is_file()) if p.is_dir() else 1
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
        return count

    def list_prefix(self, prefix: str) -> list[str]:
        p = self._path(prefix)
        if not p.is_dir():
            return []
        root = self.root.resolve()
        return sorted(f.relative_to(root).as_posix() for f in p.rglob("*") if f.is_file())


class S3BlobStore:
    """S3-compatible store (MinIO, R2, AWS). Requires the `[s3]` extra (boto3)."""

    def __init__(self, settings: Settings) -> None:
        try:
            import boto3  # type: ignore[import-not-found,unused-ignore]
        except ImportError as e:  # pragma: no cover - depends on the optional extra
            raise RuntimeError("EZMD_BLOB_BACKEND=s3 requires `pip install ezmd-api[s3]`") from e
        self.bucket = settings.s3_bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key.get_secret_value() if settings.s3_access_key else None,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None,
        )

    def put_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=check_key(key), Body=data)

    def put_file(self, key: str, src: Path) -> None:
        self.client.upload_file(str(src), self.bucket, check_key(key))

    def get_bytes(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=check_key(key))
        except self.client.exceptions.NoSuchKey as e:
            raise KeyError(key) from e
        return bytes(obj["Body"].read())

    def download(self, key: str, dest: Path) -> None:
        self.client.download_file(self.bucket, check_key(key), str(dest))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=check_key(key))
            return True
        except Exception:
            return False

    def list_prefix(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=check_key(prefix)):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_prefix(prefix)
        for i in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in keys[i : i + 1000]]
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch})
        return len(keys)


def build_blob_store(settings: Settings) -> BlobStore:
    if settings.blob_backend == "s3":
        return S3BlobStore(settings)
    return LocalBlobStore(settings.resolved_blob_root)
