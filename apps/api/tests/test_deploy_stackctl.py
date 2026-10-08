"""deploy/stackctl.py (the in-container half of backup.sh/restore.sh/upgrade.sh): round trip and hostile input."""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
import tarfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

STACKCTL = Path(__file__).resolve().parents[3] / "deploy" / "stackctl.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ezmd_stackctl_under_test", STACKCTL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Std:
    """Stand-in for sys.stdin/sys.stdout with a binary `.buffer`."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)


@pytest.fixture
def stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    data, blobs = tmp_path / "state", tmp_path / "blobs"
    data.mkdir()
    blobs.mkdir()
    for key in ("EZMD_DATABASE_URL", "EZMD_BLOB_BACKEND"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EZMD_DATA_DIR", str(data))
    monkeypatch.setenv("EZMD_BLOB_FS_ROOT", str(blobs))
    monkeypatch.setenv("EZMD_KEYS_FILE", str(data / "keys.json"))
    con = sqlite3.connect(data / "ezmd.db")
    con.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, state TEXT)")
    con.execute("INSERT INTO jobs VALUES ('job_1', 'done')")
    con.commit()
    con.close()
    (data / "keys.json").write_text('[{"key_hash": "x"}]', encoding="utf-8")
    (blobs / "jobs" / "job_1").mkdir(parents=True)
    (blobs / "jobs" / "job_1" / "result.md").write_bytes(b"# hello\n")
    return {"data": data, "blobs": blobs}


def _run(mod: ModuleType, monkeypatch: pytest.MonkeyPatch, argv: list[str], stdin: bytes = b"") -> tuple[int, bytes]:
    out = _Std()
    monkeypatch.setattr(sys, "stdin", _Std(stdin))
    monkeypatch.setattr(sys, "stdout", out)
    code = mod.main(["stackctl", *argv])
    return code, out.buffer.getvalue()


def _members(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        return {m.name: tar.extractfile(m).read() for m in tar if m.isfile()}  # type: ignore[union-attr]


def _pack(members: dict[str, bytes], manifest: dict[str, Any] | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if manifest is not None:
            raw = json.dumps(manifest).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return buf.getvalue()


def test_backup_wipe_restore_round_trip(stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    code, archive = _run(mod, monkeypatch, ["backup"])
    assert code == 0
    members = _members(archive)
    assert set(members) == {"db/ezmd.db", "keys/keys.json", "blobs/jobs/job_1/result.md", "manifest.json"}
    manifest = json.loads(members["manifest.json"])
    assert manifest["format"] == 1 and manifest["includes_blobs"] is True

    assert _run(mod, monkeypatch, ["verify"], archive)[0] == 0

    # Wipe everything, add a stray blob that the restore must remove.
    (stack["data"] / "ezmd.db").unlink()
    (stack["data"] / "keys.json").unlink()
    (stack["blobs"] / "jobs" / "job_1" / "result.md").unlink()
    (stack["blobs"] / "stray.bin").write_bytes(b"x")

    assert _run(mod, monkeypatch, ["restore"], archive)[0] == 0
    con = sqlite3.connect(stack["data"] / "ezmd.db")
    assert con.execute("SELECT state FROM jobs WHERE id = 'job_1'").fetchone() == ("done",)
    con.close()
    assert (stack["data"] / "keys.json").read_text(encoding="utf-8") == '[{"key_hash": "x"}]'
    assert (stack["blobs"] / "jobs" / "job_1" / "result.md").read_bytes() == b"# hello\n"
    assert not (stack["blobs"] / "stray.bin").exists()
    assert not (stack["blobs"] / mod.STAGING).exists()
    assert not (stack["data"] / mod.STAGING).exists()


def test_no_blobs_backup_leaves_blobs_alone(stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    _, archive = _run(mod, monkeypatch, ["backup", "--no-blobs"])
    assert not any(n.startswith("blobs/") for n in _members(archive))
    (stack["blobs"] / "new.bin").write_bytes(b"y")
    assert _run(mod, monkeypatch, ["restore"], archive)[0] == 0
    assert (stack["blobs"] / "new.bin").exists()


def test_tampered_backup_changes_nothing(stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    _, archive = _run(mod, monkeypatch, ["backup"])
    members = _members(archive)
    manifest = json.loads(members.pop("manifest.json"))
    members["keys/keys.json"] = b'[{"key_hash": "attacker"}]'
    bad = _pack(members, manifest)
    with pytest.raises(SystemExit) as exc:
        _run(mod, monkeypatch, ["restore"], bad)
    assert exc.value.code == 2
    assert (stack["data"] / "keys.json").read_text(encoding="utf-8") == '[{"key_hash": "x"}]'
    assert not (stack["data"] / mod.STAGING).exists()


@pytest.mark.parametrize("name", ["../escape.db", "/etc/passwd", "blobs/../../x", "other/file"])
def test_hostile_member_names_rejected(stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    mod = _load()
    bad = _pack({name: b"x"}, {"format": 1, "files": {}})
    with pytest.raises(SystemExit):
        _run(mod, monkeypatch, ["verify"], bad)


def test_missing_manifest_and_symlinks_rejected(stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    with pytest.raises(SystemExit):
        _run(mod, monkeypatch, ["verify"], _pack({"db/ezmd.db": b"x"}))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        link = tarfile.TarInfo("blobs/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    with pytest.raises(SystemExit):
        _run(mod, monkeypatch, ["verify"], buf.getvalue())


def test_migrate_fresh_database_reaches_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EZMD_DATABASE_URL", raising=False)
    monkeypatch.setenv("EZMD_DATA_DIR", str(tmp_path / "fresh"))
    mod = _load()
    assert _run(mod, monkeypatch, ["migrate"])[0] == 0
    con = sqlite3.connect(tmp_path / "fresh" / "ezmd.db")
    assert con.execute("SELECT version_num FROM alembic_version").fetchone() is not None
    con.close()


def test_migrate_adopts_create_all_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A database made by an older create_all start is stamped at head when its schema matches, not skipped."""
    from ezmd_api.db import Database

    monkeypatch.delenv("EZMD_DATABASE_URL", raising=False)
    monkeypatch.setenv("EZMD_DATA_DIR", str(tmp_path / "legacy"))
    db = Database(f"sqlite:///{(tmp_path / 'legacy' / 'ezmd.db').as_posix()}")
    db.create_all()
    db.engine.dispose()
    mod = _load()
    assert _run(mod, monkeypatch, ["migrate"])[0] == 0
    assert "stamped" in capsys.readouterr().err
    con = sqlite3.connect(tmp_path / "legacy" / "ezmd.db")
    assert con.execute("SELECT version_num FROM alembic_version").fetchone() is not None
    con.close()


def test_migrate_refuses_drifted_schema(
    stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load()
    assert _run(mod, monkeypatch, ["migrate"])[0] == 1
    assert "does not match" in capsys.readouterr().err


def test_has_keys_and_usage(stack: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    assert _run(mod, monkeypatch, ["has-keys"])[0] == 0
    (stack["data"] / "keys.json").unlink()
    assert _run(mod, monkeypatch, ["has-keys"])[0] == 1
    assert _run(mod, monkeypatch, ["nope"])[0] == 64
