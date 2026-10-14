"""Find Docling's layout and TableFormer models without importing Docling or torch.

ezmd runs Docling offline (`HF_HUB_OFFLINE=1`), so the models must already be on disk: either in the
directory named by `EZMD_DOCLING_ARTIFACTS` (what `docling-tools models download -o DIR` writes: one folder
per Hugging Face repo, `docling-project--docling-layout-heron` and `docling-project--docling-models`), or in
the Hugging Face hub cache (`models--docling-project--...`), which Docling uses when no artifacts path is
set. Importing Docling pulls in torch, which takes seconds, so this check runs first: the Docling engine
fails fast when it fails, the text-layer fallback says why, and `ezmd doctor` reports it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ARTIFACTS_ENV = "EZMD_DOCLING_ARTIFACTS"
DOWNLOAD_HINT = (
    "docling-tools models download layout tableformer -o ~/.cache/ezmd/docling, "
    "then set EZMD_DOCLING_ARTIFACTS to that directory"
)
_MODELS = (("layout", "docling-project--docling-layout-*"), ("tableformer", "docling-project--docling-models"))
"""(label, folder pattern) per model Docling's PDF pipeline loads; the layout repo name varies by version."""


@dataclass(frozen=True, slots=True)
class ModelsStatus:
    location: str
    """Where the models were looked for, for messages."""
    missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing


def _hub_cache(env: Mapping[str, str]) -> Path:
    """The Hugging Face hub cache, resolved the way huggingface_hub does it."""
    for key in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if env.get(key):
            return Path(env[key]).expanduser()
    if env.get("HF_HOME"):
        return Path(env["HF_HOME"]).expanduser() / "hub"
    base = Path(env["XDG_CACHE_HOME"]).expanduser() if env.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return base / "huggingface" / "hub"


def _has_files(folder: Path) -> bool:
    try:
        return any(p.is_file() for p in folder.rglob("*"))
    except OSError:
        return False


def _found(root: Path, pattern: str) -> bool:
    try:
        return any(_has_files(p) for p in root.glob(pattern) if p.is_dir())
    except OSError:
        return False


def models_status(env: Mapping[str, str] | None = None) -> ModelsStatus:
    """Which Docling models are missing from the place Docling will look for them offline."""
    env = os.environ if env is None else env
    artifacts = env.get(ARTIFACTS_ENV)
    if artifacts:
        root = Path(artifacts).expanduser()
        missing = tuple(label for label, pattern in _MODELS if not _found(root, pattern))
        return ModelsStatus(f"{ARTIFACTS_ENV}={root}", missing)
    hub = _hub_cache(env)
    missing = tuple(label for label, pattern in _MODELS if not _found(hub, f"models--{pattern}/snapshots"))
    return ModelsStatus(f"the Hugging Face cache ({hub}; {ARTIFACTS_ENV} is not set)", missing)


def missing_message(status: ModelsStatus) -> str:
    return f"Docling's {' and '.join(status.missing)} models are not downloaded (looked in {status.location})"
