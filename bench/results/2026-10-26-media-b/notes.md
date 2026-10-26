## What this run is

The `media` corpus as pulled on the afternoon of 2026-10-26: 7,138 Wikimedia Commons images by `filemime`
search, WebP (2,974), SVG (2,866) and TIFF (1,298), with the PNG, JPEG, GIF, DjVu, audio, video, Gutenberg,
LibriVox and NASA sets still downloading. ezmd main at d078ebb, four workers, 120-second limit; outcome scored
(`tools/bench/scoring/corpus.py`).

## Results

Clean rate 1.0000 over 7,138 files: no output, 7,138 declared refusals, no bug. 135 seconds in all.

Every image was refused with `no converter for <name> (mime=image/...)`: the expected outcome before Phase 2,
when OCR and image description arrive, and a clean one. One SVG was taken for XML and failed to parse
(`invalid XML: encoding`), which is the `+xml` routing question in reverse: once `application/*+xml` resolves
to the XML converter, `image/svg+xml` must not, or must go to a converter that reads an SVG's `title`,
`desc` and `text` elements rather than its geometry.

## What this says

- **The media types refuse cleanly today.** No crash and no timeout on 7,138 images of three formats; the
  corpus is ready for the Phase 2 image path, and this run is the baseline it will be measured against.
- **SVG needs a decision**: an image, an XML document, or a text-bearing drawing. The one parse failure says
  the current answer is accidental.
