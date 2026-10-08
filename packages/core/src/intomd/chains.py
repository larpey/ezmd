"""intomd.chains: default fallback chains per mime type (docs/spec/part1.md section 5.3).

Exact keys are matched before wildcard keys (`audio/*`). Part 2 fills this per family.
"""

from __future__ import annotations

DEFAULT_CHAINS: dict[str, list[str]] = {
    "text/plain": ["text.plain"],
    "text/markdown": ["text.markdown_passthrough", "text.plain"],
    # Filled by Part 2. Examples of the intended shape:
    # "application/pdf": ["documents.docling_pdf", "documents.pypdfium2_text", "images.ocr_pages"],
    # "text/html": ["web.trafilatura", "web.readability", "web.html_raw"],
    # "audio/*": ["media.asr_local", "media.asr_hosted"],
}
