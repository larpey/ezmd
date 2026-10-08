"""code.source_file: one source file as a heading plus one fenced code block (docs/spec/part2.md 8c steps 12-13).

Language comes from the file name, the detected mime (Magika label), or a shebang. Secrets are redacted before
the text enters the IR. Options (`--opt extra.<key>=...`): `signatures_only` (compressed mode, 8c step 7),
`outline` (symbol list; automatic above 500 lines).
"""

from __future__ import annotations

from pathlib import PurePosixPath

from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import (
    CodeBlock,
    Document,
    Heading,
    InlineSpan,
    ListBlock,
    ListItem,
    Metadata,
    Provenance,
    SourceType,
    Warning,
    WarningKind,
)
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.code.common import count_tokens, opt_bool, secret_warning
from intomd_converters.code.languages import CODE_MIMES, is_code_name, language_for, shebang
from intomd_converters.code.secrets import redact
from intomd_converters.code.signatures import outline, signatures
from intomd_converters.text.plain import decode_text_detailed

OUTLINE_AUTO_LINES = 500
_NUL = chr(0).encode()
_CODE_MIME_SET = frozenset(CODE_MIMES)


class SourceFileConverter:
    id = "code.source_file"
    family = "code"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = CODE_MIMES

    def can_handle(self, ref: InputRef) -> float:
        if not ref.has_body or ref.detected is None:
            return 0.0
        mime = ref.detected.mime
        if mime in _CODE_MIME_SET:
            return 1.0
        if mime.startswith("text/") and mime != "text/markdown" and is_code_name(ref.display):
            # Above text.plain's 0.9 so a .go/.rs/.kt file Magika calls text/plain is packed as code.
            return 0.95
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raw = ref.read()
        source = ref.display
        name = PurePosixPath(source.replace("\\", "/")).name or source
        mime = ref.detected.mime if ref.detected else None
        meta = Metadata(source=source, source_type=SourceType.CODE, mime=mime, title=name)
        doc = Document(metadata=meta)
        if not raw.strip():
            doc.warnings.append(
                Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="The file contains no code.")
            )
            return doc.finalize()
        if _NUL in raw[:8192] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise ConversionError("input looks binary", user_message="This file does not look like source code.")
        text, encoding, uncertain, confidence = decode_text_detailed(raw)
        stats = CleanStats()
        text = clean_text(text, stats).rstrip("\n")
        meta.encoding, meta.encoding_confidence = encoding, confidence
        if uncertain:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.ENCODING_UNCERTAIN,
                    message=f"Text encoding was detected as {encoding}; some characters may be wrong.",
                    detail={"encoding": encoding},
                )
            )
        text, found = redact(text, name)
        language = language_for(name, text, mime)
        n_lines = text.count("\n") + 1
        compressed = opt_bool(options, "signatures_only", False) or opt_bool(options, "compress", False)
        body = signatures(text, language) if compressed else text
        tokens = count_tokens(body)
        interp = shebang(text)
        meta.extra.update({"language": language, "lines": n_lines, "bytes": len(raw), "tokens": tokens})
        if interp:
            meta.extra["shebang"] = interp
        title = f"{name} (signatures only)" if compressed else name
        meta.title = title
        prov = Provenance(source=source, path=name, line_start=1, line_end=n_lines)
        doc.blocks.append(Heading(level=1, spans=[InlineSpan(text=title)], provenance=prov))
        if opt_bool(options, "outline", n_lines > OUTLINE_AUTO_LINES):
            syms = outline(text, language)
            if syms:
                items = [
                    ListItem(
                        spans=[InlineSpan(text=f"{s.name} ({s.kind}) line {s.line}")],
                        provenance=Provenance(source=source, path=name, line_start=s.line, line_end=s.line),
                    )
                    for s in syms
                ]
                doc.blocks.append(ListBlock(items=items, provenance=prov.model_copy()))
        doc.blocks.append(
            CodeBlock(
                code=body,
                language=language,
                filename=name,
                provenance=prov.model_copy(),
                attrs={"tokens": str(tokens), "lines": str(n_lines), **({"compressed": "true"} if compressed else {})},
            )
        )
        warning = secret_warning(found)
        if warning is not None:
            doc.warnings.append(warning)
        if stats.total:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                    severity="info",
                    message=f"Removed {stats.total} control or invisible characters (possible Trojan Source).",
                    count=stats.total,
                )
            )
        return doc.finalize()
