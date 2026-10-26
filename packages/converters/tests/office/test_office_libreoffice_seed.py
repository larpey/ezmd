"""LibreOffice's profile is initialised once per process and copied for every later conversion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ezmd.core import sandbox
from ezmd.inputs import InputRef
from ezmd_converters.office import libreoffice


def _fake_soffice(calls: list[dict[str, object]]):  # type: ignore[no-untyped-def]
    """Stands in for `sandbox.run`: initialises the profile the way soffice does, writes the output."""

    def run(argv: list[str], **kw: object) -> SimpleNamespace:
        profile = Path(argv[[a.startswith("-env:UserInstallation=") for a in argv].index(True)].split("=", 1)[1][8:])
        if profile.as_posix().startswith("/") and not profile.exists():  # file:///C:/... on Windows
            profile = Path(profile.as_posix().lstrip("/"))
        marker = profile / "user" / "initialised.txt"
        calls.append({"seeded": marker.exists(), "profile": profile})
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("init")
        outdir = Path(argv[argv.index("--outdir") + 1])
        (outdir / f"input.{argv[argv.index('--convert-to') + 1]}").write_bytes(b"PK")
        return SimpleNamespace(returncode=0)

    return run


def test_second_conversion_reuses_the_initialised_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(libreoffice, "_seed", None)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sandbox, "run", _fake_soffice(calls))
    ref = InputRef.from_bytes(b"\xd0\xcf\x11\xe0legacy", filename="old.doc")
    soffice = str(tmp_path / "soffice.exe")
    assert libreoffice._run(soffice, ref, "docx", 10) == b"PK"
    assert libreoffice._run(soffice, ref, "docx", 10) == b"PK"
    assert [c["seeded"] for c in calls] == [False, True]
    seed = libreoffice._seed
    assert seed is not None and seed[0] == soffice and (seed[1] / "user" / "initialised.txt").is_file()
    assert (seed[1] / "user" / "registrymodifications.xcu").read_text(encoding="utf-8") == libreoffice._XCU
    # The per-file profile was a copy: the seed is untouched by the second run's temp directory removal.
    assert calls[0]["profile"] != calls[1]["profile"]


def test_a_failed_first_conversion_keeps_no_seed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(libreoffice, "_seed", None)
    monkeypatch.setattr(sandbox, "run", lambda argv, **kw: SimpleNamespace(returncode=1))
    ref = InputRef.from_bytes(b"\xd0\xcf\x11\xe0legacy", filename="old.doc")
    with pytest.raises(libreoffice.ConversionError, match="wrote no docx"):
        libreoffice._run(str(tmp_path / "soffice.exe"), ref, "docx", 10)
    assert libreoffice._seed is None
