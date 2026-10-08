---
title: "input.py"
source: "input.py"
source_type: code
converter: code.source_file
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 40
tokens: {o200k_base: 155, cl100k_base: 153, claude_approx: 167}
content_hash: "sha256:72d3e2b6a2037eb58ca39cb6cfbcaf493d823007b577caa93c4e24548c12dc36"
source_hash: "sha256:3845209bd860f02ab74a7d4e320464c86ddee7f422f253e56bbc453977e51616"
truncated: false
warnings: [secret_redacted]
injection_risk: none
extra: {bytes: 814, encoding: utf-8, language: python, lines: 22, tokens: 135}
---
# input.py {#doc}

File: `input.py`

```python
# settings.py: application settings with planted fake secrets (intomd fixture).
import os

DEBUG = os.environ.get("APP_DEBUG", "0") == "1"
API_SECRET_KEY = "[REDACTED:generic_secret]"
SERVICE_TOKEN = [REDACTED:generic_secret]
DATABASE_PASSWORD = "changeme"  # placeholder, must stay visible
MAX_TOKENS = 4096

SIGNING_KEY_PEM = '''
[REDACTED:private_key]






'''


def database_url(host: str) -> str:
    return f"postgresql://app:[REDACTED:basic_auth_url]@{host}/app"
```
