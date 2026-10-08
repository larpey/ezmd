---
title: "tidepool"
source: "input.repo.zip"
source_type: code
converter: code.repo_pack
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 231
tokens: {o200k_base: 939, cl100k_base: 949, claude_approx: 1014}
content_hash: "sha256:6ec9d5c22869e38a380aa368dc54d0cabe04bc381c33affe08bd3d02739dc28c"
source_hash: "sha256:8075688268aea0a68c0c589350df666990f1bfb15818253cb68883185d06de81"
truncated: false
warnings: [secret_file_excluded, secret_redacted]
injection_risk: none
extra:
  bytes: 1141
  excluded.gitignored: 2
  excluded.secret_file: 2
  files: 8
  languages: "javascript, python, dockerfile"
  packed_bytes: 1142
  repo: tidepool
  tokens: 318
---
> Sections: 1 Directory tree, 2 Files.

## Contents

- [1 Directory tree](#sec-1)
- [2 Files](#sec-2)
    - [2.1 README.md](#sec-2-1)
    - [2.2 .gitignore](#sec-2-2)
    - [2.3 Dockerfile](#sec-2-3)
    - [2.4 config/alerts.ini](#sec-2-4)
    - [2.5 config/app.yaml](#sec-2-5)
    - [2.6 web/client.js](#sec-2-6)
    - [2.7 src/tidepool/\_\_main\_\_.py](#sec-2-7)
    - [2.8 docs/operations.md](#sec-2-8)

# tidepool {#doc}

8 files packed (1,141 source bytes, 318 tokens). Languages: javascript 47%, python 29%, dockerfile 24%. Not packed: 2 ignored by .gitignore/.intomdignore; 2 credential files.

## 1 Directory tree {#sec-1}

```text
tidepool/
├── config/
│   ├── alerts.ini
│   └── app.yaml
├── deploy/
│   └── id_ed25519 (excluded: secret file)
├── docs/
│   └── operations.md
├── src/
│   └── tidepool/
│       └── __main__.py
├── web/
│   └── client.js
├── .gitignore
├── .npmrc (excluded: secret file)
├── Dockerfile
└── README.md
```

## 2 Files {#sec-2}

### 2.1 README.md {#sec-2-1}

File: `README.md`

```markdown
# tidepool

Sensor ingest service (intomd secret-scatter fixture).
```

### 2.2 .gitignore {#sec-2-2}

File: `.gitignore`

```gitignore
*.pyc
secrets/
!secrets/README.md
```

### 2.3 Dockerfile {#sec-2-3}

File: `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV INGEST_TOKEN=[REDACTED:generic_secret]
ENV LOG_LEVEL=info
CMD ["python", "-m", "tidepool"]
```

### 2.4 config/alerts.ini {#sec-2-4}

File: `config/alerts.ini`

```ini
[alerts]
smtp_host = mail.example.invalid
smtp_password = <your password here>
webhook_secret = [REDACTED:generic_secret]
```

### 2.5 config/app.yaml {#sec-2-5}

File: `config/app.yaml`

```yaml
service: tidepool
database:
  host: db.example.invalid
  password: [REDACTED:generic_secret]
  pool_size: 8
upstream:
  api_key: "${UPSTREAM_API_KEY}"
```

### 2.6 web/client.js {#sec-2-6}

File: `web/client.js`

```javascript
// client.js: upstream HTTP client.
export async function fetchReadings(base) {
  const res = await fetch(base + '/readings', {
    headers: { Authorization: 'Bearer [REDACTED:authorization_header]' },
  });
  return res.json();
}
export const MAX_RETRIES = 3;
```

### 2.7 src/tidepool/\_\_main\_\_.py {#sec-2-7}

File: `src/tidepool/__main__.py`

```python
"""tidepool entry point."""
import os

TOKEN = os.environ["INGEST_TOKEN"]  # read at runtime, nothing to redact


def main() -> None:
    print("ingest ready")
```

### 2.8 docs/operations.md {#sec-2-8}

File: `docs/operations.md`

````markdown
# Operations

Connect to the staging replica:

```
psql postgres://ingest:[REDACTED:basic_auth_url]@db.staging.example.invalid/tide
```

Local default (placeholder, keep visible): `postgres://ingest:changeme@localhost/tide`.
````
