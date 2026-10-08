# Security policy

ezmd converts untrusted files and URLs, so security reports are welcome and taken seriously.

## Supported versions

ezmd has not had a release yet. Until it does, only `main` is supported. After the first release, the
latest minor version receives security fixes.

| Version | Supported |
|---|---|
| `main` (pre-release, 0.0.x) | yes |
| latest minor, once released | yes |
| older minors | no |

## Reporting a vulnerability

Report privately; do not open a public issue, discussion, or pull request.

- Preferred: a private security advisory on the GitHub repository (Security, Report a vulnerability).
- Email: security@ezmd.dev. This address is a placeholder until the project domain is set up; until
  then use the private advisory. A PGP key will be published here with the address.

Include the affected version or commit, the component (converter, API, worker, MCP server, web UI,
deploy configuration), a minimal reproduction or input file, and the impact you observed.

Response targets:

- acknowledgement within 3 days;
- a fix or a mitigation plan within 14 days for high and critical issues, and within 30 days for others;
- a coordinated disclosure date agreed with you, and credit in the advisory if you want it.

## Scope

In scope:

- the software in this repository: converters and their input handling (archive bombs, XML entities, PDF
  and Office payloads, path traversal), the sandbox around external programs, the SSRF guard and fetch
  client, the REST API and job store, the MCP server, the web UI, the TypeScript SDK, and the deploy
  configuration (`deploy/`);
- the public instance, once it exists, including bypasses of its abuse limits (rate limits, size and
  duration caps, challenge checks).

Out of scope:

- volumetric or load testing against the public instance, and denial of service by sheer traffic;
- social engineering, and physical attacks;
- findings in third-party engines that ezmd already isolates as documented in `docs/security.md`, unless
  ezmd's handling makes them exploitable (report those upstream, and tell us if ezmd should mitigate);
- optional `nonfree` engines' own license or security posture beyond how ezmd invokes them.

## Safe harbor

Research done in good faith under this policy is authorized: we will not pursue legal action or ask
anyone else to, for accessing only what is needed to demonstrate an issue, avoiding privacy violations
and service disruption, not exfiltrating or keeping other people's data, and giving us reasonable time to
fix the issue before disclosure. If in doubt, ask first through a private advisory.

## Security exceptions

Known, accepted vulnerabilities in dependencies (no fix available yet) are listed with an expiry date and
a decision reference in `tools/audit_ignore.toml`; the audit jobs stop ignoring an entry once it expires. Image
scans fail on fixable high and critical findings; a `SECURITY-EXCEPTIONS.md` register for unfixed image
findings is planned.

## Further reading

The threat model and the controls in place (sandboxed workers, SSRF guard, input validation, upload
limits, log redaction, retention) are described in `docs/security.md` and in section 8 of
`docs/spec/part1.md`.
