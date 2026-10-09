"""ezmd.warnings.codes: the canonical warning code registry.

Every warning code ezmd can emit is a member of :class:`WarningKind`, and every member has exactly one
:class:`CodeSpec` in :data:`CODES` giving its default severity, family, a one-line description of what happened,
and a one-line suggested action for the user. Codes are stable lowercase snake_case strings. Adding a code means
adding it here and regenerating ``docs/warnings.md``. Retired duplicate spellings live in :data:`ALIASES` and
normalize through :func:`normalize_code` (D-0017).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal

Severity = Literal["info", "warning", "error"]


class WarningKind(StrEnum):
    """Every warning code, grouped by family."""

    # Core and detection
    MISNAMED_FILE = "misnamed_file"
    CONTENT_TYPE_MISMATCH = "content_type_mismatch"
    ENCODING_UNCERTAIN = "encoding_uncertain"
    MULTILINGUAL_CONTENT = "multilingual_content"
    ENGINE_FALLBACK = "engine_fallback"
    ENGINE_FAILED = "engine_failed"
    CONVERTER_FAILED = "converter_failed"
    EXTRACTION_EMPTY = "extraction_empty"
    SIZE_CAP = "size_cap"
    PAGE_CAP_REACHED = "page_cap_reached"
    PAGE_TIMEOUT = "page_timeout"
    ROW_CAP_REACHED = "row_cap_reached"
    TIMEOUT_PARTIAL = "timeout_partial"
    TIMEOUT_HARD = "timeout_hard"
    EXTRA_REQUIRED = "extra_required"
    EXPERIMENTAL_CONVERTER = "experimental_converter"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    INJECTION_SUSPECTED = "injection_suspected"
    REMOVED_HIDDEN_ELEMENTS = "removed_hidden_elements"
    REMOVED_SCRIPT_OR_MACRO = "removed_script_or_macro"
    PII_COLUMNS_REMOVED = "pii_columns_removed"
    IMAGE_SKIPPED = "image_skipped"
    IMAGE_TOO_LARGE = "image_too_large"
    NESTING_FLATTENED = "nesting_flattened"
    OTHER = "other"

    # PDF
    ENCRYPTED_NO_PASSWORD = "encrypted_no_password"
    COPY_RESTRICTED_IGNORED = "copy_restricted_ignored"
    PAGES_WITHOUT_TEXT = "pages_without_text"
    OCR_UNAVAILABLE = "ocr_unavailable"
    OCR_CONFIDENCE_LOW = "ocr_confidence_low"
    READING_ORDER_UNCERTAIN = "reading_order_uncertain"
    HEADING_SOURCE_STRUCTURE_TREE = "heading_source_structure_tree"
    STRUCTURE_TREE_UNUSABLE = "structure_tree_unusable"
    REMOVED_RUNNING_HEADER_FOOTER = "removed_running_header_footer"
    TABLE_REJOINED = "table_rejoined"
    EQUATION_UNRECOGNIZED = "equation_unrecognized"
    XFA_PARTIAL = "xfa_partial"
    IWORK_PREVIEW_FALLBACK = "iwork_preview_fallback"

    # Office
    HEADING_INFERRED_FROM_FORMATTING = "heading_inferred_from_formatting"
    TEXTBOX_CONTENT_RELOCATED = "textbox_content_relocated"
    HIDDEN_SLIDES_INCLUDED = "hidden_slides_included"
    HIDDEN_SHEETS_INCLUDED = "hidden_sheets_included"
    FORMULA_UNCALCULATED = "formula_uncalculated"
    FORMULAS_PRESENT = "formulas_present"
    CELL_ERRORS = "cell_errors"
    POSSIBLE_SERIAL_DATES = "possible_serial_dates"
    RAGGED_ROWS = "ragged_rows"
    SMARTART_FLATTENED = "smartart_flattened"
    OLE_OBJECT_SKIPPED = "ole_object_skipped"
    LEGACY_TEXT_ONLY = "legacy_text_only"
    LIBREOFFICE_MISSING = "libreoffice_missing"
    PAGES_ESTIMATED = "pages_estimated"
    EQUATION_PARTIAL = "equation_partial"
    TRACKED_CHANGES_PRESENT = "tracked_changes_present"
    COMMENTS_PRESENT = "comments_present"
    SLIDE_CAP_REACHED = "slide_cap_reached"

    # Google
    PRIVATE_LINK = "private_link"
    FIRST_SHEET_ONLY = "first_sheet_only"
    SUGGESTIONS_NOT_EXPORTED = "suggestions_not_exported"

    # Ebooks and text
    EPUB_MIMETYPE_MISSING = "epub_mimetype_missing"
    CALIBRE_MISSING = "calibre_missing"
    DRM_PROTECTED = "drm_protected"
    LATEX_MAIN_AMBIGUOUS = "latex_main_ambiguous"
    LATEX_UNKNOWN_MACRO = "latex_unknown_macro"
    NOTEBOOK_INVALID = "notebook_invalid"
    MDX_COMPONENTS_STRIPPED = "mdx_components_stripped"
    TABLE_INFERRED = "table_inferred"
    EMPTY_BODY_JS_REQUIRED = "empty_body_js_required"
    MARKUP_PARTIAL = "markup_partial"

    # Web
    ROBOTS_DISALLOWED = "robots_disallowed"
    HTTP_ERROR = "http_error"
    PAYWALL_DETECTED = "paywall_detected"
    READABILITY_FALLBACK_FULL_BODY = "readability_fallback_full_body"
    MULTIPAGE_ARTICLE = "multipage_article"
    LAZY_CONTENT_POSSIBLE = "lazy_content_possible"
    IMAGES_WITHOUT_ALT = "images_without_alt"
    FETCH_BLOCKED = "fetch_blocked"
    FETCH_FAILED = "fetch_failed"

    # Sites
    LLMS_TXT_USED = "llms_txt_used"
    LLMS_TXT_MAY_BE_STALE = "llms_txt_may_be_stale"
    SITEMAP_TRUNCATED = "sitemap_truncated"
    VERSIONS_SKIPPED = "versions_skipped"
    BOILERPLATE_REMOVED_CORPUS = "boilerplate_removed_corpus"
    HEADING_DEPTH_CLAMPED = "heading_depth_clamped"
    COMBINED_TOO_LARGE = "combined_too_large"

    # Social
    COMMENTS_TRUNCATED = "comments_truncated"
    COMMENTS_COLLAPSED = "comments_collapsed"
    TOS_RISK_SOURCE = "tos_risk_source"
    PRIVATE_POST = "private_post"
    THREAD_PARTIAL_FEDERATION = "thread_partial_federation"
    API_FALLBACK_HTML = "api_fallback_html"
    BEST_EFFORT_EXTRACTION = "best_effort_extraction"
    RATE_LIMITED = "rate_limited"

    # Code
    SECRET_FILE_EXCLUDED = "secret_file_excluded"
    SECRET_REDACTED = "secret_redacted"
    TOKEN_BUDGET_APPLIED = "token_budget_applied"
    LOG_LINES_COLLAPSED = "log_lines_collapsed"
    LOG_TRUNCATED = "log_truncated"
    TIMEZONE_ASSUMED = "timezone_assumed"
    SPEC_INVALID = "spec_invalid"
    ENV_VALUES_REDACTED = "env_values_redacted"

    # Communication
    QUOTED_HISTORY_REMOVED = "quoted_history_removed"
    THREAD_RECONSTRUCTED_FROM_TEXT = "thread_reconstructed_from_text"
    ORPHAN_THREAD_REPLIES = "orphan_thread_replies"
    UNRESOLVED_USERS = "unresolved_users"
    ATTACHMENT_SKIPPED = "attachment_skipped"
    ATTACHMENT_FAILED = "attachment_failed"
    ATTACHMENT_UNCONVERTED = "attachment_unconverted"
    TNEF_UNPARSED = "tnef_unparsed"
    SMIME_NOT_DECRYPTED = "smime_not_decrypted"
    MSG_PARTIAL = "msg_partial"
    DATE_ORDER_ASSUMED = "date_order_assumed"
    DISCORD_PACKAGE_NO_AUTHORS = "discord_package_no_authors"
    TEAMS_HTML_BEST_EFFORT = "teams_html_best_effort"

    # Data
    JSON_REPAIRED = "json_repaired"
    ROWS_SAMPLED = "rows_sampled"
    COLUMNS_TRUNCATED = "columns_truncated"
    DEPTH_TRUNCATED = "depth_truncated"
    YAML_UNSAFE_TAGS = "yaml_unsafe_tags"
    API_ERROR_PAYLOAD = "api_error_payload"
    SQLITE_ENCRYPTED = "sqlite_encrypted"
    CONNECTION_STRING_REFUSED = "connection_string_refused"

    # Notes
    UNRESOLVED_WIKILINKS = "unresolved_wikilinks"
    AMBIGUOUS_WIKILINK = "ambiguous_wikilink"
    MISSING_RESOURCE = "missing_resource"
    ENCRYPTED_CONTENT = "encrypted_content"
    DATES_FROM_FILESYSTEM = "dates_from_filesystem"
    KINDLE_CLIP_LIMIT = "kindle_clip_limit"
    CLIPPINGS_DEDUPED = "clippings_deduped"

    # Specialized
    XBRL_STATEMENT_MISMATCH = "xbrl_statement_mismatch"
    IXT_FORMAT_UNKNOWN = "ixt_format_unknown"
    RECONCILIATION_FAILED = "reconciliation_failed"
    AMOUNT_CORRECTED_BY_RECONCILIATION = "amount_corrected_by_reconciliation"
    COLUMNS_SWAPPED_BY_RECONCILIATION = "columns_swapped_by_reconciliation"
    DUPLICATE_ROW_AT_PAGE_BREAK = "duplicate_row_at_page_break"
    ACCOUNT_NUMBER_MASKED = "account_number_masked"
    INVOICE_VALIDATION_FAILED = "invoice_validation_failed"
    WORD_INDEX_DROPPED = "word_index_dropped"
    FULLTEXT_UNAVAILABLE = "fulltext_unavailable"
    BIBTEX_DUPLICATE_KEYS = "bibtex_duplicate_keys"
    PHI_REFUSED = "phi_refused"
    PHI_POSSIBLE = "phi_possible"
    MUSIC_SUMMARY_ONLY = "music_summary_only"
    ARCHIVE_ENCRYPTED = "archive_encrypted"
    ARCHIVE_BOMB_SUSPECTED = "archive_bomb_suspected"
    ARCHIVE_PATH_REJECTED = "archive_path_rejected"
    ARCHIVE_TRUNCATED = "archive_truncated"
    ARCHIVE_ENTRY_SKIPPED = "archive_entry_skipped"

    # Media (audio, video, transcripts)
    ASR_CONFIDENCE_LOW = "asr_confidence_low"
    ASR_HALLUCINATION_FILTERED = "asr_hallucination_filtered"
    DELOOP = "deloop"
    NO_SPEECH_DETECTED = "no_speech_detected"
    LANGUAGE_UNCERTAIN = "language_uncertain"
    DURATION_LIMIT_REACHED = "duration_limit_reached"
    DURATION_CAP_EXCEEDED = "duration_cap_exceeded"
    DIARIZATION_SKIPPED_CPU_BUDGET = "diarization_skipped_cpu_budget"
    DIARIZATION_SKIPPED_SHORT = "diarization_skipped_short"
    DIARIZATION_UNAVAILABLE_OFFLOAD = "diarization_unavailable_offload"
    CHAPTERS_GENERATED = "chapters_generated"
    MEDIA_UNAVAILABLE = "media_unavailable"
    CAPTIONS_ONLY = "captions_only"
    BROWSER_ASR_SMALL_MODEL = "browser_asr_small_model"
    TIMESTAMPS_APPROXIMATE = "timestamps_approximate"
    PROFANITY_MASKED = "profanity_masked"
    FILLERS_REMOVED = "fillers_removed"
    VERBATIM_MODE = "verbatim_mode"

    # OCR
    UNREADABLE_REGION = "unreadable_region"
    LAYOUT_OCR_UNAVAILABLE_CPU = "layout_ocr_unavailable_cpu"
    LICENSE_RESTRICTED_ENGINE_USED = "license_restricted_engine_used"
    RECEIPT_TOTALS_MISMATCH = "receipt_totals_mismatch"
    CHAT_SCREENSHOT_DECORATIONS_REMOVED = "chat_screenshot_decorations_removed"

    # Rendering and output
    TABLE_STRUCTURE_UNCERTAIN = "table_structure_uncertain"
    MERGED_CELLS_FLATTENED = "merged_cells_flattened"
    TABLE_SAMPLED = "table_sampled"
    EQUATION_AS_TEXT = "equation_as_text"
    TRUNCATED = "truncated"

    # Fetch and policy
    FETCH_DEGRADED = "fetch_degraded"
    FETCHED_PARTIAL = "fetched_partial"
    FETCH_BLOCKED_BY_PLATFORM = "fetch_blocked_by_platform"
    FETCH_BLOCKED_BY_POLICY = "fetch_blocked_by_policy"
    FETCH_REFUSED_PRIVATE_NETWORK = "fetch_refused_private_network"
    FETCH_REFUSED_SCHEME = "fetch_refused_scheme"
    URL_BLOCKED_BY_POLICY = "url_blocked_by_policy"


@dataclass(frozen=True, slots=True)
class CodeSpec:
    """Registry entry for one warning code."""

    code: WarningKind
    severity: Severity
    family: str
    description: str
    suggestion: str
    truncates: bool = False
    """True when this warning means part of the input or output was cut (sets ConversionResult.truncated)."""


# fmt: off
_SPECS: tuple[CodeSpec, ...] = (
    # Core and detection
    CodeSpec(WarningKind.MISNAMED_FILE, "warning", "core",
             "The file extension does not match the detected format; converted by content.",
             "Rename the file with the extension of its real format."),
    CodeSpec(WarningKind.CONTENT_TYPE_MISMATCH, "warning", "core",
             "The server's Content-Type disagrees with the detected format.",
             "Check the URL serves the intended file, or pass --format to force a converter."),
    CodeSpec(WarningKind.ENCODING_UNCERTAIN, "warning", "core",
             "Text encoding was detected with low confidence; characters may be garbled.",
             "Re-save the file as UTF-8 or pass the source encoding in options."),
    CodeSpec(WarningKind.MULTILINGUAL_CONTENT, "info", "core",
             "The document contains substantial text in more than one language.",
             "Pass --lang to pin the primary language if downstream tools need a single one."),
    CodeSpec(WarningKind.ENGINE_FALLBACK, "warning", "core",
             "The preferred engine failed and a fallback engine produced the output.",
             "Check engine_trace in the sidecar for the failure, or pick an engine with --engine family=name."),
    CodeSpec(WarningKind.ENGINE_FAILED, "error", "core",
             "The conversion engine crashed or was killed and produced no output.",
             "Retry with another engine via --engine family=name, or report the file with a fixture."),
    CodeSpec(WarningKind.CONVERTER_FAILED, "error", "core",
             "The converter raised an error and produced no usable output.",
             "Check the sidecar for the error detail, try another engine, or report the file."),
    CodeSpec(WarningKind.EXTRACTION_EMPTY, "error", "core", "Conversion finished but produced no text.",
             "If the source is scanned or image-only, enable OCR; otherwise confirm the file is not empty."),
    CodeSpec(WarningKind.SIZE_CAP, "warning", "core", "The input exceeded the size cap; only part of it was processed.",
             "Split the input into smaller files, or self-host with a higher size cap."),
    CodeSpec(WarningKind.PAGE_CAP_REACHED, "warning", "core",
             "The page cap was reached; remaining pages were not converted.",
             "Convert the document in page ranges, or raise the page cap on a self-hosted instance."),
    CodeSpec(WarningKind.PAGE_TIMEOUT, "warning", "core",
             "Some pages exceeded the per-page time budget and were skipped.",
             "Convert the listed pages separately, or self-host on faster hardware or a GPU."),
    CodeSpec(WarningKind.ROW_CAP_REACHED, "warning", "core",
             "The row cap was reached; remaining rows were not converted.",
             "Use the CSV export for every row, or raise the row cap in options."),
    CodeSpec(WarningKind.TIMEOUT_PARTIAL, "warning", "core",
             "Conversion hit its time budget; the output covers only what finished.",
             "Retry with a smaller input or fewer pages, or raise the job timeout when self-hosting."),
    CodeSpec(WarningKind.TIMEOUT_HARD, "error", "core", "Conversion exceeded the hard time limit and was stopped.",
             "Split the input into smaller parts, or self-host with a longer timeout."),
    CodeSpec(WarningKind.EXTRA_REQUIRED, "error", "core", "This format needs an optional extra that is not installed.",
             "Install the extra named in the message, e.g. pip install 'ezmd[docs]'."),
    CodeSpec(WarningKind.EXPERIMENTAL_CONVERTER, "info", "core", "The output came from an experimental converter.",
             "Review the output closely and report problems so the converter can graduate."),
    CodeSpec(WarningKind.UNSUPPORTED_FEATURE, "warning", "core",
             "The source uses a feature this converter does not support; it was skipped.",
             "Export the source to a simpler format (PDF, DOCX, HTML) that keeps the feature, then reconvert."),
    CodeSpec(WarningKind.INJECTION_SUSPECTED, "warning", "core",
             "Text matching prompt-injection patterns was found and kept.",
             "Treat the flagged text as untrusted and review sidecar injection_findings before using it."),
    CodeSpec(WarningKind.REMOVED_HIDDEN_ELEMENTS, "info", "core",
             "Hidden elements (CSS-hidden, aria-hidden, invisible text) were removed.",
             "Inspect the original source if the hidden content matters to you."),
    CodeSpec(WarningKind.REMOVED_SCRIPT_OR_MACRO, "info", "core", "Scripts or macros were removed and not executed.",
             "Open the source in its native app if you need to review the macro code."),
    CodeSpec(WarningKind.PII_COLUMNS_REMOVED, "info", "core",
             "Columns detected as personal data were removed from tabular output.",
             "Turn off PII column removal in data options if you are permitted to keep those columns."),
    CodeSpec(WarningKind.NESTING_FLATTENED, "info", "core",
             "List nesting deeper than the supported depth was flattened into the deepest level kept.",
             "No action needed; the text is complete, only the deepest indentation was merged."),
    CodeSpec(WarningKind.IMAGE_SKIPPED, "info", "core", "An image was skipped and appears only as a placeholder.",
             "Enable image OCR or description in options if the image carries information."),
    CodeSpec(WarningKind.IMAGE_TOO_LARGE, "warning", "core", "An image exceeded the pixel limit and was not decoded.",
             "Downscale the image below 50 megapixels and reconvert."),
    CodeSpec(WarningKind.OTHER, "warning", "core",
             "An uncategorized issue occurred; see the warning message for details.",
             "Read the message and sidecar details; report it so a specific code can be added."),
    # PDF
    CodeSpec(WarningKind.ENCRYPTED_NO_PASSWORD, "error", "pdf", "The PDF is encrypted and no password was supplied.",
             "Provide the password in the PDF options or upload an unencrypted copy."),
    CodeSpec(WarningKind.COPY_RESTRICTED_IGNORED, "info", "pdf",
             "The PDF's copy-restriction flag was ignored for extraction.",
             "Make sure you have the right to extract text from this document."),
    CodeSpec(WarningKind.PAGES_WITHOUT_TEXT, "warning", "pdf",
             "Some pages have no text layer; their content is missing.",
             "Enable OCR or upload a text-layer PDF."),
    CodeSpec(WarningKind.OCR_UNAVAILABLE, "warning", "pdf", "OCR was needed but no OCR engine is available.",
             "OCR (the ocr extra) is coming in a later release; use a text-layer PDF or an instance with OCR enabled."),
    CodeSpec(WarningKind.OCR_CONFIDENCE_LOW, "warning", "pdf",
             "OCR confidence was low on some pages or regions; text may be wrong.",
             "Upload a higher-resolution scan (300 DPI or more) or try a layout OCR engine."),
    CodeSpec(WarningKind.READING_ORDER_UNCERTAIN, "warning", "pdf",
             "Reading order of a multi-column or complex layout may be wrong.",
             "Try a layout-aware engine such as --engine pdf=docling, and check column order."),
    CodeSpec(WarningKind.HEADING_SOURCE_STRUCTURE_TREE, "info", "pdf",
             "Headings came from the PDF's tagged structure tree.",
             "No action needed; edit the PDF's tags in the authoring tool to change headings."),
    CodeSpec(WarningKind.STRUCTURE_TREE_UNUSABLE, "info", "pdf",
             "The PDF's structure tree was unusable; layout analysis was used instead.",
             "Re-export the PDF with accessibility tagging for more reliable headings."),
    CodeSpec(WarningKind.REMOVED_RUNNING_HEADER_FOOTER, "info", "pdf",
             "Repeated page headers and footers were removed.",
             "Use the full profile with page provenance if you need page boundaries."),
    CodeSpec(WarningKind.TABLE_REJOINED, "info", "pdf", "A table split across pages was rejoined into one table.",
             "Check the rejoined table at the page break against the source."),
    CodeSpec(WarningKind.EQUATION_UNRECOGNIZED, "warning", "pdf",
             "An equation could not be converted to LaTeX and is missing or raw.",
             "Use an engine with formula recognition, e.g. --engine pdf=docling, or a GPU OCR tier."),
    CodeSpec(WarningKind.XFA_PARTIAL, "warning", "pdf", "XFA form content was only partially extracted.",
             "Print the form to PDF from Adobe Reader to flatten it, then convert that copy."),
    CodeSpec(WarningKind.IWORK_PREVIEW_FALLBACK, "warning", "pdf",
             "The iWork file was converted from its embedded preview, losing structure.",
             "Export from Pages, Numbers or Keynote to DOCX, XLSX or PPTX and convert that."),
    # Office
    CodeSpec(WarningKind.HEADING_INFERRED_FROM_FORMATTING, "info", "office",
             "Headings were inferred from font size and weight, not styles.",
             "Apply Heading styles in the source document for reliable structure."),
    CodeSpec(WarningKind.TEXTBOX_CONTENT_RELOCATED, "info", "office",
             "Text box content was moved to the nearest paragraph position.",
             "Check relocated text box content against the source layout."),
    CodeSpec(WarningKind.HIDDEN_SLIDES_INCLUDED, "info", "office", "Hidden slides were included in the output.",
             "Turn off hidden slide inclusion in the presentation options to omit them."),
    CodeSpec(WarningKind.HIDDEN_SHEETS_INCLUDED, "info", "office", "Hidden sheets were included in the output.",
             "Turn off hidden sheet inclusion in the spreadsheet options to omit them."),
    CodeSpec(WarningKind.FORMULA_UNCALCULATED, "warning", "office",
             "Formula cells have no cached values and are shown blank or as formulas.",
             "Open and save the workbook in Excel or LibreOffice to compute values, then reconvert."),
    CodeSpec(WarningKind.FORMULAS_PRESENT, "info", "office",
             "The workbook contains formulas; values and formulas are both recorded.",
             "Set formulas=false in options if you only want computed values."),
    CodeSpec(WarningKind.CELL_ERRORS, "warning", "office", "Some cells contain errors such as #REF! or #DIV/0!.",
             "Fix the errors in the source workbook; error cells are kept as-is."),
    CodeSpec(WarningKind.POSSIBLE_SERIAL_DATES, "info", "office",
             "Numeric cells look like unformatted date serial numbers.",
             "Apply a date format to those cells in the source workbook."),
    CodeSpec(WarningKind.RAGGED_ROWS, "warning", "office", "Rows have inconsistent column counts and were padded.",
             "Check the source for missing delimiters or stray cells."),
    CodeSpec(WarningKind.SMARTART_FLATTENED, "info", "office", "SmartArt was flattened to a nested list of its text.",
             "Check the source if the diagram's layout carries meaning."),
    CodeSpec(WarningKind.OLE_OBJECT_SKIPPED, "warning", "office",
             "An embedded OLE object could not be converted and was skipped.",
             "Extract the embedded object from the source and convert it separately."),
    CodeSpec(WarningKind.LEGACY_TEXT_ONLY, "warning", "office",
             "A legacy binary format was converted as plain text, losing structure.",
             "Save the file as DOCX, XLSX or PPTX and reconvert."),
    CodeSpec(WarningKind.SLIDE_CAP_REACHED, "warning", "office",
             "The slide cap was reached; remaining slides were not converted.",
             "Split the deck, or raise office.max_slides when self-hosting."),
    CodeSpec(WarningKind.LIBREOFFICE_MISSING, "warning", "office",
             "LibreOffice is not installed, so a lower-fidelity path was used.",
             "Install LibreOffice so soffice is on PATH, then reconvert."),
    CodeSpec(WarningKind.PAGES_ESTIMATED, "info", "office",
             "Page numbers are estimated because the format has no fixed pages.",
             "Cite by section heading rather than page number."),
    CodeSpec(WarningKind.EQUATION_PARTIAL, "warning", "office", "Some equations were converted only partially.",
             "Compare equations with the source; DOCX with native equations converts best."),
    CodeSpec(WarningKind.TRACKED_CHANGES_PRESENT, "info", "office",
             "The document has tracked changes; they were accepted in the output.",
             "Set track_changes=all to keep insertions and deletions as CriticMarkup."),
    CodeSpec(WarningKind.COMMENTS_PRESENT, "info", "office",
             "The document has reviewer comments that are not in the body.",
             "Set track_changes=all to render comments inline at their anchors."),
    # Google
    CodeSpec(WarningKind.PRIVATE_LINK, "error", "google", "The Google link is not publicly accessible.",
             "Share the file as 'Anyone with the link can view', or export it and upload the file."),
    CodeSpec(WarningKind.FIRST_SHEET_ONLY, "warning", "google",
             "Only the first sheet of the Google Sheet was exported.",
             "Download the spreadsheet as XLSX and upload it to convert every sheet."),
    CodeSpec(WarningKind.SUGGESTIONS_NOT_EXPORTED, "info", "google",
             "Suggested edits in the Google Doc were not exported.",
             "Download the doc as DOCX to keep suggestions as tracked changes, then convert that."),
    # Ebooks and text
    CodeSpec(WarningKind.EPUB_MIMETYPE_MISSING, "info", "ebooks",
             "The EPUB lacks its mimetype entry; it was parsed anyway.",
             "Re-export the EPUB with a compliant tool if other readers reject it."),
    CodeSpec(WarningKind.CALIBRE_MISSING, "error", "ebooks",
             "Calibre is required for this ebook format and is not installed.",
             "Install Calibre so ebook-convert is on PATH, or convert the book to EPUB first."),
    CodeSpec(WarningKind.DRM_PROTECTED, "error", "ebooks", "The ebook is DRM-protected and cannot be read.",
             "Use a DRM-free copy of the book."),
    CodeSpec(WarningKind.LATEX_MAIN_AMBIGUOUS, "warning", "ebooks",
             "Several LaTeX files could be the main document; one was picked.",
             "Name the main .tex file explicitly in the LaTeX options."),
    CodeSpec(WarningKind.LATEX_UNKNOWN_MACRO, "info", "ebooks", "Unknown LaTeX macros were kept verbatim.",
             "Include the .sty or macro definitions in the upload so they can be expanded."),
    CodeSpec(WarningKind.NOTEBOOK_INVALID, "warning", "ebooks",
             "The notebook fails nbformat validation and was parsed best-effort.",
             "Open and re-save the notebook in Jupyter to repair it."),
    CodeSpec(WarningKind.MDX_COMPONENTS_STRIPPED, "info", "ebooks",
             "MDX components were removed, keeping their text children.",
             "Convert the rendered HTML page instead if components carry essential content."),
    CodeSpec(WarningKind.TABLE_INFERRED, "info", "ebooks", "A table was inferred from aligned plain text.",
             "Check the inferred table against the source text."),
    CodeSpec(WarningKind.EMPTY_BODY_JS_REQUIRED, "error", "ebooks",
             "The page body is empty without JavaScript rendering.",
             "Enable the browser rendering engine, or convert the page with the browser extension."),
    CodeSpec(WarningKind.MARKUP_PARTIAL, "warning", "ebooks",
             "Markup was only partially parsed; some constructs remain as raw text.",
             "Check the raw spans, or convert from the original source format if available."),
    # Web
    CodeSpec(WarningKind.ROBOTS_DISALLOWED, "error", "web", "robots.txt disallows fetching this URL.",
             "Save the page in your browser and upload it, or use the browser extension."),
    CodeSpec(WarningKind.HTTP_ERROR, "error", "web", "The server returned an HTTP error status.",
             "Check the URL opens in a browser, then retry; the message has the status code."),
    CodeSpec(WarningKind.PAYWALL_DETECTED, "warning", "web",
             "A paywall was detected; only the free portion was converted.",
             "Save the page from a logged-in browser and upload it, or use the browser extension."),
    CodeSpec(WarningKind.READABILITY_FALLBACK_FULL_BODY, "info", "web",
             "Main-content extraction failed, so the full page body was kept.",
             "Expect navigation text; use the extension's selection mode to convert only the article."),
    CodeSpec(WarningKind.MULTIPAGE_ARTICLE, "info", "web", "The article spans multiple pages, which were joined.",
             "Check the page joins, or pass the site's single-page or print URL."),
    CodeSpec(WarningKind.LAZY_CONTENT_POSSIBLE, "info", "web",
             "The page may load more content on scroll that was not captured.",
             "Enable browser rendering, or convert with the extension after scrolling to the end."),
    CodeSpec(WarningKind.IMAGES_WITHOUT_ALT, "info", "web",
             "Some images have no alt text and are listed without description.",
             "Enable image description or OCR if the images carry information."),
    CodeSpec(WarningKind.FETCH_BLOCKED, "error", "web", "The remote site blocked the fetch.",
             "Download the content in your browser and upload it, or use the browser extension."),
    CodeSpec(WarningKind.FETCH_FAILED, "error", "web", "The network fetch failed (DNS, TLS, connection or timeout).",
             "Check the URL and that the site is up, then retry."),
    # Sites
    CodeSpec(WarningKind.LLMS_TXT_USED, "info", "sites", "The site's llms.txt was used to choose pages.",
             "Pass a sitemap URL or explicit URL list to crawl a different set of pages."),
    CodeSpec(WarningKind.LLMS_TXT_MAY_BE_STALE, "info", "sites", "llms.txt looks older than the site's content.",
             "Crawl via the sitemap instead of llms.txt to get current pages."),
    CodeSpec(WarningKind.SITEMAP_TRUNCATED, "warning", "sites",
             "The sitemap had more URLs than the page limit; the rest were skipped.",
             "Raise the site page limit, or narrow the crawl with an include pattern."),
    CodeSpec(WarningKind.VERSIONS_SKIPPED, "info", "sites", "Older documentation versions were skipped.",
             "Pass the versioned URL prefix to convert a specific version."),
    CodeSpec(WarningKind.BOILERPLATE_REMOVED_CORPUS, "info", "sites",
             "Navigation repeated across pages was removed corpus-wide.",
             "Turn off corpus boilerplate removal in site options if you need that text."),
    CodeSpec(WarningKind.HEADING_DEPTH_CLAMPED, "info", "sites",
             "Heading levels were clamped when pages were combined.",
             "Use per-page output to keep each page's original heading depth."),
    CodeSpec(WarningKind.COMBINED_TOO_LARGE, "warning", "sites", "The combined site output exceeds the size cap.",
             "Use per-page output or the rag profile instead of one combined file."),
    # Social
    CodeSpec(WarningKind.COMMENTS_TRUNCATED, "warning", "social", "Only part of the comment thread was fetched.",
             "Raise the comment limit in options, or configure the platform API key."),
    CodeSpec(WarningKind.COMMENTS_COLLAPSED, "info", "social", "Low-scored or deep comment branches were collapsed.",
             "Raise the comment depth option to include collapsed branches."),
    CodeSpec(WarningKind.TOS_RISK_SOURCE, "warning", "social",
             "The source's terms of service restrict automated access.",
             "Make sure your use complies with the platform's terms; prefer an official export."),
    CodeSpec(WarningKind.PRIVATE_POST, "error", "social", "The post is private or requires login.",
             "Save the post from a logged-in browser and upload it, or use the browser extension."),
    CodeSpec(WarningKind.THREAD_PARTIAL_FEDERATION, "info", "social",
             "Some federated replies on other servers could not be fetched.",
             "Open the thread on its home server to convert remote replies."),
    CodeSpec(WarningKind.API_FALLBACK_HTML, "warning", "social",
             "The platform API was unavailable, so HTML scraping was used.",
             "Configure the platform API credentials for complete, stable extraction."),
    CodeSpec(WarningKind.BEST_EFFORT_EXTRACTION, "warning", "social",
             "Extraction relied on fragile heuristics; fields may be missing.",
             "Verify key fields against the source, or use an official export."),
    CodeSpec(WarningKind.RATE_LIMITED, "error", "social", "The platform rate-limited the request.",
             "Wait a few minutes and retry, or configure your own API credentials."),
    # Code
    CodeSpec(WarningKind.SECRET_FILE_EXCLUDED, "info", "code",
             "Files that look like secrets (.env, private keys) were excluded.",
             "No action needed; rename the file if it was wrongly detected as a secret."),
    CodeSpec(WarningKind.SECRET_REDACTED, "info", "code", "Values that look like secrets (keys, tokens) were redacted.",
             "No action needed; rotate the secret if the source was shared anywhere."),
    CodeSpec(WarningKind.TOKEN_BUDGET_APPLIED, "warning", "code",
             "Repository output was trimmed to fit the token budget.",
             "Raise max_tokens or narrow the include globs to the files you need."),
    CodeSpec(WarningKind.LOG_LINES_COLLAPSED, "info", "code", "Repeated log lines were collapsed with counts.",
             "Turn off log collapsing in options if you need every line."),
    CodeSpec(WarningKind.LOG_TRUNCATED, "warning", "code", "The log was truncated to fit limits.",
             "Filter the log by time range or level before converting."),
    CodeSpec(WarningKind.TIMEZONE_ASSUMED, "info", "code", "Timestamps had no timezone, so UTC was assumed.",
             "Pass the source timezone in options if the timestamps are local time."),
    CodeSpec(WarningKind.SPEC_INVALID, "warning", "code",
             "The API spec fails schema validation and was rendered best-effort.",
             "Validate the spec with an OpenAPI linter, fix the errors, and reconvert."),
    CodeSpec(WarningKind.ENV_VALUES_REDACTED, "info", "code",
             "Values in environment files were redacted; only keys are kept.",
             "No action needed; share values through a secret manager, not converted output."),
    # Communication
    CodeSpec(WarningKind.QUOTED_HISTORY_REMOVED, "info", "comms", "Quoted reply history was removed from messages.",
             "Turn off quoted-history stripping in email options to keep it."),
    CodeSpec(WarningKind.THREAD_RECONSTRUCTED_FROM_TEXT, "info", "comms",
             "Thread order was reconstructed from message text, not headers.",
             "Export with full headers (EML or MBOX) for reliable threading."),
    CodeSpec(WarningKind.ORPHAN_THREAD_REPLIES, "warning", "comms",
             "Some replies reference parent messages that are missing.",
             "Include the full export or channel history so parents can be matched."),
    CodeSpec(WarningKind.UNRESOLVED_USERS, "warning", "comms", "Some user IDs could not be resolved to names.",
             "Include the export's users file (e.g. users.json) in the upload."),
    CodeSpec(WarningKind.ATTACHMENT_SKIPPED, "info", "comms",
             "An attachment was skipped by policy or type and is listed by name.",
             "Extract the attachment and convert it separately if you need its content."),
    CodeSpec(WarningKind.ATTACHMENT_FAILED, "warning", "comms",
             "An attachment failed to convert and is listed by name only.",
             "Extract the attachment and convert it on its own to see the specific error."),
    CodeSpec(WarningKind.ATTACHMENT_UNCONVERTED, "warning", "comms",
             "An attachment could not be converted and is listed by name only.",
             "Extract the named attachment and convert it separately."),
    CodeSpec(WarningKind.TNEF_UNPARSED, "warning", "comms", "A winmail.dat (TNEF) attachment could not be decoded.",
             "Ask the sender to resend in plain or HTML format, or decode it with a TNEF tool."),
    CodeSpec(WarningKind.SMIME_NOT_DECRYPTED, "warning", "comms",
             "An S/MIME encrypted message body could not be decrypted.",
             "Decrypt the message in your mail client and export the decrypted copy."),
    CodeSpec(WarningKind.MSG_PARTIAL, "warning", "comms", "The Outlook MSG file was parsed only partially.",
             "Install the nonfree extra for full MSG support, or save the message as EML."),
    CodeSpec(WarningKind.DATE_ORDER_ASSUMED, "warning", "comms",
             "Ambiguous dates were parsed with an assumed day/month order.",
             "Pass the date order (DMY or MDY) in options to match the export's locale."),
    CodeSpec(WarningKind.DISCORD_PACKAGE_NO_AUTHORS, "info", "comms",
             "The Discord data package lacks names for other users.",
             "Use a channel export tool that includes author names for full attribution."),
    CodeSpec(WarningKind.TEAMS_HTML_BEST_EFFORT, "warning", "comms", "The Teams HTML export was parsed best-effort.",
             "Use a Teams JSON export (Purview or Graph) for reliable structure."),
    # Data
    CodeSpec(WarningKind.JSON_REPAIRED, "warning", "data", "Invalid JSON was repaired before parsing.",
             "Fix the source JSON; repaired values may differ from what was intended."),
    CodeSpec(WarningKind.ROWS_SAMPLED, "info", "data",
             "Only a sample of rows is shown; full data is in the CSV export.",
             "Use the CSV export for every row."),
    CodeSpec(WarningKind.COLUMNS_TRUNCATED, "info", "data", "Wide data had columns truncated.",
             "Select the columns you need in options, or use the CSV export."),
    CodeSpec(WarningKind.DEPTH_TRUNCATED, "info", "data", "Nested data beyond the depth limit was truncated.",
             "Raise the depth limit in data options."),
    CodeSpec(WarningKind.YAML_UNSAFE_TAGS, "warning", "data", "The YAML contains unsafe tags, which were not executed.",
             "Remove language-specific tags such as !!python/object from the YAML."),
    CodeSpec(WarningKind.API_ERROR_PAYLOAD, "warning", "data", "The fetched JSON looks like an API error response.",
             "Check the API URL, authentication and query parameters."),
    CodeSpec(WarningKind.SQLITE_ENCRYPTED, "error", "data", "The SQLite database is encrypted.",
             "Decrypt the database (e.g. with SQLCipher) and upload the plain copy."),
    CodeSpec(WarningKind.CONNECTION_STRING_REFUSED, "error", "data",
             "Database connection strings are refused for safety.",
             "Export the data to a file such as CSV or SQLite and upload that."),
    # Notes
    CodeSpec(WarningKind.UNRESOLVED_WIKILINKS, "info", "notes", "Some wikilinks point to notes not in the upload.",
             "Upload the whole vault folder so links can resolve."),
    CodeSpec(WarningKind.AMBIGUOUS_WIKILINK, "info", "notes",
             "A wikilink matched more than one note; the first match was used.",
             "Use full paths in wikilinks to disambiguate."),
    CodeSpec(WarningKind.MISSING_RESOURCE, "warning", "notes", "An embedded image or attachment was not found.",
             "Include the attachments folder in the upload."),
    CodeSpec(WarningKind.ENCRYPTED_CONTENT, "info", "notes", "Encrypted content was skipped.",
             "Decrypt the content in its source app and export it again."),
    CodeSpec(WarningKind.DATES_FROM_FILESYSTEM, "info", "notes",
             "Note dates come from filesystem timestamps, which may be wrong.",
             "Add created and updated dates to the notes' frontmatter."),
    CodeSpec(WarningKind.KINDLE_CLIP_LIMIT, "warning", "notes",
             "Kindle highlights are cut off at the publisher's export limit.",
             "Copy the full passage from the book itself; the export cannot recover it."),
    CodeSpec(WarningKind.CLIPPINGS_DEDUPED, "info", "notes", "Duplicate Kindle highlights were merged.",
             "Check merged highlights if you edited a highlight and expected both versions."),
    # Specialized
    CodeSpec(WarningKind.XBRL_STATEMENT_MISMATCH, "warning", "specialized",
             "XBRL facts disagree with the rendered statement.",
             "Compare the flagged values with the filing's official XBRL viewer."),
    CodeSpec(WarningKind.IXT_FORMAT_UNKNOWN, "warning", "specialized",
             "Inline XBRL used an unknown transformation format.",
             "Check the flagged facts by hand; upgrade ezmd in case the format was added."),
    CodeSpec(WarningKind.RECONCILIATION_FAILED, "error", "specialized",
             "Statement totals do not reconcile with the extracted rows.",
             "Review the flagged page against the source; try a layout OCR engine for scans."),
    CodeSpec(WarningKind.AMOUNT_CORRECTED_BY_RECONCILIATION, "warning", "specialized",
             "An amount was corrected so totals reconcile.",
             "Verify the corrected amount against the source document."),
    CodeSpec(WarningKind.COLUMNS_SWAPPED_BY_RECONCILIATION, "warning", "specialized",
             "Debit and credit columns were swapped so totals reconcile.",
             "Verify the column assignment against the source document."),
    CodeSpec(WarningKind.DUPLICATE_ROW_AT_PAGE_BREAK, "info", "specialized",
             "A row repeated at a page break was removed.",
             "Check the page break in the source if row counts look off."),
    CodeSpec(WarningKind.ACCOUNT_NUMBER_MASKED, "info", "specialized",
             "Account numbers were masked to their last digits.",
             "No action needed; refer to the source document for full numbers."),
    CodeSpec(WarningKind.INVOICE_VALIDATION_FAILED, "warning", "specialized",
             "Invoice totals or required fields failed validation.",
             "Check line items, tax and totals against the source invoice."),
    CodeSpec(WarningKind.WORD_INDEX_DROPPED, "info", "specialized", "A back-of-book word index was dropped.",
             "Convert the index pages separately if you need them."),
    CodeSpec(WarningKind.FULLTEXT_UNAVAILABLE, "warning", "specialized",
             "Full text was unavailable; only metadata or the abstract was converted.",
             "Upload the full-text PDF, or use an open-access link."),
    CodeSpec(WarningKind.BIBTEX_DUPLICATE_KEYS, "warning", "specialized",
             "The BibTeX file has duplicate citation keys.",
             "Rename the duplicate keys in the .bib file."),
    CodeSpec(WarningKind.PHI_REFUSED, "error", "specialized",
             "The content appears to contain protected health information and was refused.",
             "Self-host ezmd to process health records under your own compliance controls."),
    CodeSpec(WarningKind.PHI_POSSIBLE, "warning", "specialized",
             "The content may contain protected health information.",
             "Review and redact before sharing, and self-host for regulated data."),
    CodeSpec(WarningKind.MUSIC_SUMMARY_ONLY, "info", "specialized",
             "The music file was summarized (tags, duration) without transcription.",
             "Force transcription in the media options if the file contains speech."),
    CodeSpec(WarningKind.ARCHIVE_ENCRYPTED, "warning", "specialized", "Encrypted archive entries could not be read.",
             "Provide the archive password, or upload an unencrypted archive."),
    CodeSpec(WarningKind.ARCHIVE_BOMB_SUSPECTED, "error", "specialized",
             "The archive expands beyond safe limits and was refused.",
             "Extract the files you need locally and upload them individually."),
    CodeSpec(WarningKind.ARCHIVE_PATH_REJECTED, "warning", "specialized",
             "Archive entries with unsafe paths were rejected.",
             "Repack the archive with relative paths and no symlinks."),
    CodeSpec(WarningKind.ARCHIVE_TRUNCATED, "warning", "specialized",
             "Archive extraction stopped at the entry-count or expansion-ratio limit.",
             "Upload fewer files per archive, or raise the archive limits when self-hosting."),
    CodeSpec(WarningKind.ARCHIVE_ENTRY_SKIPPED, "warning", "specialized",
             "Archive entries with traversal paths, absolute paths or symlinks were skipped.",
             "Repack the archive with plain relative paths and upload it again."),
    # Media (audio, video, transcripts)
    CodeSpec(WarningKind.ASR_CONFIDENCE_LOW, "warning", "media",
             "Speech recognition confidence was low; the transcript may contain errors.",
             "Upload a cleaner recording, or retry with a larger ASR model."),
    CodeSpec(WarningKind.ASR_HALLUCINATION_FILTERED, "info", "media",
             "Likely ASR hallucinations (text over silence or music) were removed.",
             "Check the flagged timestamps against the audio if you need every word."),
    CodeSpec(WarningKind.DELOOP, "info", "media", "Repeated n-gram loops in ASR output were collapsed.",
             "Check the marked segments against the audio; a larger model loops less."),
    CodeSpec(WarningKind.NO_SPEECH_DETECTED, "warning", "media",
             "Almost no speech was detected, so the transcript is empty.",
             "Check the file has an audio track with speech; set the language if it is quiet speech."),
    CodeSpec(WarningKind.LANGUAGE_UNCERTAIN, "warning", "media", "The language was detected with low confidence.",
             "Pass --lang with the correct language code and reconvert."),
    CodeSpec(WarningKind.DURATION_LIMIT_REACHED, "warning", "media",
             "The media duration limit was reached; later audio was not transcribed.",
             "Trim the file into shorter parts, or self-host with a higher duration limit."),
    CodeSpec(WarningKind.DURATION_CAP_EXCEEDED, "warning", "media",
             "The audio exceeded this instance's duration cap; only the start was transcribed.",
             "Split the audio into shorter parts, or self-host to remove the cap."),
    CodeSpec(WarningKind.DIARIZATION_SKIPPED_CPU_BUDGET, "warning", "media",
             "Speaker labels were skipped because the audio exceeds the CPU budget.",
             "Force diarization in options, or run on a GPU or a hosted backend that includes it."),
    CodeSpec(WarningKind.DIARIZATION_SKIPPED_SHORT, "info", "media",
             "Speaker labels were skipped because the audio is very short.",
             "No action needed; force diarization in options if the clip has several speakers."),
    CodeSpec(WarningKind.DIARIZATION_UNAVAILABLE_OFFLOAD, "warning", "media",
             "The hosted ASR backend has no diarization, so speaker labels are missing.",
             "Use a local or diarizing backend (e.g. Deepgram), or upload a shorter clip that stays local."),
    CodeSpec(WarningKind.CHAPTERS_GENERATED, "info", "media",
             "Chapters were generated automatically rather than taken from the source.",
             "Check chapter boundaries and titles; add chapters at the source to use them instead."),
    CodeSpec(WarningKind.MEDIA_UNAVAILABLE, "error", "media",
             "The media could not be downloaded; only metadata was converted.",
             "Upload the media file directly, or use the browser extension or share sheet."),
    CodeSpec(WarningKind.CAPTIONS_ONLY, "info", "media",
             "The transcript comes from platform captions, not speech recognition.",
             "Request ASR in options if the captions are poor or missing words."),
    CodeSpec(WarningKind.BROWSER_ASR_SMALL_MODEL, "warning", "media",
             "A small in-browser ASR model was used; expect more transcription errors.",
             "Choose a larger browser model, or convert on the server for better accuracy."),
    CodeSpec(WarningKind.TIMESTAMPS_APPROXIMATE, "info", "media",
             "Timestamps are approximate rather than word-aligned.",
             "Use server-side ASR with word timestamps if you need precise timing."),
    CodeSpec(WarningKind.PROFANITY_MASKED, "info", "media", "Profanity in the transcript was masked.",
             "Turn off profanity masking in the transcript options to keep the original words."),
    CodeSpec(WarningKind.FILLERS_REMOVED, "info", "media", "Filler words (um, uh) were removed from the transcript.",
             "Enable verbatim mode to keep filler words."),
    CodeSpec(WarningKind.VERBATIM_MODE, "info", "media",
             "The transcript is verbatim, with fillers and false starts kept.",
             "Turn off verbatim mode for a cleaner, more readable transcript."),
    # OCR
    CodeSpec(WarningKind.UNREADABLE_REGION, "warning", "ocr", "A region of the page or image could not be read.",
             "Upload a sharper, higher-resolution scan of the marked region."),
    CodeSpec(WarningKind.LAYOUT_OCR_UNAVAILABLE_CPU, "warning", "ocr",
             "Layout-aware OCR needs a GPU; basic OCR was used on this CPU-only host.",
             "Run on a host with a GPU, or install a CPU-capable layout model, for complex layouts."),
    CodeSpec(WarningKind.LICENSE_RESTRICTED_ENGINE_USED, "info", "ocr",
             "A license-restricted OCR engine (non-commercial or OpenRAIL) was used.",
             "Check the engine license allows your use, or unset EZMD_ALLOW_RESTRICTED_MODELS."),
    CodeSpec(WarningKind.RECEIPT_TOTALS_MISMATCH, "warning", "ocr", "Receipt line items, tax and total do not add up.",
             "Check the flagged values against the receipt; rescan if digits are blurred."),
    CodeSpec(WarningKind.CHAT_SCREENSHOT_DECORATIONS_REMOVED, "info", "ocr",
             "Chat app UI elements (status bar, buttons) were removed.",
             "No action needed; crop the screenshot yourself if something was wrongly removed."),
    # Rendering and output
    CodeSpec(WarningKind.TABLE_STRUCTURE_UNCERTAIN, "warning", "render",
             "Table structure was detected with low confidence; cells may be misaligned.",
             "Check the table against the source, or try a layout-aware engine."),
    CodeSpec(WarningKind.MERGED_CELLS_FLATTENED, "info", "render",
             "Merged table cells were flattened by repeating their value.",
             "Use the full profile with merged_cells=html to keep spans as an HTML table."),
    CodeSpec(WarningKind.TABLE_SAMPLED, "info", "render",
             "A very large table was sampled; full data is in the CSV export.",
             "Use the table's CSV export for every row."),
    CodeSpec(WarningKind.EQUATION_AS_TEXT, "info", "render", "An equation was kept as plain text instead of LaTeX.",
             "Use an engine with formula recognition if you need LaTeX output."),
    CodeSpec(WarningKind.TRUNCATED, "warning", "render",
             "Output was truncated at a size, token or output cap; detail.reason says which.",
             "Raise max_tokens or page through the result with the cursor, or self-host with a higher cap."),
    # Fetch and policy
    CodeSpec(WarningKind.FETCH_DEGRADED, "warning", "fetch",
             "The fetch used a degraded path; content may be incomplete.",
             "Retry later, or upload the file directly for complete content."),
    CodeSpec(WarningKind.FETCHED_PARTIAL, "warning", "fetch", "Only part of the remote content was fetched.",
             "Retry, or download the content in your browser and upload it."),
    CodeSpec(WarningKind.FETCH_BLOCKED_BY_PLATFORM, "error", "fetch", "The platform blocked the server's fetch.",
             "Upload the file directly, or install the browser extension to fetch from your own connection."),
    CodeSpec(WarningKind.FETCH_BLOCKED_BY_POLICY, "error", "fetch",
             "This source is disabled for direct fetch on this instance.",
             "Use the browser extension or share sheet, or upload the file directly."),
    CodeSpec(WarningKind.FETCH_REFUSED_PRIVATE_NETWORK, "error", "fetch",
             "The URL resolves to a private or local network address and was refused.",
             "Use a public URL, or upload the file; self-host to convert intranet URLs."),
    CodeSpec(WarningKind.FETCH_REFUSED_SCHEME, "error", "fetch",
             "The URL scheme is not allowed; only http and https are fetched.",
             "Use an http or https URL, or upload the file directly."),
    CodeSpec(WarningKind.URL_BLOCKED_BY_POLICY, "error", "fetch",
             "The URL matches this instance's blocklist and was refused.",
             "Upload the content as a file, or contact the instance operator if this is a mistake."),
)
# fmt: on

_TRUNCATING: frozenset[WarningKind] = frozenset(
    {
        WarningKind.SIZE_CAP,
        WarningKind.PAGE_CAP_REACHED,
        WarningKind.PAGE_TIMEOUT,
        WarningKind.ROW_CAP_REACHED,
        WarningKind.SLIDE_CAP_REACHED,
        WarningKind.TIMEOUT_PARTIAL,
        WarningKind.TIMEOUT_HARD,
        WarningKind.SITEMAP_TRUNCATED,
        WarningKind.COMMENTS_TRUNCATED,
        WarningKind.TOKEN_BUDGET_APPLIED,
        WarningKind.LOG_TRUNCATED,
        WarningKind.ROWS_SAMPLED,
        WarningKind.COLUMNS_TRUNCATED,
        WarningKind.DEPTH_TRUNCATED,
        WarningKind.ARCHIVE_TRUNCATED,
        WarningKind.DURATION_LIMIT_REACHED,
        WarningKind.DURATION_CAP_EXCEEDED,
        WarningKind.TABLE_SAMPLED,
        WarningKind.TRUNCATED,
        WarningKind.FETCHED_PARTIAL,
    }
)

CODES: dict[WarningKind, CodeSpec] = {spec.code: replace(spec, truncates=spec.code in _TRUNCATING) for spec in _SPECS}

ALIASES: dict[str, WarningKind] = {
    "fallback_engine_used": WarningKind.ENGINE_FALLBACK,
    "engine_downgraded": WarningKind.ENGINE_FALLBACK,
    "page_limit_reached": WarningKind.PAGE_CAP_REACHED,
    "hidden_sheets": WarningKind.HIDDEN_SHEETS_INCLUDED,
    "injection_pattern": WarningKind.INJECTION_SUSPECTED,
    "possible_prompt_injection": WarningKind.INJECTION_SUSPECTED,
    "injection_flagged": WarningKind.INJECTION_SUSPECTED,
    "table_merged_cells_flattened": WarningKind.MERGED_CELLS_FLATTENED,
    "encoding_guessed": WarningKind.ENCODING_UNCERTAIN,
    "truncated_max_tokens": WarningKind.TRUNCATED,
    "output_truncated": WarningKind.TRUNCATED,
    "unreadable_regions": WarningKind.UNREADABLE_REGION,
    "removed_invisible_chars": WarningKind.REMOVED_HIDDEN_ELEMENTS,
}
"""Retired spellings (D-0017 item 3). They still parse and normalize to the canonical Part 2 13.6 code."""


def normalize_code(code: str) -> WarningKind:
    """Return the canonical WarningKind for a code or one of its retired aliases; raise ``ValueError`` otherwise."""
    if isinstance(code, WarningKind):
        return code
    alias = ALIASES.get(code)
    if alias is not None:
        return alias
    return WarningKind(code)


def spec_for(kind: WarningKind | str) -> CodeSpec:
    """Return the registry entry for a warning code; raise ``KeyError`` for an unknown code."""
    try:
        member = normalize_code(kind)
    except ValueError:
        raise KeyError(kind) from None
    return CODES[member]
