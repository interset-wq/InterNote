# Algolia-backed site search

Status: approved
Date: 2026-10-01

## Problem

Search exists on `tag.html` only, and it is a case-insensitive substring match
against the rendered row text of the tag page (`tag.j2.html:178`). It covers
title plus label badges plus the date badge, and nothing else. Article bodies
are not searchable.

A second defect: `post-list.json` is built by walking `ctx["post_list"]` only
(`generator.py:548`), so `single_list` entries never enter the index. Single
pages such as `about.html` are invisible to search. The RSS feed merges both
lists (`_create_feed`, `generator.py:502`) but the search index does not.

## Decision

Add Algolia as a hosted search backend, fed by the generator at build time, and
replace the inline substring search with a site-wide modal dialog.

Chosen after surveying current free tiers. Only Algolia and Upstash Search offer
permanently free hosted tiers; Meilisearch Cloud ($20/mo) and Typesense Cloud
(one-shot 720 free hours) are trials that expire. DocSearch was rejected because
it is free only for eligible documentation sites and requires application.

## Non-goals

- Semantic or vector search. Algolia's relevance ranking is lexical.
- Per-heading record splitting as DocSearch does. One record per post is
  sufficient at this scale; `attributesToSnippet` supplies match context.
- Any change to how posts are written, labelled, or routed.
- Search over anything not already in the index.

## Architecture

```
build ──► generator renders posts
            ├──► _finalize() writes post-list.json      (unchanged)
            └──► _sync_search()          [new, network, opt-in]
                  │  ALGOLIA_ADMIN_KEY set? ── no ──► skip silently
                  ▼
                  1. copy settings   main → tmp
                  2. batch addObject all records into tmp
                  3. moveIndex       tmp → main
                  ▼
              Algolia index

browser ──Ctrl/Cmd+K──► plugins/search.js
                          └──► POST /1/indexes/{index}/query ──► results overlay
```

### Why no SDK

Neither Algolia SDK is used.

`algoliasearch` for Python is 4.47.0 and declares `requires_python >=3.8.1`, so it
is compatible with the pinned 3.14, but it pulls in `aiohttp`, `async-timeout`,
`python-dateutil`, `requests` and `urllib3` — five dependencies for one batch
POST. The JS client would mean either a CDN script, which contradicts the
bundled-Primer policy in `AGENTS.md`, or vendoring roughly 40 kB.

Both APIs are plain REST. The Python side uses `urllib.request` from the standard
library; the browser side uses `fetch`. This matches the existing decision to
self-implement the TOC in `toc.js` rather than depend on tocbot.

### Why the three-step index swap

Clearing and refilling in place leaves the index briefly empty, and a reader
searching during a publish sees no results. Algolia's temporary-index pattern
avoids that: copy settings to a scratch index, write records there, then move it
over the live name. Three HTTP calls, no SDK, and the swap is a server-side
rename.

## Records

One record per post. `objectID` is `post-<issue number>` for `post_list` entries
and `page-<label>` for `single_list` entries, so the two namespaces cannot
collide.

| Field | Source |
|---|---|
| `objectID` | `post-<n>` or `page-<label>` |
| `title` | front-matter `title`, falling back to issue title — same precedence as the rendered page |
| `body` | plain text derived from `sources/<n>.md` |
| `labels` | label names, for faceting |
| `url` | `post_url` resolved to absolute against `home_url` |
| `date` | `created_date` |
| `wordCount` | entry word count |

### Why the markdown source, not the rendered HTML

The first draft of this spec indexed `body_html`. That turned out not to exist:
`_create_post` renders the body into a local and passes it straight to the
template, so it never reaches the entry dict. The only ways to get it were to
cache it on the entry or to re-read the rendered page, and both are worse than
the obvious alternative.

`sources/<n>.md` is already written per post, already stripped of front matter,
and already what the render cache keys on. Indexing it keeps `internote.json`
unchanged in size — which matters because the blog repo commits that file — and
works identically on a full build and an incremental one, since `sources/` is
not wiped by `run_one`.

The cost is stripping markdown rather than HTML, which is the same set of rules
in reverse order.

### Markdown stripping

`<script>` and `<style>` are dropped with their contents, inline HTML tags are
removed, images keep their alt text and links keep their label, heading /
blockquote / list / rule markers are stripped, and fence markers go while the
code between them stays — code is legitimate searchable content. HTML entities
are decoded **last**, so an escaped `&lt;script&gt;` cannot reconstruct a tag
after the tag pass has already run.

That last case is worth being precise about: an escaped tag *does* survive into
the indexed text as literal `<script>`, because the author meant it to be
visible. That is fine, because the dialog only ever builds DOM from text nodes
and `search.js` contains no `innerHTML`. A test asserts that absence directly,
since it is the actual safety property rather than a consequence of the
stripping rules.

`post_url` is stored percent-encoded and relative (`generator.py:250`), so it is
resolved against `home_url` before upload. A consumer sitting outside `dist/`
cannot use the raw value.

## Index settings

```
searchableAttributes:   ["title", "labels", "body"]
attributesForFaceting:  ["searchable(labels)"]
attributesToSnippet:    ["body:25"]
```

Setting these on every sync is deliberate. It keeps the index self-describing, so
a settings change in this repository takes effect on the next build instead of
requiring a one-off dashboard edit.

## Configuration

Mirrors the existing `visit_counter` plus `[giscus]` split.

```toml
[features]
search = "off"        # off | algolia

[search]
app_id     = "..."
api_key    = "..."    # search-only key
index_name = "posts"
```

`features.search` is `Literal["off", "algolia"]` defaulting to `"off"`, exactly
like `features.visit_counter`. The three credential keys default to `""` so a
config that omits the section still validates.

### Credential separation

The **admin key is never stored in `config.toml`**. It is read from the
`ALGOLIA_ADMIN_KEY` environment variable, populated from a CI secret, following
the existing `secrets.GITHUB_TOKEN` pattern in `examples/blog-workflow.yml`.

The search-only key *is* stored in `config.toml` and committed to the blog repo.
That is correct: an Algolia search-only key is restricted to search operations by
design, and it is the key the browser must have. Only the admin key is sensitive.

### Schema sync obligation

`config.py` sets `extra="forbid"` on every model. Adding `[search]` and
`[features].search` means the blog repository must gain both keys in the same
change or the build fails validation. `.github/workflows/internote.yml` must also
export `ALGOLIA_ADMIN_KEY`. Both edits are part of this work, per the
two-repository rule in `AGENTS.md`.

## The plugin

`src/internote/plugins/search.js`, following all six existing conventions: IIFE
with `'use strict'`, copied verbatim to `dist/plugins/` so it is never
Jinja-rendered, configuration read from `data-*` attributes on its own `<script>`
tag, no CSS injection, and a `document.readyState` bootstrap guard.

Behaviour:

- `Ctrl`/`Cmd` + `K` toggles the dialog; `Escape` closes; arrows move the
  selection; `Enter` navigates.
- The nav search control opens the dialog instead of linking to `tag.html`.
- Results render title, label badges, and a highlighted snippet.
- The plugin returns early when its anchor element is absent, so pages without
  the script tag are unaffected.

Styling lives in `main.css` under the `in-search-` prefix using `--in-*` tokens.
Never combine the `hidden` attribute with `style.display` on the same element;
toggle the `hidden` property.

### Tag browsing

`tag.html` keeps its tag cloud and label filtering. Its inline substring search
is removed, since the modal replaces it. Because the nav search control no longer
links there, a footer link to `tag.html` is added for tag browsing. Adding a nav
icon for tags was rejected as unnecessary churn for `window.icons`.

## Failure handling

A failed push emits a loud warning and **does not fail the build**. A search
outage must not block publishing an article. The warning names the failing step
so a silent index drift is visible in the Actions log.

`_sync_search()` is skipped entirely — no network call — when
`ALGOLIA_ADMIN_KEY` is unset, which covers tests, fixture builds, and local
previews. Since the build is the only source of records, re-running a build is
also the way to repair a drifted index.

## Testing

Not TDD. Tests are written alongside the behaviour, covering:

- `[search]` schema validation, including `extra="forbid"` rejecting unknown keys
  and `features.search` rejecting values outside the `Literal`
- Markdown stripping: script and style contents removed, entities decoded,
  whitespace collapsed, code text retained, escaped tags left inert
- Record shape, including that `single_list` entries are present — the bug this
  work fixes
- `url` resolved to absolute against `home_url`, and a trailing slash on
  `home_url` not doubled
- `post-N` and `page-N` objectIDs cannot collide when an issue number is also a
  label name
- `_sync_search()` performs no HTTP call when the admin key is absent, and
  `features.search = "off"` never reaches `sync` at all
- The three-step swap issues `posts/operation`, `posts_tmp/settings`,
  `posts_tmp/batch`, `posts_tmp/operation` in that order, with the admin key in
  the header and never in a URL
- An empty site clears the scratch index explicitly, since an empty batch is a
  no-op and a move could otherwise resurrect stale records
- A failing push warns rather than raising
- `search.js` contains no `innerHTML`, `outerHTML` or `insertAdjacentHTML`

Shared HTTP stubbing lives in `tests/conftest.py` because `tests/` is not an
importable package and two modules need the same double.

## Known risks

- **Index drift.** If a push degrades to a warning, search serves stale content.
  Mitigated by a warning that names the failing step, and by the fact that any
  rebuild re-syncs.
- **Algolia branding.** The free tier requires displaying the Algolia logo in the
  search UI.
- **CJK relevance is unverified.** Algolia handles Chinese natively, but this has
  not been tested against real content. The first acceptance test is that a term
  such as `这是` matches a post containing it, and that a title-only term
  outranks a body-only term. The UI path was verified in a browser against a
  stubbed endpoint: endpoint, headers, `\u0001`/`\u0002` highlight sentinels,
  `<mark>` rendering, arrow-key selection and `Escape` all behave. What remains
  unproven is Algolia's own ranking and Chinese segmentation on real data.