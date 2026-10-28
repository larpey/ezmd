# Benchmark baseline 2026-10-27-media-c

Hardware: AMD Ryzen 9 7900X 12-Core Processor, 24 logical cores, 95.1 GB RAM, GPU NVIDIA GeForce RTX 4090, 24564 MiB, 616.56, Windows 11 (10.0.26200).

Each cell: primary metric [95% CI] (n). fail = error/timeout/crash share of attempted documents; cov = attempted/total; s/doc = median and p95 wall seconds; RSS = median and peak over documents of the per-document peak MB (process tree plus any containers the tool starts, models loaded). Rows marked * are ezmd.

## What this run is

The whole `media` corpus as pulled by the evening of 2026-10-27: 20,348 files. Wikimedia Commons by `filemime`
search (PNG 5,512, SVG 3,777, WebP 3,060, TIFF 1,926, GIF 1,542, JPEG 1,396, DjVu 272; Ogg 295, MP3 277, MIDI
161, WAV 137, FLAC 111, WebM audio 100; WebM video 197), Project Gutenberg EPUB (998 of the seeded 1,000),
LibriVox MP3 chapters (300), NASA audio (125) and video (162). The pull was stopped and restarted once; PNG, SVG
and WebP are over the caps in `tools/bench/media.py` (3,000 each), and the restarted pull's log holds 1,949
duplicate records that the loader folds by (source, id). ezmd main at 2648184, four workers, 120-second limit;
outcome scored (`tools/bench/scoring/corpus.py`). `2026-10-26-media-b` was the first 7,138 Commons images of
this corpus (WebP, SVG, TIFF) on main at d078ebb.

## Results

Clean rate 1.0000 over 20,348 files: 4,774 outputs, 15,574 declared refusals, no bug. 3,654 seconds of
conversion, half an hour of wall time on four workers.

- **Every raster image, every audio file and every video is a declared refusal**, `no converter for <name>
  (mime=...)`, in 30 ms each: the media extra (transcription) and the image path (OCR, description) are not
  released, and the detector names the type correctly on the way out, including 40 NASA "m4a" files that are raw
  AAC streams (`audio/x-hx-aac-adts`) and one "djvu" that is an ACE archive. 55 NASA files, 107 MB to 828 MB,
  are refused as `InputTooLarge` at the 100 MB cap before any of that.
- **EPUB: 998 of 998 convert.** Median 0.9 seconds and 284 KB of markdown (65,000 o200k tokens); p95 4.7
  seconds; the slowest is the 97 MB first volume of *Principia Mathematica*, 644 pages and 672,000 tokens, in 69
  seconds. Reported smells, none gated: 28 `repeated_lines`, 12 `empty_table` (Gutenberg's illustration grids,
  whose header cells are empty), 2 `mojibake`, 1 `heading_bullet`; one `lone_bullet` is gated, so the gated-clean
  rate is 0.9998.
- **SVG is the finding of this run.** In media-b every SVG was a declared refusal. Since #39, the registry hands
  an unclaimed text-like type to the plain-text converter, and an SVG is text: 3,776 of 3,777 now convert "ok"
  through `text.plain` with the `unknown_type_read_as_text` warning, and the output is the escaped XML source.
  Median 35 KB (14,000 tokens) for a drawing whose readable content is a `title` and a few labels; 1,620 outputs
  over 100 KB, 130 over 1 MB, three county election maps and a heraldic template at 14 to 18 MB of path data in 27
  to 36 seconds each; 698 MB of markdown in all. The scorer has no smell for a source dumped as text, so the clean
  rate does not see it; the smells it does see are SVG's: 397 of the 425 `repeated_lines`, all 46 `char_run`. The
  one failure is the same file as in media-b, sniffed as XML and failed on its encoding declaration. Evidence
  filed on #55.
- **Injection, EPUB.** 12 of 998 novels score high, every one `role_hijack` on dialogue between characters:
  "you are now the head of the family", "you are now a soldier in the pick of that army", "Do you forget all your
  acquaintances so quickly, Baron?", "I shall never forget all your kindness", "from now on you will discontinue
  your active efforts", and one "act as assistant instructors" (the #54 shape). 27 medium, 28 low. Filed as #59:
  these patterns need the model as addressee, as #44 required of the heuristics.
- **Injection, SVG.** 31 medium and 1 high; the high is `delimiter_spoof` on Inkscape's own `<!-- Page: 1/1 -->`
  comment in the source, which the dump puts in the body where ezmd's marker regex finds it. A symptom of the
  SVG route, not a rule problem.

## What this says

- **The refusals are the right ones and cost nothing**: 15,574 files in 30 ms each, every type named. The corpus
  is ready for the media extra and the image path, and this run is the baseline they are measured against.
- **"Readable text is never refused" needs a list of exceptions.** #39 was right for SQL, DTDs and property
  lists and wrong for SVG, which is text that is not for reading. #55's small SVG converter (title, desc, text;
  no geometry) turns the median case into a few lines; until it exists, refusing `image/svg+xml` before the text
  fallback restores media-b.
- **A clean rate of 1.0 is not a quality number.** It counts outcomes; the SVG dump is an outcome. The smells
  caught it sideways (`repeated_lines`, `char_run`), which is the argument for reading the smell table every
  time and for a smell that measures markup density.
- **Fiction is the hardest corpus for role_hijack.** Novels are made of people telling each other who they now
  are and what to forget. 1.2% high on public-domain fiction is the number to bring down.

## media-clean

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main* | 1.000 [1.000, 1.000] | 20348 | 76.5% | 20348/20348 | 0.04 | 0.57 | 245 | 703 |

