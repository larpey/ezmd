"""intomd.library: the public Python API (docs/spec/part4.md section 4.3).

The library is the product; the CLI, the API worker, and the MCP server wrap it. Everything here is
thin over `intomd.pipeline.convert_ref` and `intomd.render.render`, so there is exactly one conversion
path. Importing this module (and `intomd`) never imports heavy engines; families load them lazily.
"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel, ConfigDict, Field

from intomd.inputs import InputRef
from intomd.ir import ConversionResult, Document, Warning
from intomd.pipeline import convert_ref
from intomd.registry import Converter, ConvertOptions, default_registry

__all__ = [
    "Options",
    "Progress",
    "Result",
    "Source",
    "capabilities",
    "convert",
    "convert_async",
    "convert_many",
    "register_converter",
    "unload_models",
]

Source = str | Path | bytes | IO[bytes] | InputRef
"""A filesystem path (str or Path), an http(s) URL (str), raw bytes, a binary file object, or an InputRef."""


@dataclass(frozen=True, slots=True)
class Progress:
    """One progress event. Stage names match the API's SSE `progress` events."""

    stage: str
    progress: float | None
    message: str
    detail: dict[str, object] = field(default_factory=dict)


class Options(BaseModel):
    """Conversion options. Field names mirror `POST /v1/convert` `options` so a request body round-trips
    (`Options(**request_json["options"])`). Dotted keys such as `chunks.chunk_tokens` are profile overrides
    and go in `render`."""

    model_config = ConfigDict(extra="forbid")

    max_pages: int | None = Field(default=500, ge=1)
    max_duration_seconds: float | None = Field(default=3 * 3600, gt=0)
    max_seconds: float = Field(default=600.0, gt=0)
    max_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    ocr: bool = True
    asr_model: str | None = None
    diarize: bool = True
    languages: list[str] = Field(default_factory=list)
    extract_images: bool = True
    tracked_changes: bool = True
    comments: bool = True
    formulas: bool = True
    experimental: bool = True
    converter: str | None = None
    """Force a converter id instead of automatic resolution."""
    allow_private_networks: bool = False
    """Allow URL fetches to private/loopback addresses (intranet use). Off by default (SSRF guard)."""
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)
    render: dict[str, object] = Field(default_factory=dict)
    """Profile overrides applied when rendering, e.g. {"chunks.chunk_tokens": 512}."""

    def to_convert_options(self, on_progress: Callable[[Progress], None] | None = None) -> ConvertOptions:
        opts = ConvertOptions(
            max_pages=self.max_pages,
            max_duration_seconds=self.max_duration_seconds,
            max_seconds=self.max_seconds,
            ocr=self.ocr,
            asr_model=self.asr_model,
            diarize=self.diarize,
            languages=list(self.languages),
            extract_images=self.extract_images,
            tracked_changes=self.tracked_changes,
            comments=self.comments,
            formulas=self.formulas,
            experimental=self.experimental,
            extra=dict(self.extra),
        )
        if on_progress is not None:
            callback = on_progress

            def relay(stage: str, fraction: float | None, message: str) -> None:
                callback(Progress(stage=stage, progress=fraction, message=message))

            opts.ctx.on_progress = relay
        return opts


class Result:
    """A conversion result that keeps the intermediate representation, so other profiles render without
    re-converting (`result.render("compact")` equals converting with `compact` directly)."""

    def __init__(self, conversion: ConversionResult, *, profile: str = "full", render: dict[str, object] | None = None):
        self.conversion = conversion
        self.profile = profile
        self._overrides = dict(render or {})
        self._cache: dict[str, Any] = {}

    def render(self, profile: str | None = None, format: str = "md", **overrides: object) -> Any:
        """Render another profile or format from the retained IR. Returns `intomd.render.RenderedOutput`."""
        from intomd.render import render

        merged = {**self._overrides, **overrides} if profile in (None, self.profile) else dict(overrides)
        key = json.dumps([profile or self.profile, format, sorted((k, repr(v)) for k, v in merged.items())])
        if key not in self._cache:
            self._cache[key] = render(self.conversion, profile or self.profile, format, **merged)
        return self._cache[key]

    @property
    def markdown(self) -> str:
        """The full Markdown output: frontmatter plus body."""
        return str(self.render().markdown)

    @property
    def body(self) -> str:
        return str(self.render().body)

    @property
    def frontmatter(self) -> dict[str, object]:
        return dict(self.render().frontmatter)

    @property
    def sidecar(self) -> dict[str, object] | None:
        sc = self.render().sidecar
        return dict(sc) if sc is not None else None

    @property
    def warnings(self) -> list[Warning]:
        return list(self.render().warnings)

    @property
    def tokens(self) -> int:
        return int(self.render().tokens)

    @property
    def truncated(self) -> bool:
        return bool(self.render().truncated)

    @property
    def document(self) -> Document:
        return self.conversion.document

    @property
    def ok(self) -> bool:
        """False when any error-severity warning is present (the output may still be usable)."""
        return not any(w.severity == "error" for w in self.warnings)

    def chunks(self, chunk_tokens: int = 400, overlap: int = 0) -> list[Any]:
        """RAG chunks (`intomd.render.Chunk`) using the `rag` profile."""
        out = self.render("rag", **{"chunks.chunk_tokens": chunk_tokens, "chunks.overlap_tokens": overlap})
        return list(out.chunks)

    def save(self, path: str | Path, *, sidecar: bool = True) -> Path:
        """Write the Markdown to `path` (a file, or a directory to write `<stem>.md` into) and, when
        `sidecar` is true and the profile has one, `<stem>.intomd.json` beside it. Returns the .md path."""
        target = Path(path)
        if target.is_dir():
            stem = Path(self.conversion.input_ref.display.split("?", 1)[0].rstrip("/")).stem or "output"
            target = target / f"{stem}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.markdown, encoding="utf-8", newline="\n")
        sc = self.sidecar
        if sidecar and sc is not None:
            side = target.with_name(target.stem + ".intomd.json")
            side.write_text(json.dumps(sc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return target

    def __repr__(self) -> str:
        return f"<intomd.Result {self.conversion.converter_id} {self.conversion.input_ref.display!r}>"


def _ref(source: Source, *, filename: str | None, opts: Options) -> InputRef:
    if isinstance(source, InputRef):
        return source
    if isinstance(source, bytes):
        return InputRef.from_bytes(source, filename=filename or "input", max_bytes=opts.max_bytes)
    if isinstance(source, (io.IOBase, io.BufferedIOBase)) or hasattr(source, "read"):
        data = source.read(opts.max_bytes + 1)  # type: ignore[union-attr]
        if not isinstance(data, bytes):
            raise TypeError("file objects must be opened in binary mode")
        return InputRef.from_bytes(data, filename=filename or "input", max_bytes=opts.max_bytes)
    text = str(source)
    if isinstance(source, str) and text.startswith(("http://", "https://")):
        from intomd.core.netguard import fetch

        res = fetch(text, max_bytes=opts.max_bytes, allow_private=opts.allow_private_networks)
        name = filename or Path(res.url.split("?", 1)[0].rstrip("/")).name or "index"
        ref = InputRef.from_bytes(res.body, filename=name, declared_mime=res.content_type, max_bytes=opts.max_bytes)
        ref.kind = "url"
        ref.url = res.url
        ref.display = res.url
        return ref
    p = Path(text)
    if not p.is_file():
        raise FileNotFoundError(text)
    ref = InputRef.from_path(p, max_bytes=opts.max_bytes)
    if filename:
        ref.display = filename
    return ref


def _options(options: Options | dict[str, object] | None) -> Options:
    if options is None:
        return Options()
    if isinstance(options, Options):
        return options
    return Options(**options)


def convert(
    source: Source,
    *,
    profile: str = "full",
    options: Options | dict[str, object] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    filename: str | None = None,
    mime: str | None = None,
) -> Result:
    """Convert one source in-process: detect, route, (fetch), convert, and keep the IR for rendering.

    Raises `intomd.registry.ConversionError` (subclasses carry `.code` and `.user_message`),
    `intomd.inputs.InputTooLarge`, `intomd.core.netguard.NetguardError` for blocked URLs, and
    `FileNotFoundError` for missing paths.
    """
    opts = _options(options)
    ref = _ref(source, filename=filename, opts=opts)
    try:
        conversion = convert_ref(
            ref, opts.to_convert_options(on_progress), converter_id=opts.converter, mime_override=mime
        )
    finally:
        if not isinstance(source, InputRef):
            ref.cleanup()
    result = Result(conversion, profile=profile, render=opts.render)
    result.render()  # validate the profile and overrides now, not on first attribute access
    return result


async def convert_async(
    source: Source,
    *,
    profile: str = "full",
    options: Options | dict[str, object] | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    filename: str | None = None,
    mime: str | None = None,
) -> Result:
    """`convert` on a worker thread so an event loop (FastAPI, MCP) is never blocked."""
    return await asyncio.to_thread(
        convert, source, profile=profile, options=options, on_progress=on_progress, filename=filename, mime=mime
    )


def convert_many(
    sources: Iterable[Source], *, workers: int = 4, return_exceptions: bool = False, **kwargs: Any
) -> Iterator[Result | BaseException]:
    """Convert several sources concurrently, yielding results in input order. With `return_exceptions`,
    a failed source yields its exception instead of stopping the iteration."""

    def one(src: Source) -> Result | BaseException:
        try:
            return convert(src, **kwargs)
        except Exception as e:
            if return_exceptions:
                return e
            raise

    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="intomd-convert") as pool:
        yield from pool.map(one, sources)


def capabilities() -> dict[str, object]:
    """Registered converters (including unavailable ones with the reason), profiles, and formats."""
    from intomd import __version__

    rows = [
        {
            "id": r.converter.id,
            "family": r.converter.family,
            "mimes": list(getattr(r.converter, "mimes", ())),
            "source": r.source,
            "experimental": r.converter.experimental,
            "extras": list(r.converter.requires_extras),
            "loaded": r.import_error is None,
            "reason": r.import_error,
        }
        for r in default_registry().registrations()
    ]
    return {
        "version": __version__,
        "converters": rows,
        "profiles": ["full", "compact", "rag", "agent"],
        "formats": ["md", "json", "txt"],
    }


def register_converter(converter: Converter, *, source: str = "runtime") -> None:
    """Register a converter in the process-wide registry (for embedding and tests)."""
    default_registry().register(converter, source=source)


def unload_models() -> None:
    """Free cached engine models. Families with heavy engines expose an `unload()` hook."""
    try:
        import importlib

        import intomd_converters
    except ImportError:
        return
    for name in intomd_converters.family_names():
        mod = importlib.import_module(f"intomd_converters.{name}")
        hook = getattr(mod, "unload", None)
        if callable(hook):
            hook()
