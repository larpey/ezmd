"""Write docs/api/openapi.json from the app factory. Run: `uv run python apps/api/scripts/export_openapi.py`.

`apps/api/tests/test_openapi.py` fails when the committed file is stale.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ezmd_api.openapi import openapi_document

OUTPUT = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.json"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(openapi_document(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
