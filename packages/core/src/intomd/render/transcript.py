"""intomd.render.transcript: TranscriptSegment runs to speaker paragraphs (docs/spec/part3.md section 16).

Segments merge into paragraphs until the speaker changes or the pause between segments exceeds
`paragraph_gap_seconds`. Each paragraph starts with the bold speaker label (repeated on every paragraph so
chunks stay self-describing) and an `[HH:MM:SS]` timestamp. A single unnamed speaker gets no label.
Non-speech segments become bracketed cues (`[pause]`, `[music]`), italic in `full`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from intomd.ir import Document, TranscriptSegment
from intomd.render.context import RenderContext, Unit
from intomd.render.text import clean_text, collapse_ws, escape_inline, fmt_time

__all__ = ["prepare_speakers", "render_transcript_run", "transcript_paragraphs"]

_DIARIZATION_LABEL = re.compile(r"^(speaker|spk|spkr)[ _-]?\d+$", re.I)
_CUES = {"silence": "[pause]", "music": "[music]", "noise": "[noise]"}


def prepare_speakers(ctx: RenderContext, doc: Document) -> None:
    order: list[str] = []
    for b in doc.blocks:
        if isinstance(b, TranscriptSegment) and b.kind == "speech" and b.speaker and b.speaker not in order:
            order.append(b.speaker)
    ctx.speaker_names = {
        sp: (f"Speaker {i}" if _DIARIZATION_LABEL.match(sp) else sp) for i, sp in enumerate(order, start=1)
    }
    named = [sp for sp in order if not _DIARIZATION_LABEL.match(sp)]
    ctx.show_speakers = len(order) > 1 or bool(named)


@dataclass(slots=True)
class _Para:
    speaker: str | None
    start: float
    end: float
    pieces: list[tuple[float, str]] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    words: list[dict[str, object]] = field(default_factory=list)
    on_screen: bool = False


def _cue(ctx: RenderContext, seg: TranscriptSegment) -> str:
    text = collapse_ws(clean_text(seg.text, ctx.stats)).strip()
    cue = text if text.startswith("[") and text.endswith("]") else _CUES.get(seg.kind, f"[{seg.kind}]")
    return f"*{cue}*" if ctx.profile.transcript.non_speech_italic else cue


def _speech_text(ctx: RenderContext, seg: TranscriptSegment) -> str:
    text = collapse_ws(clean_text(seg.text, ctx.stats)).strip()
    conf = seg.provenance.confidence
    if conf is not None and conf < 0.5 and len(text.split()) < 3:
        return "[inaudible]"
    return escape_inline(text)


def transcript_paragraphs(ctx: RenderContext, run: list[TranscriptSegment]) -> list[_Para]:
    rules = ctx.profile.transcript
    paras: list[_Para] = []
    cur: _Para | None = None
    for seg in run:
        if seg.kind == "slide_change":
            continue
        if seg.kind == "on_screen_text":
            text = collapse_ws(clean_text(seg.text, ctx.stats)).strip()
            if len(text) > 500:
                text = text[:497] + "..."
            paras.append(
                _Para(
                    None,
                    seg.start,
                    seg.end,
                    [(seg.start, f"[On screen: {escape_inline(text)}]")],
                    [seg.id],
                    on_screen=True,
                )
            )
            cur = None
            continue
        is_cue = seg.kind != "speech"
        if is_cue and not rules.non_speech_cues:
            continue
        piece = _cue(ctx, seg) if is_cue else _speech_text(ctx, seg)
        if not piece:
            continue
        speaker = seg.speaker if (seg.speaker and not is_cue) else (cur.speaker if cur else seg.speaker)
        new = cur is None or (
            not is_cue and (speaker != cur.speaker or seg.start - cur.end > rules.paragraph_gap_seconds)
        )
        if new or cur is None:
            cur = _Para(speaker, seg.start, seg.end)
            paras.append(cur)
        cur.pieces.append((seg.start, piece))
        cur.ids.append(seg.id)
        cur.end = max(cur.end, seg.end)
        if seg.provenance.confidence is not None:
            cur.confidences.append(seg.provenance.confidence)
        if seg.words:
            cur.words.extend({"w": w, "s": s, "e": e} for w, s, e in seg.words)
    return paras


def _para_text(ctx: RenderContext, para: _Para) -> str:
    rules = ctx.profile.transcript
    if para.on_screen:
        return para.pieces[0][1]
    if rules.timestamps == "sentence":
        body = " ".join(f"[{fmt_time(t)}] {p}" if i else p for i, (t, p) in enumerate(para.pieces))
    else:
        body = " ".join(p for _, p in para.pieces)
    stamp = f"[{fmt_time(para.start)}]" if rules.timestamps != "none" else ""
    if rules.confidence_marks and para.confidences and sum(para.confidences) / len(para.confidences) < 0.5:
        stamp = f"{stamp} (?)".strip()
    if ctx.show_speakers:
        name = ctx.speaker_names.get(para.speaker or "", para.speaker or "Unknown speaker")
        label = f"**{escape_inline(name)}**" + (f" {stamp}" if stamp else "")
        return f"{label}: {body}"
    return f"{stamp} {body}" if stamp else body


def render_transcript_run(ctx: RenderContext, run: list[TranscriptSegment]) -> list[Unit]:
    units: list[Unit] = []
    for i, para in enumerate(transcript_paragraphs(ctx, run)):
        entry: dict[str, object] = {
            "id": f"{run[0].id}-p{i + 1}",
            "speaker": ctx.speaker_names.get(para.speaker or "", para.speaker),
            "start": para.start,
            "end": para.end,
            "text": " ".join(p for _, p in para.pieces),
            "confidence": round(sum(para.confidences) / len(para.confidences), 3) if para.confidences else None,
            "block_ids": list(para.ids),
        }
        if ctx.profile.name == "full" and para.words:
            entry["words"] = para.words
        key = ("segments", ctx.side("segments", entry))
        units.append(
            Unit(
                text=_para_text(ctx, para),
                kind="transcript",
                block_ids=list(para.ids),
                time_start=para.start,
                time_end=para.end,
                sidecar_key=key,
            )
        )
    return units
