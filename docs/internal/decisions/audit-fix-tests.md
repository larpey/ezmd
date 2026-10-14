# Audit fix: golden harness hard invariants and sidecar comparison (fix-tests)

Decision: a golden fixture now passes only when its similarity score reaches the threshold AND it has no hard
failure. The new hard failures, all in `ezmd.testing`:

- `invariants.check`: exact agreement with the golden on math expressions, block counts (headings, paragraphs,
  tables, code, blockquotes, list items), the list nesting profile, per-table cell spans, link targets, image
  sources, the frontmatter `warnings` set, `injection_risk` and `truncated`, and the multiset of numeric tokens.
- `exact_numbers` is on by default for every family (`[invariants]` in `fixtures/thresholds.toml`); a family
  `thresholds.toml` may override it and a `meta.toml` may turn it off only with `exact_numbers_reason`.
- `must_contain` / `must_not_contain` lists in `meta.toml`, populated for the eight fixtures that carry hidden
  text, injection payloads, invisible characters or planted secrets (secrets are stored as 16-character prefixes).
- `expected.sidecar.json` is compared exactly after `normalize_sidecar` (drops `metrics.duration_seconds` and
  `metrics.fetch_seconds`, replaces `frontmatter.converter_version` and `ezmd_version` with `<normalized>`).
  `write_golden` writes the normalized form. Exact rather than a structural subset because every sidecar field
  other than those four is deterministic across runs here, and the sidecar is a public output.
- The text sub-score now includes list item paragraphs, which it skipped before.

Why: the audit showed the score alone passed a leaked hidden paragraph (0.975), a downgraded `injection_risk`
(1.0), a dropped rowspan (1.0), a changed table total (0.975 / 0.996), a removed link (0.983) and others.
Similarity is kept for prose drift; the invariants catch what a similarity score cannot see.

Alternatives rejected: raising thresholds to 1.0 (brittle for prose, still blind to frontmatter and spans);
comparing only block types of the sidecar (would miss warnings detail, provenance paths and table metadata).

Risk: the goldens were generated on Windows. If a platform produces different numbers or sidecar fields, CI
will now fail where it used to pass at 0.95+; the fix is to find the platform difference, not to loosen.
