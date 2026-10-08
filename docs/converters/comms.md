# Email converters (communication family)

Family id `comms` (docs/spec/part2.md section 9). This page covers the email part: EML, MBOX, and Outlook MSG.
Chat exports, ICS, and VCF are separate tasks.

| Converter | Inputs | Engine | Install |
|---|---|---|---|
| `comms.eml` | `.eml`, `message/rfc822`, `message/global`, text that starts with RFC 5322 headers | stdlib `email` (`policy.default`) | default |
| `comms.mbox` | `.mbox`, `.mbx`, any file that starts with a `From ` line followed by headers | stdlib `mailbox` | default |
| `comms.msg` | Outlook `.msg` (OLE2 with `__substg1.0_` streams) | native MS-OXMSG reader on olefile 0.47 (BSD-2-Clause) | default |
| `comms.msg_extract` | the same, second in the chain: runs only when the native reader fails | extract-msg 0.56 (GPL-3.0) | `pip install 'ezmd[nonfree]'`; listed as unavailable otherwise |

Gmail "Show original" / "Download message" gives an EML file; Gmail Takeout gives an MBOX.

The native MSG reader reads the subject, sender, recipients (`__recip_version1.0_#`, with To/Cc/Bcc from
`PR_RECIPIENT_TYPE`), dates, transport headers (0x007D, parsed as the real RFC 5322 headers), the text
(0x1000), HTML (0x1013), or compressed-RTF (0x1009) body, attachments (`__attach_version1.0_#`), and embedded
messages (`3701000D`). Compressed RTF is decompressed (MS-OXRTFCP, LZFu and stored) and HTML is
de-encapsulated when the RTF carries `\fromhtml1` (MS-OXRTFEX); other RTF is reduced to text with striprtf.
8-bit (`001E`) strings use the message code page (0x3FFD).

## Output

One message renders as:

1. H1 with the subject (`(no subject)` when empty).
2. A `Message headers` table: From, To, Cc, Bcc (when present, per spec 9c step 1), Date (ISO 8601 with offset),
   Subject, Message-ID, In-Reply-To, References, Reply-To, List-Id, and Gmail labels for Takeout mailboxes.
3. The body. Plain text keeps its line structure through the shared `text.lines` rule: in `format=flowed`
   text only lines ending in a space join (RFC 3676), and in other text a line joins the previous one only
   when that line is full width (60+ characters) or the line starts lowercase; list items and indented code
   never join. Lines that stay separate (signatures, addresses, `Thanks,` / `Ann`) render as hard line breaks
   inside one paragraph. With `body=auto` the HTML part wins when present. It goes through the web family's HTML-to-IR
   module in file mode (no article extraction), so lists, tables, quotes, and inline images stay. The plain
   part is the fallback. `metadata.extra.body_source` records which part was used, and
   `body_alternatives=true` means the plain part is under half the length of the HTML.
4. An `Attachments` heading and table (name, type, size, status) when the message has attachments. Converted
   attachments follow as child sections named `attachments/<name>`.

A mailbox gets an H1 per thread and an H2 per message (`From · Date`). Messages are in chronological order and
carry `attrs.depth`, the reply depth.

Quoted history and signatures are tagged with block `attrs.role`: `reply_header` (the `On ... wrote:` line),
`reply_history` (the quotes after it, Gmail `gmail_quote`, Apple `blockquote type=cite`, everything after an
Outlook `-----Original Message-----`), and `signature` (after `-- `, `Sent from my ...`, Gmail
`gmail_signature`). Quoted text that has no reply-header line is an ordinary quote, so `strip` never removes a
quoted contract clause.

Provenance: `source_id` = Message-ID, `path` = `headers`, `body`, or `attachments` (prefixed `messages/<n>/` in a
mailbox), and child blocks get `attachments/<n>`. The message heading carries `attrs.timestamp`. Every raw
header goes to the sidecar under `email_headers`.

## Options (`--opt extra.comms.<name>=...`)

| Option | Default | Meaning |
|---|---|---|
| `body` | `auto` | `auto`/`html` prefer HTML, `text` prefers the plain part |
| `strip_quotes` | `mark` | `mark` tags history, `strip` removes it (`quoted_history_removed`), `keep` leaves it untagged |
| `all_headers` | `false` | also render every header (Received chains, DKIM) in an `All headers` table |
| `attachments` | `convert` | `list` or `skip` list attachments without converting them (`attachment_skipped`) |
| `max_attachment_depth` | 3 | capped by `ConvertOptions.max_attachment_depth` |
| `max_attachment_bytes` | 100 MB | larger attachments are listed, not converted |
| `max_attachments` | 200 | attachments converted per message |
| `max_messages` | 5,000 | MBOX cap; also capped by `Limits.max_entries` |
| `max_header_chars` | 16,384 | longer header values are cut at an address or word boundary with an inline `… (N more recipients truncated)` marker, in the tables and the sidecar alike |
| `max_parts` | 1,000 | MIME parts walked per message |

## Warnings

| Code | When |
|---|---|
| `attachment_unconverted` | no converter handles the attachment's type, or it produced no content |
| `attachment_failed` | the attachment's converter failed, or the part is empty |
| `attachment_skipped` | too large, over the attachment cap, beyond the depth limit, attachments disabled, or `attachments=list/skip` |
| `tnef_unparsed` | a `winmail.dat` / `application/ms-tnef` part |
| `smime_not_decrypted` | an S/MIME `.p7m` part or an `IPM.Note.SMIME` Outlook message |
| `quoted_history_removed` | `strip_quotes=strip` removed history |
| `encoding_uncertain` | a body part's declared charset did not decode its bytes (`detail.reason=declared_charset_mismatch`), a body decoded with replacement characters, or an encoded word named an unknown charset (`unknown_header_charset`) |
| `removed_hidden_elements` | control, CR/LF, bidi, or invisible characters were removed from headers (`detail.where="headers"`) |
| `missing_resource` | a `cid:` image reference with no matching part |
| `truncated` | a header was cut, MIME nesting or part count exceeded, or the mailbox exceeded `max_messages` (`detail.reason`) |
| `size_cap` | the mailbox exceeded `Limits.max_bytes` |
| `msg_partial` | an Outlook attachment, property, or compressed-RTF body could not be read (or failed its CRC) |
| `other` | an MBOX member could not be parsed at all (skipped) |

## Security

- Header values are cut before the structured header parser sees them. MIME walking is bounded to 32 levels and
  1,000 parts. A `RecursionError` from the stdlib parser becomes a clean failure. Decoded header values have
  control characters (CR, LF, NUL) and bidi/invisible characters removed and whitespace collapsed, so an
  encoded word cannot smuggle a second header line.
- MSG: at most 1,000 recipients and attachments per message, property strings up to 16 MB, attachments over
  `max_attachment_bytes` are listed without being read, and compressed RTF expands to at most 64 MB whatever
  its header claims.
- Attachments convert through `ctx.convert_child`. They share the parent's deadline and are refused past
  `max_attachment_depth`. Attachment names are reduced to a cleaned basename, so `../../etc/passwd` becomes
  `passwd`, and nothing is written to disk except inline images when `image_dir` is set.
- No network access: remote images in HTML bodies are kept as links and never fetched.

## Known limitations

- TNEF (`winmail.dat`) is not decoded. The spec's `tnefparse` path is LGPL and needs an optional `tnef` extra
  that does not exist yet.
- The native MSG reader skips named properties (categories via `Keywords`, flag status). It reads
  importance but not the normalized subject (0x0E1D). Unicode (`001F`) and ANSI (`001E`) variants both work.
  RTF-only bodies that are not HTML-encapsulated lose formatting (text only).
- `threads=separate`, `label_filter`, pasted-text thread splitting (`thread_reconstructed_from_text`), and
  calendar parts sent to an ICS converter are not implemented. `text/calendar` parts convert like any other
  attachment.
- Outlook HTML history after an `-----Original Message-----` header is tagged block by block, not wrapped in
  one Quote.
- The renderer does not yet drop `reply_history` / `signature` blocks in the `compact` profile (core change
  request).
- Embedded Outlook messages are parsed in-process up to `max_attachment_depth` and rendered as child
  Documents. Their file attachments go through `convert_child` at the parent's depth plus one, so the depth
  limit for files inside a `.msg` inside a `.msg` is approximate.
- Mislabeled 8-bit bodies prefer Windows-1252 when charset-normalizer scores it within 0.1 chaos of its best
  guess (short Western-European bodies are otherwise often read as cp1257).
