# Web pages (`web` family)

Converts static HTML pages (`text/html`, `application/xhtml+xml`) to the IR. Spec: `docs/internal/spec/part2.md`
section 5 (web/pages) and `docs/internal/spec/part3.md` section 18 (prompt-injection handling). Site crawling
(section 6) and JavaScript rendering (Crawl4AI) are Phase 3 and not part of this family yet.

The converters never fetch anything. They read the body they are given; `ref.url` (the final URL after
redirects, set by the fetcher or by a fixture's `[input] url`) is used to resolve relative links and as the
document source.

## Converters

| id | engine | default chain position | notes |
|---|---|---|---|
| `web.trafilatura` | Trafilatura 2.3 (Apache-2.0) chooses the article; each kept block is rebuilt from the matching DOM element | 1 | falls back to the rule extractor when Trafilatura returns under 200 characters or under 25 percent of the page text, unless it kept 90 percent of the page (`engine_fallback` with `detail.reason`); restores lazy-loaded images Trafilatura drops, and to the full body when no paragraph survives |
| `web.rules` | Defuddle-style rules in Python (no Node, nothing vendored) | 2 | removes nav, header/footer chrome, aside, forms, dialogs, ARIA landmarks (navigation, banner, contentinfo, complementary, search), cookie/consent banners, share/social widgets, newsletter boxes, related posts, comments, breadcrumbs, ads; then picks `<article>`, `<main>`, `[role=main]`, a known content class, or the densest block |
| `web.html_raw` | whole `<body>` | 3 | removes only structural boilerplate (tags, landmark roles, cookie banners); always warns `readability_fallback_full_body` |

All three share the same decoding, hygiene pass, metadata extraction, and HTML-to-IR module.

## What is kept

- Headings (levels normalized: when the page uses `<h1>` for every section, the title H1 stays and the rest
  shift down one level), paragraphs with bold/italic/code/strike/underline/sup/sub and inline links.
- Links are absolute: resolved against `<base href>` or the final URL; `javascript:` links become text;
  `mailto:` links are kept (the renderer prints them as text). In the `compact` profile the renderer turns
  inline links into a numbered `## Links` list; the sidecar `links` array is the deduplicated link list.
- Nested lists (ordered/unordered, `start`, mixed nesting), code blocks with the language from
  `class="language-x"`/`lang-x`, `data-lang`, highlight.js classes, or a wrapper class such as
  `highlight-python`; line-number gutters are stripped.
- Tables with `rowspan`/`colspan`, header rows (`thead` or all-`th` rows), and `caption`. Layout tables (no
  header cells and a single column, block content in every cell, or `role=presentation`) are unwrapped.
- Figures (`Figure` with the image and a caption paragraph), images as `Image` blocks with absolute URLs; the
  largest `srcset`/`<picture>` candidate wins; lazy-load attributes (`data-src`, `data-srcset`, ...) replace
  placeholder `src` values. Images with no alt and no caption get alt `image`.
- Blockquotes (paragraphs separated, `footer`/`cite` as attribution), definition lists (a `ListBlock` with `attrs.kind=definition`: terms as items, definitions as children),
  `details`/`summary` (summary becomes a heading one level below the current section), KaTeX/MathJax/MathML
  math (`Equation` or inline math from the TeX annotation, `data-latex`, or `script[type=math/tex]`),
  footnotes (`role=doc-noteref`, `rel=footnote`, `#fn` links and `doc-endnotes`/`.footnotes` sections), and
  YouTube/Vimeo iframes as `Link` blocks.
- Every block carries `Provenance.path`, a CSS-ish locator such as `body > main > article > p:nth-of-type(3)`
  (`article#<n>` for the rare Trafilatura block that cannot be matched back into the DOM).

## Metadata

Precedence: JSON-LD `Article`/`NewsArticle`/`BlogPosting` > `citation_*` > OpenGraph/Twitter > Trafilatura >
`<title>`/`<h1>`. For the title, a JSON-LD `headline` (or `name`) counts only when it agrees with another title
on the page (OpenGraph, Twitter, `<title>` or `<h1>`), so Wikipedia's short-description `headline` is skipped,
and OpenGraph/Twitter titles lose a trailing site name ("Albert Einstein - Wikipedia"). Fields: title, author(s), published, modified, site_name, description, keywords (tags),
canonical_url, language (`<html lang>`, `language_source=declared`), encoding. The canonical URL becomes the
document source only when it is same-origin with the final URL; otherwise `extra.canonical_cross_origin` is set.
`extra.readability_ratio` is extracted characters over cleaned-page characters (the cleaned page has already lost
whatever the class and id rules removed, so `extraction_dropped_text` is the loss measure, not this ratio); `extra.outbound_pdfs` lists
linked PDFs (not fetched); `extra.next_page` records `rel=next`.

## Hidden content and prompt injection

Before extraction the hygiene pass removes what a reader cannot see and never rewrites visible text:
HTML comments, `<noscript>`, `<template>`, `hidden`, `aria-hidden="true"`, inline `display:none`,
`visibility:hidden`, `opacity:0`, zero font size or zero height with overflow hidden, off-screen positioning
(`left`/`top`/`text-indent` at -999 px or beyond, clip rectangles), text colored like its declared background or
transparent, hidden class/id patterns (`hidden`, `d-none`, `sr-only`, `visually-hidden`, ...), classes and ids
hidden by simple rules in the page's own `<style>`, and 1 px tracking images. Zero-width, bidi-control and Unicode
tag characters are stripped from text nodes.

- `removed_hidden_elements` (count = elements with text) carries `detail.type.<kind>` counts and
  `detail.hidden_text` (capped at 10 KB) so nothing disappears silently.
- A second `removed_hidden_elements` warning counts removed invisible characters.
- The hidden text is scanned with the core injection scanner; a medium or high result adds
  `injection_suspected` with `detail.location = "hidden"`. Visible text that looks like an injection stays
  verbatim in the body and is flagged by the renderer's scanner as usual.

## Collapsed panels

An accordion answer is hidden in the saved HTML but a reader opens it with one click, so it is content. Text with no
way in stays removed. A panel is kept only when all of these hold:

- a control points at it: `aria-controls` on the control, `aria-labelledby` on the panel, or the control is the
  element right before it (and names no other panel);
- the control says `aria-expanded="false"`, is a `<button>`, `<a>` or `role="button"`, has a label, and neither it nor
  an ancestor is hidden;
- the panel is shut by the `hidden` attribute, `display:none` or a page rule, and by nothing else: `aria-hidden`,
  hidden classes, opacity, zero size, off-screen positioning and same-color text stay removed;
- under half its text is links (a dropdown menu is not a panel), and the injection scanner rates it below medium.

Hidden elements inside a kept panel are removed as usual. The control's label stays as plain text, in place in a
heading. Kept panel text is also added to the hidden text, so the scanner scores it as it did when it was removed.
`extra.collapsed_panels` counts the panels. Tabs (`aria-selected`) are not panels and stay removed.

## Section anchors

Class and id patterns tell a widget from content, but sites generate ids from headings, so
`<section id="how-we-share-this-log">` holds the word `share` for the same reason its heading does. Both the rule
extractor's patterns and Trafilatura's discard rules (which match substrings of ids: `share`, `social`, `cookie`,
`author`, `nav`) would remove it. An id is ignored as evidence when it is a run of the words of the heading that
opens the element, the element is not mostly links, and it sits among siblings that form an outline: at least
three of them have ids free of the pattern vocabulary, and those outnumber the rest. The rule extractor skips such
ids; Trafilatura gets a copy of the tree without them. Classes still count, and ids in the output are untouched.

## Warnings

| code | when |
|---|---|
| `removed_hidden_elements` | hidden elements or invisible characters were removed (info) |
| `injection_suspected` | the removed hidden text matches injection patterns |
| `engine_fallback` | Trafilatura under-extracted, or left out 5 percent of the page text that the rule extractor keeps at least half of (`detail.dropped_chars`, `detail.rules_dropped_chars`), and the rule extractor was used |
| `readability_fallback_full_body` | no article was found, the full body was converted (always on `web.html_raw`) |
| `extraction_dropped_text` | a headed section lost at least 200 characters and over half its text, or at least 200 characters and 5 percent of the page are gone; the page here is the body with only structural boilerplate removed (what `web.html_raw` keeps), blocks are matched by word shingles, and blocks that are mostly links or under five words are not counted. `detail` has `page_chars`, `dropped_chars` and `sections` (up to 12 headings). Not raised on `web.html_raw` or after the full-body fallback |
| `paywall_detected` | JSON-LD `isAccessibleForFree: false`, paywall selectors, or wall phrasing, and under 600 extracted characters; short subscribe/sign-in prompts inside paywall-marked elements are removed from the body (`detail.wall_prompts_removed`) |
| `empty_body_js_required` | the static HTML is a JavaScript shell (empty `#root`/`#app`/`#__next`, or over 50 KB of inline script) with under 300 characters of text; the body is a stub note |
| `lazy_content_possible` | lazy-loaded images were resolved from `data-*` attributes, or an infinite-scroll marker exists |
| `images_without_alt` | images without alt text or caption were labeled `image` |
| `multipage_article` | `rel="next"` or "Page N of M" text; the next page is recorded, not fetched |
| `size_cap` | the HTML exceeded the byte cap (50 MB local) and was truncated on a tag boundary |
| `extraction_empty` | nothing could be extracted (stub note) |

## Options

None yet beyond the shared `ConvertOptions`; choose the engine with `--converter web.rules` or
`--converter web.html_raw`. The `options.web.*` model from the spec (render, robots, user agent, images,
comments) belongs with the fetcher and the Phase 3 renderer.

## Known limitations

- No language detection beyond `<html lang>`/`og:locale` (lingua is not a dependency yet).
- No JavaScript rendering: SPA shells produce the `empty_body_js_required` stub (Phase 3, Crawl4AI extra).
- `<style>` rules are read without the cascade: a rule inside `@media` counts as unconditional, and a later rule
  that shows the element again is ignored.
- CSS from external stylesheets is not evaluated, so text hidden only by an external stylesheet is kept;
  white text is removed only when its background is declared inline on it or an ancestor.
- Comment sections are always excluded (`include_comments` is not wired yet).
- A section that takes no outline exemption (the only anchored section on the page, or an id that adds words its
  heading lacks, such as a `p-` prefix) is still removed by the patterns; `extraction_dropped_text` reports it. A
  comment section whose id repeats its heading, beside three or more plainly anchored sections, is kept.
- `extraction_dropped_text` counts text once: a block repeated verbatim elsewhere on the page reads as kept. Prose
  that extraction removes on purpose (a long author bio, a browser-upgrade notice) can raise it.
- `hr` is dropped rather than emitted as a `Raw("---")` block.
- readability-lxml is not used as a separate fallback; the rule extractor fills that slot.
- `amp-img` is handled; other AMP components are not.
- Layout-table pages (5e item 11) on the Trafilatura path: Trafilatura's flattened tables are split into
  pieces, anchored back into the DOM by text, and emitted in source order; pieces in layout cells outside the
  content cell (the cell holding most of the anchored text) are dropped as chrome when the cell has under 200
  characters or is mostly links. A longer non-content cell (a sidebar with real prose) is kept, and a piece
  whose text cannot be found in the DOM keeps the position of the block before it. Visual-only headings
  (`<font size=4><b>`) stay bold paragraphs, not headings.
- A one-row table without header cells is data unless it has a layout signal (one filled cell, an image,
  block content); a sparse table (at most one value per row) is data unless it carries such signals. One
  column without header cells is always treated as layout.
