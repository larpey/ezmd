# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.x (main) | yes |

## Reporting a vulnerability

Please report vulnerabilities privately to **security@intomd.dev** (placeholder until the domain is set
up; until then use GitHub's private vulnerability reporting on this repository). Do not open a public issue.
We aim to acknowledge within 3 days and to ship a fix or mitigation for high-severity issues within 14 days.

The threat model and the controls in place (sandboxed workers, SSRF guard, upload limits, log redaction,
24-hour retention) are documented in `docs/security.md` and docs/spec/part1.md section 8.
