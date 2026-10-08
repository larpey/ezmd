# Social and forums (Phase 1 stub)

Package `ezmd_converters.social`, converters `web.social_reddit` and `web.social_hn`, family `web` (spec:
docs/spec/part2.md section 7; ROADMAP P1-T07). The full adapters (comment `more` expansion, Markdown bodies,
listings, user pages, rate limiting, Stack Exchange, Bluesky, Mastodon, feeds) are Phase 3 (P3-T02).

## Family flag

`EZMD_ENABLE_SOCIAL` (off by default).

- Off: both converters are registered as unavailable; `ezmd capabilities` lists them with the reason, and
  Reddit and Hacker News pages fall through to the web family as ordinary HTML.
- On (`1`, `true`, `yes`, `on`; self-host testing only): experimental stub converters claim thread URLs.

## What the stubs do

| Converter | URLs | API |
|---|---|---|
| `web.social_reddit` | `reddit.com/r/<sub>/comments/<id>/...`, `old.reddit.com`, `redd.it/<id>`, `/comments/<id>.json` | `https://www.reddit.com/comments/<id>.json?raw_json=1&limit=500&sort=<sort>` |
| `web.social_hn` | `news.ycombinator.com/item?id=<id>`, `hn.algolia.com/api/v1/items/<id>` | `https://hn.algolia.com/api/v1/items/<id>` |

No network of their own: without a body the converter raises `FetchRequired` for the API URL; with a body
(the fetched API response or an uploaded recorded response) it parses the JSON and renders the shared thread
model (`ezmd_converters.social.model.ThreadNode`): H1 title, the link (link posts), the post body,
`Comments (N)`, then one `Comment` block per node in display order with `attrs` `depth`, `score`,
`parent_id`, `flags`. Deleted, removed, and dead comments are kept as placeholders. Provenance: `source_id` =
post or comment id, `path` = `comments/<id>`.

## Options (`ConvertOptions.extra`)

| Key | Default | Meaning |
|---|---|---|
| `social.sort` | `confidence` | Reddit sort (`confidence`, `top`, `new`, `old`, `controversial`, `qa`) |
| `social.max_comments` | 200 | comments rendered (`comments_truncated` beyond) |

## Warnings

`comments_truncated`, `comments_collapsed` (Reddit `more` stubs, not expanded in Phase 1).

## Known limitations

- Bodies are plain text: Reddit Markdown and HN HTML are not parsed into blocks; spoilers, superscripts, and
  `r/` and `u/` links are not rewritten.
- No `morechildren` expansion, listings, user pages, crossposts, galleries, polls, or linked-page fetching.
- No adapter-level rate limiting (the stubs make no requests); the Phase 3 adapters own that.
- No fixtures: the converters are unavailable by default, so the fixture corpus does not exercise them; the
  unit tests use small inline payloads.
