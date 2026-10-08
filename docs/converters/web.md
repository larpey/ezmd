# Web pages (`web` family)

Converts static HTML pages (`text/html`, `application/xhtml+xml`) to the IR. Spec: `docs/spec/part2.md`
section 5 (web/pages) and `docs/spec/part3.md` section 18 (prompt-injection handling). Site crawling
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
`<title>`/`<h1>`. Fields: title, author(s), published, modified, site_name, description, keywords (tags),
canonical_url, language (`<html lang>`, `language_source=declared`), encoding. The canonical URL becomes the
document source only when it is same-origin with the final URL; otherwise `extra.canonical_cross_origin` is set.
`extra.readability_ratio` is extracted characters over cleaned-page characters; `extra.outbound_pdfs` lists
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

## Warnings

| code | when |
|---|---|
| `removed_hidden_elements` | hidden elements or invisible characters were removed (info) |
| `injection_suspected` | the removed hidden text matches injection patterns |
| `engine_fallback` | Trafilatura under-extracted and the rule extractor was used |
| `readability_fallback_full_body` | no article was found, the full body was converted (always on `web.html_raw`) |
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
- CSS from external stylesheets is not evaluated, so text hidden only by an external stylesheet is kept;
  white text is removed only when its background is declared inline on it or an ancestor.
- Comment sections are always excluded (`include_comments` is not wired yet).
- `hr` is dropped rather than emitted as a `Raw("---")` block.
- readability-lxml is not used as a separate fallback; the rule extractor fills that slot.
- `amp-img` is handled; other AMP components are not.
