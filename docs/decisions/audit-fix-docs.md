## D-XXXX: server.json lists no remote until the API mounts /mcp; doctor reads extras from metadata
Date: 2026-10-09
Task: audit (fix-docs)
Status: accepted
Context: docs/spec/part4.md 4.4.5 asks for a `remotes` entry for the public instance's `/mcp` URL in
`packages/mcp/server.json`. D-0024 left mounting `/mcp` on the API pending, so the entry pointed registry users
at a URL that 404s. Separately, `ezmd doctor` hardcoded extras from the spec (`media`, `ocr`, `web`, `fetch`,
`server`) that are not published and told users to `pip install` them, and never reported `data` or `7z`.
Decision:
- Remove `remotes` from server.json until apps/api mounts `/mcp`. `packages/mcp/tests/test_mcp_registry.py`
  ties the two together (remotes present if and only if the API source mounts `/mcp`), so whoever mounts it
  must restore the entry. This deviates from part4 4.4.5 until then.
- Doctor reads the published extras from the installed `ezmd` metadata (`Provides-Extra`, minus `all`) and
  decides "installed" by following each extra's requirements, including forwarded `ezmd-converters[...]`
  extras. Spec extras not yet published live in `ezmd.cli.doctor.PLANNED_EXTRAS` and are shown as "coming in a
  later release"; tests/test_extras_hints.py keeps PLANNED_EXTRAS within its PENDING list and disjoint from the
  declared extras.
- `--engine family=name` also matches the underscore-separated parts of a converter id (so `pdf=docling`
  finds `documents.docling_pdf`), and naming an Unavailable converter raises an error that names its extra.
Alternatives: keep the remote with a "coming soon" description (the registry has no such field, and clients
would still try the URL); keep a hardcoded extras list in doctor (it drifted once already).
