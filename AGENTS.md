# AGENTS.md

## Project

InterNote — static blog generator (Python 3.14, uv, typer + pydantic + jinja2) that renders GitHub Issues into a GitHub-Pages site.
This repo is the **generator only**; posts, config, and CI live in a separate blog repo.
README is Chinese — keep new user-facing docs consistent.

## Commands

- `uv sync` — install deps (Python pinned in `.python-version`, requires `>=3.14`)
- `uv run pytest -q` — what CI (`.github/workflows/test.yml`) runs on every push/PR. **Currently red**: the old suite is quarantined in `tests-old/` (it asserts the pre-refactor schema/templates) and awaits rewrite against the new ctx shape (`site.*`, `post.*`, `posts.*`, `icons`); restore a `tests/` dir to go green again.
- `uv run internote <token> <owner/repo> [--issue-number N]` — build a site. Needs a GitHub token and `config.toml` in cwd; writes `dist/`, `sources/`, `internote.json` and rewrites README stats. Do not run casually.
- `uv run python scripts/fetch_fixtures.py <owner/repo> -o tests/fixtures/<owner>__<name>.json` — capture issues + pre-rendered markdown via `gh api` into a fixture JSON (uses your gh login, no token args).
- `uv run internote - <owner/repo> --fixtures tests/fixtures/<owner>__<name>.json` — offline build from a fixture (`src/internote/fixtures.py` provides a duck-typed repo + markdown). Use this for local previews and unit tests instead of pushing to verify; the committed fixture in `tests/fixtures/` is the shared test data.
- `uv build` — wheel; `src/internote/templates/` and `src/internote/plugins/` ship automatically (hatchling `packages = ["src/internote"]`), no pyproject change needed when adding files there.

## Layout & architecture

- `src/internote/` package: `cli.py` (entrypoint) → `generator.py` (orchestrator: build state `internote.json`, incremental `run_one()` vs full `run_all()`, README stats update) with `config.py`, `renderer.py`, `github_client.py`, `feed.py`, `constants.py` (i18n + icon SVG paths).
- Templates (`*.j2.html`) and plugins (`*.js`) live **inside the package** and are resolved via `Path(__file__)`, cwd-independent — do not move them to the repo root.
- Plugins are exactly six, all zero-dependency, all IIFE + `'use strict'`, **none inject CSS** (`theme.js` 3-state light/dark/auto, `toc.js` self-implemented TOC with scroll-spy, `lightbox.js` image viewer, `code-copy.js` clipboard buttons, `visit-counter.js` busuanzi/vercount, `giscus.js`). They are copied to `dist/plugins/` verbatim, **not** Jinja-rendered, so they get config from `data-*` attributes on server-rendered markup (`#in-toc[data-toc-title]`, `#visit-counter[data-counter]`), never `{{ }}` placeholders.
- **`window.icons` is narrowed to runtime-only icons**: the template renders every static glyph server-side via the `icon()` macro, so `window.icons` only carries what JS must swap at runtime (theme sun/moon/sync, code-copy copy/check) or apply to DOM built from `post-list.json` (tag page rows). Keep `generator.py`'s per-page crop in sync when adding icons.
- `templates/` is 4 page templates plus `components/`: `macros.j2.html` holds **all** shared UI (`icon`, `nav_link`, `theme_button`, `site_nav`, `branding`, `head_meta`) and is imported with `{% from ... with context %}` so macros can read `icons`/`i18n`; `footer.j2.html` and `comments.j2.html` are plain includes. `site_nav` uses `{% call %}`/`caller()` so a page supplies only its own buttons and gets the `<nav>` wrapper plus theme toggle for free. Icons render `d` server-side — do **not** reintroduce `setAttribute('d', ...)` hydration JS.
- `renderer.py` runs Jinja with `trim_blocks`/`lstrip_blocks` and **autoescape off** (post bodies are pre-rendered HTML from the GitHub API). `base.j2.html` owns the `<style>` wrapper: children fill `{% block style %}` with raw CSS text and base emits the tag only when non-empty.
- **Never mix the `hidden` attribute with inline `style.display`** — Chrome's UA `[hidden]` rule wins over an inline `display`, so the two must not be used on the same element. Toggle the `hidden` *property* in JS; note busuanzi/vercount reveal their counters by assigning `style.display`, so those spans must not carry `hidden`.
- `assets/` (main.css, primer.css — Primer 21 bundled, **no external CDN**) is copied to `dist/assets/` at build time; pages link it at `{{ home_url }}/assets/...`.
- **`main.css` is the only global stylesheet** — it also carries the TOC and lightbox sections. Templates emit no inline `<style>` except the user injection points (`post.style`, `site.index_style`, `layout.all_head`).
- Post bodies render inside Primer's `markdown-body` (GitHub-issues look); theme switching is 3-state light/dark/auto with no config keys, driven by `plugins/theme.js` off `internote_theme` in localStorage. Markdown-alert colors are injected by `generator.py` (`ALERT_BASE_STYLE`/`ALERT_STYLES`); task-list styles live in `main.css` (missing from the Primer bundle).
- Optional per-post TOML front matter lives in `frontmatter.py` and is split off in `_add_entry` **before** the body reaches the markdown renderer (otherwise GitHub renders the `+++` delimiters as an `<hr>`). Fields: `title`/`description`/`date`/`head`/`style`/`script`/`draft`; `labels` is rejected because GitHub issue labels drive the tag pages and single-page routing. Anything unknown raises and fails the build — `split()` is idempotent, which is what lets `scripts/fetch_fixtures.py` pre-strip at capture time so fixture `body_html` matches the cleaned body. Tests in `tests/test_frontmatter.py`.
- `scripts/fetch_fixtures.py` calls `gh` with an explicit `encoding="utf-8"`; without it the GBK locale codec crashes on non-ASCII issue bodies on Chinese Windows.
- `config.py` uses `ConfigDict(extra="forbid")` everywhere: any unknown key in `config.toml` is a hard error. Current schema = `config.sample.toml` (`[site]`/`[layout]`/`[comments]`/`[giscus]`/`[features]`; no theme/nav/feed/version).
- Template ctx: one flat `site` dict from `config.context()` (generator adds `blog_repo_url`, `label_color_dict`, `single_list`, `prev_url`/`next_url`), plus `post` (post page data), `posts` (list items via `_list_item()`), `icons` (cropped per page), `i18n`. `post-list` is the list template name (`plist` is gone).
- URLs: posts `post/<issue#>.html`; label pages `<label>.html` (which labels are single pages comes from `[layout]`). Search index `dist/post-list.json`.

## Two-repo flow (get this wrong and you break the live blog)

- Blog repo = Issues (each needs ≥1 label) + `config.toml` + `.github/workflows/internote.yml` (copy of `examples/blog-workflow.yml`). This repo never stores posts.
- Blog CI **clones this repo** into `/opt/Internote` (always HEAD of `main`; the old `site.version` pinning was removed), overlays the blog files, runs the CLI, commits artifacts back, deploys Pages.
- **Schema sync**: a `config.py` change must be applied to the blog repo's `config.toml` and, if the workflow changed, to `.github/workflows/internote.yml` in the same change — `extra="forbid"` turns stale blog keys into a hard build failure. (GitHub contents-API `PUT` on that repo's workflow paths 404s; clone the blog repo and push instead.)
- Therefore: **pushing to `main` here changes the live blog** at the next build (daily cron 0 16:00 UTC, any issue edit, or manual dispatch).
- `dist/`, `sources/`, `internote.json` are git-ignored here but must be committed by the blog repo (README `.gitignore` warning).
- Local deploy trigger: `gh workflow run internote.yml -R interset-wq/interset-wq.github.io` then `gh run watch <id> -R interset-wq/interset-wq.github.io --exit-status`.

## Conventions

- No TDD/SDD: do not write failing tests first or follow spec-driven development (too slow / token-heavy). Keep existing tests passing (`uv run pytest -q` before committing); add/adjust tests only when touching tested behavior. Commits atomic with English semantic prefixes (`feat:`/`fix:`/`refactor:`/`docs:`/`chore:`).
- Only `main` branch; push only with explicit user approval (global rule).
- `temp/` is git-ignored scratch space for this project (scripts, config copies).
