# Warning codes

Every loss or degradation intomd knows about is reported as a structured warning with one of these codes.
Generated from `packages/core/src/intomd/warnings/codes.py` by `tools/gen_warnings_doc.py`; do not edit.

| Code | Severity | Family | Meaning | What you can do |
|---|---|---|---|---|
| `misnamed_file` | warning | core | The file extension does not match the detected format; converted by content. | Rename the file with the extension of its real format. |
| `content_type_mismatch` | warning | core | The server's Content-Type disagrees with the detected format. | Check the URL serves the intended file, or pass --format to force a converter. |
| `encoding_uncertain` | warning | core | Text encoding was detected with low confidence; characters may be garbled. | Re-save the file as UTF-8 or pass the source encoding in options. |
| `encoding_guessed` | warning | core | No encoding was declared; the text encoding was guessed. | Re-save the file as UTF-8 or declare its charset, then reconvert. |
| `multilingual_content` | info | core | The document contains substantial text in more than one language. | Pass --lang to pin the primary language if downstream tools need a single one. |
| `engine_fallback` | warning | core | The preferred engine failed and a fallback engine produced the output. | Check engine_trace in the sidecar for the failure, or pick an engine with --engine family=name. |
| `fallback_engine_used` | warning | core | A lower-fidelity fallback engine was used for this conversion. | Install the extra for the preferred engine (see `intomd converters list`) and reconvert. |
| `engine_downgraded` | warning | core | The preferred engine's extra is missing; a lighter engine was used instead. | Install the missing extra, e.g. pip install 'intomd[docs]', for full-fidelity output. |
| `engine_failed` | error | core | The conversion engine crashed or was killed and produced no output. | Retry with another engine via --engine family=name, or report the file with a fixture. |
| `converter_failed` | error | core | The converter raised an error and produced no usable output. | Check the sidecar for the error detail, try another engine, or report the file. |
| `extraction_empty` | error | core | Conversion finished but produced no text. | If the source is scanned or image-only, enable OCR; otherwise confirm the file is not empty. |
| `size_cap` | warning | core | The input exceeded the size cap; only part of it was processed. | Split the input into smaller files, or self-host with a higher size cap. |
| `page_cap_reached` | warning | core | The page cap was reached; remaining pages were not converted. | Convert the document in page ranges, or raise the page cap on a self-hosted instance. |
| `page_limit_reached` | warning | core | The page limit was reached; later pages were not converted. | Convert the remaining pages as a separate range, or raise the page limit when self-hosting. |
| `page_timeout` | warning | core | Some pages exceeded the per-page time budget and were skipped. | Convert the listed pages separately, or self-host on faster hardware or a GPU. |
| `row_cap_reached` | warning | core | The row cap was reached; remaining rows were not converted. | Use the CSV export for every row, or raise the row cap in options. |
| `timeout_partial` | warning | core | Conversion hit its time budget; the output covers only what finished. | Retry with a smaller input or fewer pages, or raise the job timeout when self-hosting. |
| `timeout_hard` | error | core | Conversion exceeded the hard time limit and was stopped. | Split the input into smaller parts, or self-host with a longer timeout. |
| `extra_required` | error | core | This format needs an optional extra that is not installed. | Install the extra named in the message, e.g. pip install 'intomd[docs]'. |
| `experimental_converter` | info | core | The output came from an experimental converter. | Review the output closely and report problems so the converter can graduate. |
| `unsupported_feature` | warning | core | The source uses a feature this converter does not support; it was skipped. | Export the source to a simpler format (PDF, DOCX, HTML) that keeps the feature, then reconvert. |
| `injection_suspected` | warning | core | Text matching prompt-injection patterns was found and kept. | Treat the flagged text as untrusted and review sidecar injection_findings before using it. |
| `removed_hidden_elements` | info | core | Hidden elements (CSS-hidden, aria-hidden, invisible text) were removed. | Inspect the original source if the hidden content matters to you. |
| `removed_invisible_chars` | info | core | Zero-width and other invisible characters were removed. | Inspect the original file if invisible characters carry meaning. |
| `removed_script_or_macro` | info | core | Scripts or macros were removed and not executed. | Open the source in its native app if you need to review the macro code. |
| `pii_columns_removed` | info | core | Columns detected as personal data were removed from tabular output. | Turn off PII column removal in data options if you are permitted to keep those columns. |
| `image_skipped` | info | core | An image was skipped and appears only as a placeholder. | Enable image OCR or description in options if the image carries information. |
| `image_too_large` | warning | core | An image exceeded the pixel limit and was not decoded. | Downscale the image below 50 megapixels and reconvert. |
| `other` | warning | core | An uncategorized issue occurred; see the warning message for details. | Read the message and sidecar details; report it so a specific code can be added. |
| `encrypted_no_password` | error | pdf | The PDF is encrypted and no password was supplied. | Provide the password in the PDF options or upload an unencrypted copy. |
| `copy_restricted_ignored` | info | pdf | The PDF's copy-restriction flag was ignored for extraction. | Make sure you have the right to extract text from this document. |
| `pages_without_text` | warning | pdf | Some pages have no text layer; their content is missing. | Enable OCR or upload a text-layer PDF. |
| `ocr_unavailable` | warning | pdf | OCR was needed but no OCR engine is available. | Install the ocr extra, e.g. pip install 'intomd[ocr]', or use an instance with OCR enabled. |
| `ocr_confidence_low` | warning | pdf | OCR confidence was low on some pages or regions; text may be wrong. | Upload a higher-resolution scan (300 DPI or more) or try a layout OCR engine. |
| `reading_order_uncertain` | warning | pdf | Reading order of a multi-column or complex layout may be wrong. | Try a layout-aware engine such as --engine pdf=docling, and check column order. |
| `heading_source_structure_tree` | info | pdf | Headings came from the PDF's tagged structure tree. | No action needed; edit the PDF's tags in the authoring tool to change headings. |
| `structure_tree_unusable` | info | pdf | The PDF's structure tree was unusable; layout analysis was used instead. | Re-export the PDF with accessibility tagging for more reliable headings. |
| `removed_running_header_footer` | info | pdf | Repeated page headers and footers were removed. | Use the full profile with page provenance if you need page boundaries. |
| `table_rejoined` | info | pdf | A table split across pages was rejoined into one table. | Check the rejoined table at the page break against the source. |
| `equation_unrecognized` | warning | pdf | An equation could not be converted to LaTeX and is missing or raw. | Use an engine with formula recognition, e.g. --engine pdf=docling, or a GPU OCR tier. |
| `xfa_partial` | warning | pdf | XFA form content was only partially extracted. | Print the form to PDF from Adobe Reader to flatten it, then convert that copy. |
| `iwork_preview_fallback` | warning | pdf | The iWork file was converted from its embedded preview, losing structure. | Export from Pages, Numbers or Keynote to DOCX, XLSX or PPTX and convert that. |
| `heading_inferred_from_formatting` | info | office | Headings were inferred from font size and weight, not styles. | Apply Heading styles in the source document for reliable structure. |
| `textbox_content_relocated` | info | office | Text box content was moved to the nearest paragraph position. | Check relocated text box content against the source layout. |
| `hidden_slides_included` | info | office | Hidden slides were included in the output. | Turn off hidden slide inclusion in the presentation options to omit them. |
| `hidden_sheets_included` | info | office | Hidden sheets were included in the output. | Turn off hidden sheet inclusion in the spreadsheet options to omit them. |
| `hidden_sheets` | info | office | The workbook has hidden sheets; they are included and marked (hidden). | Delete or unhide sheets in the source if the hidden ones should not be shared. |
| `formula_uncalculated` | warning | office | Formula cells have no cached values and are shown blank or as formulas. | Open and save the workbook in Excel or LibreOffice to compute values, then reconvert. |
| `formulas_present` | info | office | The workbook contains formulas; values and formulas are both recorded. | Set formulas=false in options if you only want computed values. |
| `cell_errors` | warning | office | Some cells contain errors such as #REF! or #DIV/0!. | Fix the errors in the source workbook; error cells are kept as-is. |
| `possible_serial_dates` | info | office | Numeric cells look like unformatted date serial numbers. | Apply a date format to those cells in the source workbook. |
| `ragged_rows` | warning | office | Rows have inconsistent column counts and were padded. | Check the source for missing delimiters or stray cells. |
| `smartart_flattened` | info | office | SmartArt was flattened to a nested list of its text. | Check the source if the diagram's layout carries meaning. |
| `ole_object_skipped` | warning | office | An embedded OLE object could not be converted and was skipped. | Extract the embedded object from the source and convert it separately. |
| `legacy_text_only` | warning | office | A legacy binary format was converted as plain text, losing structure. | Save the file as DOCX, XLSX or PPTX and reconvert. |
| `libreoffice_missing` | warning | office | LibreOffice is not installed, so a lower-fidelity path was used. | Install LibreOffice so soffice is on PATH, then reconvert. |
| `pages_estimated` | info | office | Page numbers are estimated because the format has no fixed pages. | Cite by section heading rather than page number. |
| `equation_partial` | warning | office | Some equations were converted only partially. | Compare equations with the source; DOCX with native equations converts best. |
| `tracked_changes_present` | info | office | The document has tracked changes; they were accepted in the output. | Set track_changes=all to keep insertions and deletions as CriticMarkup. |
| `comments_present` | info | office | The document has reviewer comments that are not in the body. | Set track_changes=all to render comments inline at their anchors. |
| `private_link` | error | google | The Google link is not publicly accessible. | Share the file as 'Anyone with the link can view', or export it and upload the file. |
| `first_sheet_only` | warning | google | Only the first sheet of the Google Sheet was exported. | Download the spreadsheet as XLSX and upload it to convert every sheet. |
| `suggestions_not_exported` | info | google | Suggested edits in the Google Doc were not exported. | Download the doc as DOCX to keep suggestions as tracked changes, then convert that. |
| `epub_mimetype_missing` | info | ebooks | The EPUB lacks its mimetype entry; it was parsed anyway. | Re-export the EPUB with a compliant tool if other readers reject it. |
| `calibre_missing` | error | ebooks | Calibre is required for this ebook format and is not installed. | Install Calibre so ebook-convert is on PATH, or convert the book to EPUB first. |
| `drm_protected` | error | ebooks | The ebook is DRM-protected and cannot be read. | Use a DRM-free copy of the book. |
| `latex_main_ambiguous` | warning | ebooks | Several LaTeX files could be the main document; one was picked. | Name the main .tex file explicitly in the LaTeX options. |
| `latex_unknown_macro` | info | ebooks | Unknown LaTeX macros were kept verbatim. | Include the .sty or macro definitions in the upload so they can be expanded. |
| `notebook_invalid` | warning | ebooks | The notebook fails nbformat validation and was parsed best-effort. | Open and re-save the notebook in Jupyter to repair it. |
| `output_truncated` | info | ebooks | Long notebook cell outputs were truncated. | Raise the notebook output limit in options if you need full outputs. |
| `mdx_components_stripped` | info | ebooks | MDX components were removed, keeping their text children. | Convert the rendered HTML page instead if components carry essential content. |
| `table_inferred` | info | ebooks | A table was inferred from aligned plain text. | Check the inferred table against the source text. |
| `empty_body_js_required` | error | ebooks | The page body is empty without JavaScript rendering. | Enable the browser rendering engine, or convert the page with the browser extension. |
| `markup_partial` | warning | ebooks | Markup was only partially parsed; some constructs remain as raw text. | Check the raw spans, or convert from the original source format if available. |
| `robots_disallowed` | error | web | robots.txt disallows fetching this URL. | Save the page in your browser and upload it, or use the browser extension. |
| `http_error` | error | web | The server returned an HTTP error status. | Check the URL opens in a browser, then retry; the message has the status code. |
| `paywall_detected` | warning | web | A paywall was detected; only the free portion was converted. | Save the page from a logged-in browser and upload it, or use the browser extension. |
| `readability_fallback_full_body` | info | web | Main-content extraction failed, so the full page body was kept. | Expect navigation text; use the extension's selection mode to convert only the article. |
| `multipage_article` | info | web | The article spans multiple pages, which were joined. | Check the page joins, or pass the site's single-page or print URL. |
| `lazy_content_possible` | info | web | The page may load more content on scroll that was not captured. | Enable browser rendering, or convert with the extension after scrolling to the end. |
| `images_without_alt` | info | web | Some images have no alt text and are listed without description. | Enable image description or OCR if the images carry information. |
| `fetch_blocked` | error | web | The remote site blocked the fetch. | Download the content in your browser and upload it, or use the browser extension. |
| `fetch_failed` | error | web | The network fetch failed (DNS, TLS, connection or timeout). | Check the URL and that the site is up, then retry. |
| `llms_txt_used` | info | sites | The site's llms.txt was used to choose pages. | Pass a sitemap URL or explicit URL list to crawl a different set of pages. |
| `llms_txt_may_be_stale` | info | sites | llms.txt looks older than the site's content. | Crawl via the sitemap instead of llms.txt to get current pages. |
| `sitemap_truncated` | warning | sites | The sitemap had more URLs than the page limit; the rest were skipped. | Raise the site page limit, or narrow the crawl with an include pattern. |
| `versions_skipped` | info | sites | Older documentation versions were skipped. | Pass the versioned URL prefix to convert a specific version. |
| `boilerplate_removed_corpus` | info | sites | Navigation repeated across pages was removed corpus-wide. | Turn off corpus boilerplate removal in site options if you need that text. |
| `heading_depth_clamped` | info | sites | Heading levels were clamped when pages were combined. | Use per-page output to keep each page's original heading depth. |
| `combined_too_large` | warning | sites | The combined site output exceeds the size cap. | Use per-page output or the rag profile instead of one combined file. |
| `comments_truncated` | warning | social | Only part of the comment thread was fetched. | Raise the comment limit in options, or configure the platform API key. |
| `comments_collapsed` | info | social | Low-scored or deep comment branches were collapsed. | Raise the comment depth option to include collapsed branches. |
| `tos_risk_source` | warning | social | The source's terms of service restrict automated access. | Make sure your use complies with the platform's terms; prefer an official export. |
| `private_post` | error | social | The post is private or requires login. | Save the post from a logged-in browser and upload it, or use the browser extension. |
| `thread_partial_federation` | info | social | Some federated replies on other servers could not be fetched. | Open the thread on its home server to convert remote replies. |
| `api_fallback_html` | warning | social | The platform API was unavailable, so HTML scraping was used. | Configure the platform API credentials for complete, stable extraction. |
| `best_effort_extraction` | warning | social | Extraction relied on fragile heuristics; fields may be missing. | Verify key fields against the source, or use an official export. |
| `rate_limited` | error | social | The platform rate-limited the request. | Wait a few minutes and retry, or configure your own API credentials. |
| `secret_file_excluded` | info | code | Files that look like secrets (.env, private keys) were excluded. | No action needed; rename the file if it was wrongly detected as a secret. |
| `secret_redacted` | info | code | Values that look like secrets (keys, tokens) were redacted. | No action needed; rotate the secret if the source was shared anywhere. |
| `token_budget_applied` | warning | code | Repository output was trimmed to fit the token budget. | Raise max_tokens or narrow the include globs to the files you need. |
| `log_lines_collapsed` | info | code | Repeated log lines were collapsed with counts. | Turn off log collapsing in options if you need every line. |
| `log_truncated` | warning | code | The log was truncated to fit limits. | Filter the log by time range or level before converting. |
| `timezone_assumed` | info | code | Timestamps had no timezone, so UTC was assumed. | Pass the source timezone in options if the timestamps are local time. |
| `spec_invalid` | warning | code | The API spec fails schema validation and was rendered best-effort. | Validate the spec with an OpenAPI linter, fix the errors, and reconvert. |
| `env_values_redacted` | info | code | Values in environment files were redacted; only keys are kept. | No action needed; share values through a secret manager, not converted output. |
| `quoted_history_removed` | info | comms | Quoted reply history was removed from messages. | Turn off quoted-history stripping in email options to keep it. |
| `thread_reconstructed_from_text` | info | comms | Thread order was reconstructed from message text, not headers. | Export with full headers (EML or MBOX) for reliable threading. |
| `orphan_thread_replies` | warning | comms | Some replies reference parent messages that are missing. | Include the full export or channel history so parents can be matched. |
| `unresolved_users` | warning | comms | Some user IDs could not be resolved to names. | Include the export's users file (e.g. users.json) in the upload. |
| `attachment_skipped` | info | comms | An attachment was skipped by policy or type and is listed by name. | Extract the attachment and convert it separately if you need its content. |
| `attachment_failed` | warning | comms | An attachment failed to convert and is listed by name only. | Extract the attachment and convert it on its own to see the specific error. |
| `attachment_unconverted` | warning | comms | An attachment could not be converted and is listed by name only. | Extract the named attachment and convert it separately. |
| `tnef_unparsed` | warning | comms | A winmail.dat (TNEF) attachment could not be decoded. | Ask the sender to resend in plain or HTML format, or decode it with a TNEF tool. |
| `smime_not_decrypted` | warning | comms | An S/MIME encrypted message body could not be decrypted. | Decrypt the message in your mail client and export the decrypted copy. |
| `msg_partial` | warning | comms | The Outlook MSG file was parsed only partially. | Install the nonfree extra for full MSG support, or save the message as EML. |
| `date_order_assumed` | warning | comms | Ambiguous dates were parsed with an assumed day/month order. | Pass the date order (DMY or MDY) in options to match the export's locale. |
| `discord_package_no_authors` | info | comms | The Discord data package lacks names for other users. | Use a channel export tool that includes author names for full attribution. |
| `teams_html_best_effort` | warning | comms | The Teams HTML export was parsed best-effort. | Use a Teams JSON export (Purview or Graph) for reliable structure. |
| `json_repaired` | warning | data | Invalid JSON was repaired before parsing. | Fix the source JSON; repaired values may differ from what was intended. |
| `rows_sampled` | info | data | Only a sample of rows is shown; full data is in the CSV export. | Use the CSV export for every row. |
| `columns_truncated` | info | data | Wide data had columns truncated. | Select the columns you need in options, or use the CSV export. |
| `depth_truncated` | info | data | Nested data beyond the depth limit was truncated. | Raise the depth limit in data options. |
| `yaml_unsafe_tags` | warning | data | The YAML contains unsafe tags, which were not executed. | Remove language-specific tags such as !!python/object from the YAML. |
| `api_error_payload` | warning | data | The fetched JSON looks like an API error response. | Check the API URL, authentication and query parameters. |
| `sqlite_encrypted` | error | data | The SQLite database is encrypted. | Decrypt the database (e.g. with SQLCipher) and upload the plain copy. |
| `connection_string_refused` | error | data | Database connection strings are refused for safety. | Export the data to a file such as CSV or SQLite and upload that. |
| `unresolved_wikilinks` | info | notes | Some wikilinks point to notes not in the upload. | Upload the whole vault folder so links can resolve. |
| `ambiguous_wikilink` | info | notes | A wikilink matched more than one note; the first match was used. | Use full paths in wikilinks to disambiguate. |
| `missing_resource` | warning | notes | An embedded image or attachment was not found. | Include the attachments folder in the upload. |
| `encrypted_content` | info | notes | Encrypted content was skipped. | Decrypt the content in its source app and export it again. |
| `dates_from_filesystem` | info | notes | Note dates come from filesystem timestamps, which may be wrong. | Add created and updated dates to the notes' frontmatter. |
| `kindle_clip_limit` | warning | notes | Kindle highlights are cut off at the publisher's export limit. | Copy the full passage from the book itself; the export cannot recover it. |
| `clippings_deduped` | info | notes | Duplicate Kindle highlights were merged. | Check merged highlights if you edited a highlight and expected both versions. |
| `xbrl_statement_mismatch` | warning | specialized | XBRL facts disagree with the rendered statement. | Compare the flagged values with the filing's official XBRL viewer. |
| `ixt_format_unknown` | warning | specialized | Inline XBRL used an unknown transformation format. | Check the flagged facts by hand; upgrade intomd in case the format was added. |
| `reconciliation_failed` | error | specialized | Statement totals do not reconcile with the extracted rows. | Review the flagged page against the source; try a layout OCR engine for scans. |
| `amount_corrected_by_reconciliation` | warning | specialized | An amount was corrected so totals reconcile. | Verify the corrected amount against the source document. |
| `columns_swapped_by_reconciliation` | warning | specialized | Debit and credit columns were swapped so totals reconcile. | Verify the column assignment against the source document. |
| `duplicate_row_at_page_break` | info | specialized | A row repeated at a page break was removed. | Check the page break in the source if row counts look off. |
| `account_number_masked` | info | specialized | Account numbers were masked to their last digits. | No action needed; refer to the source document for full numbers. |
| `invoice_validation_failed` | warning | specialized | Invoice totals or required fields failed validation. | Check line items, tax and totals against the source invoice. |
| `word_index_dropped` | info | specialized | A back-of-book word index was dropped. | Convert the index pages separately if you need them. |
| `fulltext_unavailable` | warning | specialized | Full text was unavailable; only metadata or the abstract was converted. | Upload the full-text PDF, or use an open-access link. |
| `bibtex_duplicate_keys` | warning | specialized | The BibTeX file has duplicate citation keys. | Rename the duplicate keys in the .bib file. |
| `phi_refused` | error | specialized | The content appears to contain protected health information and was refused. | Self-host intomd to process health records under your own compliance controls. |
| `phi_possible` | warning | specialized | The content may contain protected health information. | Review and redact before sharing, and self-host for regulated data. |
| `music_summary_only` | info | specialized | The music file was summarized (tags, duration) without transcription. | Force transcription in the media options if the file contains speech. |
| `archive_encrypted` | warning | specialized | Encrypted archive entries could not be read. | Provide the archive password, or upload an unencrypted archive. |
| `archive_bomb_suspected` | error | specialized | The archive expands beyond safe limits and was refused. | Extract the files you need locally and upload them individually. |
| `archive_path_rejected` | warning | specialized | Archive entries with unsafe paths were rejected. | Repack the archive with relative paths and no symlinks. |
| `archive_truncated` | warning | specialized | Archive extraction stopped at the entry-count or expansion-ratio limit. | Upload fewer files per archive, or raise the archive limits when self-hosting. |
| `archive_entry_skipped` | warning | specialized | Archive entries with traversal paths, absolute paths or symlinks were skipped. | Repack the archive with plain relative paths and upload it again. |
| `asr_confidence_low` | warning | media | Speech recognition confidence was low; the transcript may contain errors. | Upload a cleaner recording, or retry with a larger ASR model. |
| `asr_hallucination_filtered` | info | media | Likely ASR hallucinations (text over silence or music) were removed. | Check the flagged timestamps against the audio if you need every word. |
| `deloop` | info | media | Repeated n-gram loops in ASR output were collapsed. | Check the marked segments against the audio; a larger model loops less. |
| `no_speech_detected` | warning | media | Almost no speech was detected, so the transcript is empty. | Check the file has an audio track with speech; set the language if it is quiet speech. |
| `language_uncertain` | warning | media | The language was detected with low confidence. | Pass --lang with the correct language code and reconvert. |
| `duration_limit_reached` | warning | media | The media duration limit was reached; later audio was not transcribed. | Trim the file into shorter parts, or self-host with a higher duration limit. |
| `duration_cap_exceeded` | warning | media | The audio exceeded this instance's duration cap; only the start was transcribed. | Split the audio into shorter parts, or self-host to remove the cap. |
| `diarization_skipped_cpu_budget` | warning | media | Speaker labels were skipped because the audio exceeds the CPU budget. | Force diarization in options, or run on a GPU or a hosted backend that includes it. |
| `diarization_skipped_short` | info | media | Speaker labels were skipped because the audio is very short. | No action needed; force diarization in options if the clip has several speakers. |
| `diarization_unavailable_offload` | warning | media | The hosted ASR backend has no diarization, so speaker labels are missing. | Use a local or diarizing backend (e.g. Deepgram), or upload a shorter clip that stays local. |
| `chapters_generated` | info | media | Chapters were generated automatically rather than taken from the source. | Check chapter boundaries and titles; add chapters at the source to use them instead. |
| `media_unavailable` | error | media | The media could not be downloaded; only metadata was converted. | Upload the media file directly, or use the browser extension or share sheet. |
| `captions_only` | info | media | The transcript comes from platform captions, not speech recognition. | Request ASR in options if the captions are poor or missing words. |
| `browser_asr_small_model` | warning | media | A small in-browser ASR model was used; expect more transcription errors. | Choose a larger browser model, or convert on the server for better accuracy. |
| `timestamps_approximate` | info | media | Timestamps are approximate rather than word-aligned. | Use server-side ASR with word timestamps if you need precise timing. |
| `profanity_masked` | info | media | Profanity in the transcript was masked. | Turn off profanity masking in the transcript options to keep the original words. |
| `fillers_removed` | info | media | Filler words (um, uh) were removed from the transcript. | Enable verbatim mode to keep filler words. |
| `verbatim_mode` | info | media | The transcript is verbatim, with fillers and false starts kept. | Turn off verbatim mode for a cleaner, more readable transcript. |
| `unreadable_region` | warning | ocr | A region of the page or image could not be read. | Upload a sharper, higher-resolution scan of the marked region. |
| `unreadable_regions` | warning | ocr | Several regions of the page or image could not be read. | Upload a sharper scan (300 DPI or more), or try a layout OCR engine. |
| `layout_ocr_unavailable_cpu` | warning | ocr | Layout-aware OCR needs a GPU; basic OCR was used on this CPU-only host. | Run on a host with a GPU, or install a CPU-capable layout model, for complex layouts. |
| `license_restricted_engine_used` | info | ocr | A license-restricted OCR engine (non-commercial or OpenRAIL) was used. | Check the engine license allows your use, or unset INTOMD_ALLOW_RESTRICTED_MODELS. |
| `receipt_totals_mismatch` | warning | ocr | Receipt line items, tax and total do not add up. | Check the flagged values against the receipt; rescan if digits are blurred. |
| `chat_screenshot_decorations_removed` | info | ocr | Chat app UI elements (status bar, buttons) were removed. | No action needed; crop the screenshot yourself if something was wrongly removed. |
| `table_structure_uncertain` | warning | render | Table structure was detected with low confidence; cells may be misaligned. | Check the table against the source, or try a layout-aware engine. |
| `merged_cells_flattened` | info | render | Merged table cells were flattened by repeating their value. | Use the full profile with merged_cells=html to keep spans as an HTML table. |
| `table_merged_cells_flattened` | info | render | Merged table cells were flattened for this profile. | Use the full profile with merged_cells=html to keep spans as an HTML table. |
| `table_sampled` | info | render | A very large table was sampled; full data is in the CSV export. | Use the table's CSV export for every row. |
| `equation_as_text` | info | render | An equation was kept as plain text instead of LaTeX. | Use an engine with formula recognition if you need LaTeX output. |
| `truncated` | warning | render | Output was truncated at the size cap. | Download the full result, or self-host with a higher output cap. |
| `truncated_max_tokens` | warning | render | Output was truncated at the requested max_tokens. | Raise max_tokens, or page through the result with the cursor. |
| `possible_prompt_injection` | warning | render | Text that looks like instructions aimed at an AI was found and kept. | Treat the flagged text as untrusted; review sidecar injection_findings first. |
| `injection_pattern` | warning | render | A known prompt-injection pattern was matched in the content. | Treat the content as untrusted and use the agent profile's fenced output. |
| `injection_flagged` | warning | render | Some text looks like instructions aimed at an AI; it was kept and flagged. | Review the flagged spans in the sidecar before passing the output to an AI. |
| `fetch_degraded` | warning | fetch | The fetch used a degraded path; content may be incomplete. | Retry later, or upload the file directly for complete content. |
| `fetched_partial` | warning | fetch | Only part of the remote content was fetched. | Retry, or download the content in your browser and upload it. |
| `fetch_blocked_by_platform` | error | fetch | The platform blocked the server's fetch. | Upload the file directly, or install the browser extension to fetch from your own connection. |
| `fetch_blocked_by_policy` | error | fetch | This source is disabled for direct fetch on this instance. | Use the browser extension or share sheet, or upload the file directly. |
| `fetch_refused_private_network` | error | fetch | The URL resolves to a private or local network address and was refused. | Use a public URL, or upload the file; self-host to convert intranet URLs. |
| `fetch_refused_scheme` | error | fetch | The URL scheme is not allowed; only http and https are fetched. | Use an http or https URL, or upload the file directly. |
| `url_blocked_by_policy` | error | fetch | The URL matches this instance's blocklist and was refused. | Upload the content as a file, or contact the instance operator if this is a mistake. |
