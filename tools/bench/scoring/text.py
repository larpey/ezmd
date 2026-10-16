"""Output normalization shared by the scorers."""

from __future__ import annotations

import html
import re
from pathlib import Path

from markdown_it import MarkdownIt

from tools.bench.schema import DocResult


def strip_frontmatter(md: str) -> str:
    """Remove one leading YAML frontmatter block (`---` ... `---`)."""
    text = md.lstrip("\ufeff")
    if text.startswith("---\n") or text.startswith("---\r\n"):
        lines = text.splitlines(keepends=True)
        for i in range(1, len(lines)):
            if lines[i].rstrip("\r\n") in ("---", "..."):
                return "".join(lines[i + 1 :]).lstrip("\r\n")
    return text


def read_output(result: DocResult, run_dir: Path) -> str:
    """The tool's Markdown for an ok result (frontmatter removed), else ""."""
    if result.status != "ok" or not result.output:
        return ""
    return strip_frontmatter((run_dir / result.output).read_text(encoding="utf-8", errors="replace"))


_MD = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
_TAG = re.compile(r"<[^>]+>")
_CELL_END = re.compile(r"</t[dh]>|<br\s*/?>", re.I)
_ROW_END = re.compile(r"</tr>|</p>|</div>|</li>|</h[1-6]>", re.I)


def html_to_text(fragment: str) -> str:
    """Text of an HTML fragment (raw HTML blocks some tools emit for tables): cells space-separated."""
    t = _ROW_END.sub("\n", _CELL_END.sub(" ", fragment))
    return html.unescape(_TAG.sub("", t)).strip()


def markdown_to_text(md: str) -> str:
    """Plain text of a Markdown document: block texts separated by blank lines, markup removed."""
    blocks: list[str] = []
    for tok in _MD.parse(md):
        if tok.type == "inline":
            parts = []
            for child in tok.children or []:
                if child.type in ("text", "code_inline"):
                    parts.append(child.content)
                elif child.type in ("softbreak", "hardbreak") or (
                    child.type == "html_inline" and child.content.lower().startswith("<br")
                ):
                    parts.append("\n")
            text = "".join(parts).strip()
            if text:
                blocks.append(text)
        elif tok.type in ("fence", "code_block") and tok.content.strip():
            blocks.append(tok.content.strip())
        elif tok.type == "html_block":
            text = html_to_text(tok.content)
            if text:
                blocks.append(text)
    return "\n\n".join(blocks)
