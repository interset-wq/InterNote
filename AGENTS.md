# AGENTS.md

## Project

InterNote — static blog generator (Python 3.14, uv, typer + pydantic + jinja2), a rewrite of Gmeek.
This repo is the **generator only**; posts, config, and CI live in a separate blog repo.
README is Chinese — keep new user-facing docs consistent.

## Commands

- `uv sync` — install deps (Python pinned in `.python-version`, requires `>=3.14`)
- `uv run pytest -q` — full suite; this is exactly what CI (`.github/workflows/test.yml`) runs on every push/PR (`uv sync --frozen` first). Must pass before committing.
- `uv run pytest tests/test_renderer.py::test_name -q` — single test
- `uv run internote <token> <owner/repo> [--issue-number N]` — build a site. Needs a GitHub token and `config.toml` in cwd; writes `dist/`, `sources/`, `internote.json` and rewrites README stats. Do not run casually.
- `uv build` — wheel; `src/internote/templates/` and `src/internote/plugins/` ship automatically (hatchling `packages = ["src/internote"]`), no pyproject change needed when adding files there.

## Layout & architecture

- `src/internote/` package: `cli.py` (entrypoint) → `generator.py` (orchestrator: build state `internote.json`, incremental `run_one()` vs full `run_all()`, README stats update) with `config.py`, `renderer.py`, `github_client.py`, `feed.py`, `constants.py` (i18n + icon SVG paths).
- Templates (`*.j2.html`) and plugins (`*.js`) live **inside the package** and are resolved via `Path(__file__)`, cwd-independent — do not move them to the repo root.
- `config.py` uses `ConfigDict(extra="forbid")` everywhere: any unknown key in `config.toml` is a hard error.
- URLs: posts `post/<issue#>.html`; label pages `<label>.html` (which labels are single pages comes from `[layout]` config). Search index `dist/post-list.json`.
- Renderer tests: `tests/test_renderer.py` has `base_context(**overrides)` (defaults incl. `blog_repo_url`) and `_header(html)` / `_footer(html)` helpers for region assertions.

## Two-repo flow (get this wrong and you break the live blog)

- Blog repo = Issues (each needs ≥1 label) + `config.toml` + `.github/workflows/internote.yml` (copy of `examples/blog-workflow.yml`). This repo never stores posts.
- Blog CI **clones this repo** into `/opt/Internote` (config `site.version = "last"`; there are **no git tags**, so it falls back to HEAD of `main`), overlays the blog files, runs the CLI, commits artifacts back, deploys Pages.
- Therefore: **pushing to `main` here changes the live blog** at the next build (daily cron 0 16:00 UTC, any issue edit, or manual dispatch).
- `dist/`, `sources/`, `internote.json` are git-ignored here but must be committed by the blog repo (README `.gitignore` warning).
- Local deploy trigger: `gh workflow run internote.yml -R interset-wq/interset-wq.github.io` then `gh run watch <id> -R interset-wq/interset-wq.github.io --exit-status`.

## Conventions

- TDD: write a failing test first, then implement; commits atomic with English semantic prefixes (`feat:`/`fix:`/`refactor:`/`docs:`/`chore:`).
- Only `main` branch; push only with explicit user approval (global rule).
- `temp/` is git-ignored scratch space for this project (scripts, config copies).
