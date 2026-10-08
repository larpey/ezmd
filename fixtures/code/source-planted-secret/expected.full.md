---
title: "input.py"
source: "input.py"
source_type: code
converter: code.source_file
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 40
tokens: {o200k_base: 154, cl100k_base: 152, claude_approx: 166}
content_hash: "sha256:4f9a05980bd56b25df1e8890821e9b9070a4e2114e22c553c987fd781e370701"
source_hash: "sha256:e349ab440f07388ce956ecb4d8f648ba71357a6042730b022275c07d05493b53"
truncated: false
warnings: [secret_redacted]
injection_risk: none
extra: {bytes: 800, encoding: utf-8, language: python, lines: 22, tokens: 134}
---
# input.py {#doc}

File: `input.py`

```python
# settings.py: application settings with planted fake secrets (ezmd fixture).
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
