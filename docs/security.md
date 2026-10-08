# Security

intomd treats every input as hostile. The public instance and self-hosted instances get the same
defaults; self-hosters may loosen limits through environment variables, never the sandbox. To report
a vulnerability, follow `SECURITY.md` in the repository root.

This page adapts [Part 1, section 8](spec/part1.md#8-security-baseline) of the specification for
operators and users. Items marked Planned are specified but not built yet.

## Sandboxed workers

- Conversions run in worker containers separate from the API: non-root (uid 10001), read-only root
  filesystem, a size-limited `/tmp` tmpfs, all capabilities dropped, `no-new-privileges`, and a
  seccomp profile (`deploy/seccomp-worker.json`) that also denies `ptrace`, `mount`, `keyctl`, `bpf`,
  and `userfaultfd`.
- `worker-default` and the API sit on an internal network with no route to the internet. Only
  `worker-fetch` (and Caddy) can reach the internet, and every fetch goes through the SSRF guard.
- Each conversion runs in a spawned child process with resource limits (address space
  `INTOMD_JOB_MEM_MB`, CPU time, process count, file size). A crashing or hanging engine kills only
  that child; the parent enforces the wall-clock timeout.
- External programs are started only through `intomd.core.sandbox.run` with a list argv, no shell,
  a minimal environment, no stdin, output caps, and a timeout. bubblewrap is used where it works;
  inside the hardened containers the container itself is the sandbox (D-0013).

## Input validation

- Types are detected from content (Magika, then libmagic), never from the extension. When the
  declared and detected types disagree, the detected type wins. Executables are rejected.
- Upload filenames are reduced to a sanitized basename and never used as paths on disk.
- Size caps apply at the edge (Caddy), while streaming the upload, and in the input reader.
  `Content-Length` is advisory; bytes are counted.
- Text: NUL bytes are stripped, invalid UTF-8 is replaced, and bidi overrides, zero-width and other
  non-printing format characters, and Unicode tag characters are removed and counted in the
  `removed_hidden_elements` warning.
- Planned with their converter families (Phase 1 onward): archive limits (total size, entry count,
  nesting depth, compression ratio), PDF sanitizing (JavaScript, launch actions, embedded files),
  Office macro and external-relationship removal, SVG and XML hardening, the image pixel cap, and
  media probing before transcription.

## SSRF protection

`intomd.core.netguard` guards every URL fetch:

1. Only `http` and `https`; URLs with userinfo are rejected.
2. IP literals and resolved addresses in private, loopback, link-local, multicast, reserved, CGNAT
   (`100.64.0.0/10`), and IPv6 ULA ranges are rejected, as are `localhost`, `*.localhost`,
   `*.internal`, `*.local`, `*.arpa`, and cloud metadata hostnames.
3. DNS is resolved once and the connection is pinned to the checked address (no rebinding).
4. At most 5 redirects, each re-checked; credentials are dropped across hosts.
5. Response bodies are capped and time-limited; executable content types are rejected.
6. A `platforms.toml` (`INTOMD_PLATFORMS_FILE`) can mark hosts `disabled` or `residential_only`.

`INTOMD_ALLOW_PRIVATE_NETWORKS=true` lifts the private-range block. Leave it off unless the instance
is on a trusted network.

## Application hardening

- No shell interpolation of user data; `subprocess` is imported only in the sandbox module, and a
  test enforces it.
- Secrets come only from the environment. In public mode the API refuses to start when
  `INTOMD_JWT_SECRET` or `INTOMD_KEY_PEPPER` is shorter than 32 bytes.
- Security headers on every response: a strict Content-Security-Policy, `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, plus HSTS at Caddy.
- CORS is same-origin unless `INTOMD_CORS_ORIGINS` lists origins.
- Per-client rate limits and a global active-job cap (`queue_unavailable` with `Retry-After`).
- Prompt-injection flagging: results are scanned, `injection_risk` is set, and the `agent` profile
  wraps the body in an `<untrusted_content>` fence. Flagged text is never removed.
- Logs are redacted (API keys, `Authorization`, Turnstile and claim tokens, URL userinfo) and never
  contain document content. Client IPs are stored only as salted hashes.
- Retention: jobs and blobs are purged after `INTOMD_RETENTION_HOURS` (default 24);
  `DELETE /v1/jobs/{id}` purges immediately.
- Dependency audit (`pip-audit`, `pnpm audit`) and the license check run in CI.
- Planned: MCP server auth defaults (Phase 1); extension data minimization (Phase 3).

## Threat model

| Threat | Asset | Attack vector | Controls | Residual risk |
|---|---|---|---|---|
| Malicious document executes code in the worker | Worker host, other jobs | PDF JavaScript, Office macros, OLE, engine parser bugs | Sanitize before parse (Planned per family); sandboxed child process; read-only filesystem; seccomp; no egress; non-root | An engine zero-day escaping the container; limited by dropped capabilities and resource limits, not eliminated |
| Decompression bomb | Worker memory and disk | Nested zip, PDF stream bomb, PNG bomb | Ratio and size caps (Planned with archives); address-space limit; tmpfs size; pixel cap (Planned) | Allocation inside an engine before the caps engage |
| Denial of service through slow or huge inputs | Instance availability | Long audio, huge PDFs, slow uploads, held SSE connections | Byte, page, and duration caps; per-IP and global concurrency caps; streaming upload limits; SSE keepalive and connection caps | Distributed abuse beyond the challenge; tighten caps |
| SSRF to internal services or cloud metadata | Host, Redis, private network | URL input, redirects, DNS rebinding | netguard with resolve-once pinning, scheme allowlist, private and CGNAT range block, re-checked redirects; converters run without network | A new private range or IPv6 transition trick; the block list is tested |
| Forged fetch node | Job content, residential egress | Stolen secret, spoofed claim | Shared secret plus source CIDR check; per-job claim tokens; upload bound to the claim | A leaked secret on the node; rotate it |
| Job result disclosure | User documents | Job id guessing, log leakage, shared cache | 128-bit job ids; no enumeration; key-bound access for keyed jobs; no cross-client dedup in public mode; content never logged; retention purge | Users sharing result links |
| Prompt injection through converted content | Downstream agents | Hidden text, HTML comments, bidi tricks, instructions in documents | Hidden character removal with counts; injection scanner; fence in the `agent` profile; text never altered | The scanner misses novel patterns; risk level is advisory |
| Supply chain | Everything | Compromised dependency, model weights, base image | Lockfiles; `pip-audit` and `pnpm audit`; license allowlist as inventory; pinned weights and base images (Planned with media) | Upstream compromise within a pinned version |
| Abuse of the public instance | Operator liability | Fetching platform-blocked or infringing content | Platform policy file; text out only; 24 h retention | Complaints still arrive; services can be disabled |
| Credential leakage in logs or errors | API keys, secrets | Exceptions with headers, URL userinfo | Redaction filter; error schema without internals; userinfo rejected | Third-party libraries logging raw requests |
| Path traversal | Worker filesystem, blob store | Upload filenames, archive members, attachment paths | Basename only; paths built from job ids; attachment path validation | None known |
| Unsafe deserialization | Worker | Tampered queue payloads in Redis | Queue payload is only the job id; Redis internal with `requirepass`; IR is JSON, never pickle | Redis compromise equals full compromise; keep it internal |
