# P1-T02 decisions: web/pages converter family

## P1-T02-a: Approach note (spec part1 2.5)
Date: 2026-10-08
Task: P1-T02
Status: proposed (folded into DECISIONS.md at merge)

- Library: Trafilatura 2.3.1, Apache-2.0, verified against the LICENSE file in the adbar/trafilatura
  repository (Apache License 2.0 text). Entry point: `trafilatura.extract(tree, output_format="xml",
  include_tables=True, include_images=True, include_links=True, include_formatting=True,
  include_comments=False, favor_precision=False, deduplicate=<fresh LRUCache>, with_metadata=False)` plus
  `trafilatura.extract_metadata` as one metadata layer.
- Dependency licenses verified from the license files, not READMEs: lxml BSD-3-Clause (LICENSE.txt),
  courlan Apache-2.0, htmldate Apache-2.0, jusText BSD-2-Clause (LICENSE.rst at v3.0.2: two clauses, no
  non-endorsement clause; metadata says "The BSD 2-Clause License", so an override was added), tld
  `MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later` (taken under LGPL-2.1-or-later, a separately installed
  Python package, allowed by the allowlist), lxml-html-clean BSD-3-Clause, dateparser BSD-3-Clause,
  babel BSD-3-Clause, regex Apache-2.0, tzlocal MIT. `tools/license_check.py` passes.
- Known issues and mitigations:
  - Trafilatura's `deduplicate=True` uses a process-wide LRU cache, so a second conversion of a similar page
    loses paragraphs. A fresh `LRUCache` is passed per call.
  - Trafilatura's XML drops code languages, ordered-list starts, `colspan`/`rowspan` (it pads cells),
    figure captions, footnote links, and inline math. Mitigation: Trafilatura only selects the content; every
    block it keeps is matched back into the cleaned DOM by whitespace-free text (exact, then 80 percent
    containment; math compared through its TeX) and rebuilt from the DOM element. Figures, `details`, and
    footnote sections are converted whole. Unmatched blocks are converted from the XML with
    `path = article#<n>`.
  - Trafilatura mutates its input tree: it always receives a deep copy.
  - Trafilatura can invent a title from the URL; its title is accepted only when it is the page's h1 or part of
    the `<title>`.
  - Trafilatura 2.x removed or renamed several 1.x parameters (`no_fallback` became `fast`); only stable 2.x
    keyword arguments are used, pinned `>=2.3.1,<3`.
- Fallback chain: `web.trafilatura` -> (internal) rule extractor when Trafilatura returns under 200 characters
  or under 25 percent of the cleaned page text -> full body when no paragraph survives. Registry chain for
  `text/html` and `application/xhtml+xml`: `web.trafilatura`, `web.rules`, `web.html_raw`.
- Defuddle (JavaScript, MIT) is not vendored or shelled out to. Its useful behaviors are reimplemented as
  Python rules: boilerplate removal by tag, ARIA role, and class/id patterns (with protection for elements
  holding the h1, `<article>`, `<main>`, or most of the paragraph text), main-content selection, MathJax/KaTeX
  TeX recovery, and footnote normalization.
- readability-lxml is not added: the rule extractor covers fallback 1; one fewer dependency (and no chardet).
- Fixtures: 12 self-generated pages from `fixtures/web/_generate.py` (article x3 engines, docs page x2 engines,
  hidden injection, SPA shell, relative links and lazy images, short article, paywall teaser, multipage,
  Windows-1251). Thresholds: `web.trafilatura` 0.95, `web.rules` 0.95, `web.html_raw` 0.90 (spec 5g text
  similarity 0.95; the full-body converter keeps class-pattern widgets by design).

## P1-T02-b: Hidden content is reported in warning detail; invisible characters in a second warning
Status: proposed

- Hidden elements with text are counted in `removed_hidden_elements` (`count` = elements, `detail.type.<kind>`
  per kind, `detail.hidden_text` capped at 10 KB). Empty hidden elements (icons) are removed but not counted;
  KaTeX/MathJax aria-hidden renderings are de-duplication and not counted.
- Removed zero-width/bidi/tag characters get a second `removed_hidden_elements` warning (D-0015 aliases
  `removed_invisible_chars` to that code) with `detail.invisible_chars`.
- The renderer's scanner does not yet receive hidden text, so the converter scans it with
  `ezmd.render.injection.scan(hidden_text=...)` and adds `injection_suspected` with `detail.location=hidden`.
- The warning is emitted whenever something was removed (info severity), not only when a removed element had
  over 20 words (part3 18 phase 1); always reporting is more transparent and costs nothing at info level.
- White-on-white is detected only when the background is declared inline on the element or an ancestor:
  external CSS is not evaluated and a dark theme must not lose visible white text.

## P1-T02-c: Smaller choices
Status: proposed

- Empty pages get a stub `Paragraph` (`attrs.stub=true`) naming the reason (`empty_body_js_required` or
  `extraction_empty`) so the document is never silently empty and the fixture harness sees content.
- The deduplicated link list is the renderer's sidecar `links` array and the compact profile's numbered
  `## Links` section, built from inline links; `Link` blocks are used only for embedded video iframes, to
  avoid printing every link twice. Linked PDFs go to `metadata.extra.outbound_pdfs`.
- `hr` is dropped instead of emitting `Raw("---")`, which the renderer would print as a fenced block.
- The module holding the converter classes is `engines.py`: a submodule named `converters` would shadow the
  family's `converters()` function once imported.

## New dependencies

- `trafilatura` `>=2.3.1,<3`, Apache-2.0, about 1 MB plus dependencies (lxml 9 MB, babel 33 MB, jusText
  2.6 MB, dateparser 1.7 MB, regex 1.2 MB, tld 1 MB, courlan, htmldate, lxml-html-clean, tzlocal), default
  install: the primary web extractor named by the spec (part2 5b step 2).
- `lxml` `>=6.1.3`, BSD-3-Clause, 9 MB, default install: HTML parsing for the hygiene pass and HTML-to-IR
  module (already required by Trafilatura; declared because the family imports it directly).
