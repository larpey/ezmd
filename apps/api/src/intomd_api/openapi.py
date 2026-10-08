"""intomd_api.openapi: the committed OpenAPI document (docs/api/openapi.json).

Built from a fixed Settings so the output does not depend on the environment; the fetch-node routes
are included (they exist whenever INTOMD_FETCH_NODE_SECRET is set).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from intomd_api.settings import Settings


def schema_settings() -> Settings:
    return Settings(
        queue="inline",
        scheduler_enabled=False,
        data_dir=Path(tempfile.gettempdir()) / "intomd-openapi",
        fetch_node_secret="openapi-export-placeholder",  # noqa: S106 - placeholder
        public_url="https://intomd.example.com",
        web_dist=Path(tempfile.gettempdir()) / "intomd-openapi" / "no-web-dist",
    )


def openapi_document() -> str:
    from intomd_api.main import create_app

    app = create_app(schema_settings())
    try:
        return json.dumps(app.openapi(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    finally:
        app.state.services.close()
