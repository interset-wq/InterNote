# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from . import frontmatter
from .config import InternoteConfig
from .constants import ICONS, get_i18n
from .feed import build_feed, strip_build_date
from .frontmatter import FrontMatterError
from .renderer import Renderer

#: Only collaborator comments may become sub posts; reader comments are
#: never parsed, so a passer-by cannot inject pages into the site.
SUB_AUTHORS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

MATHJAX_SCRIPT = (
    '<script>MathJax = {tex: {inlineMath: [["$", "$"]]}};</script>'
    '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>'
)

# Raw CSS (no <style> wrapper): base.j2.html already wraps the {% block
# style %} content in a <style> tag, and a nested tag would close it
# early and dump the rest of the CSS onto the page as text.
ALERT_BASE_STYLE = (
    ".markdown-alert{padding:0.5rem 1rem;margin-bottom:1rem;"
    "border-left:.25em solid var(--borderColor-default,var(--color-border-default));}"
    ".markdown-alert .markdown-alert-title {display:flex;"
    "font-weight:var(--base-text-weight-medium,500);align-items:center;line-height:1;}"
    ".markdown-alert>:first-child {margin-top:0;}"
    ".markdown-alert>:last-child {margin-bottom:0;}"
)

ALERT_STYLES = {
    "note": "accent",
    "tip": "success",
    "important": "done",
    "warning": "attention",
    "caution": "danger",
}

#: Root file names the build itself owns. A slug colliding with one of
#: these would shadow generator output, so it is rejected up front.
#: ``about`` is deliberately allowed — it is the conventional alias.
RESERVED_SLUGS = {
    "index",
    "post",
    "tag",
    "rss",
    "search-index",
    "assets",
    "plugins",
    "sources",
    "internote",
}


class Generator:
    def __init__(
        self,
        config: InternoteConfig,
        repo,
        repo_name: str,
        *,
        markdown,
        root: str | Path = ".",
    ):
        self.config = config
        self.repo = repo
        self.repo_name = repo_name
        self.markdown = markdown
        self.root = Path(root)

        self.dist_dir = self.root / "dist"
        self.post_dir = self.dist_dir / "post"
        self.sources_dir = self.root / "sources"
        self.static_dir = self.root / "static"
        self.plugins_dir = Path(__file__).resolve().parent / "plugins"
        self.assets_dir = Path(__file__).resolve().parent / "assets"
        self.state_path = self.root / "internote.json"

        self.ctx = config.context()
        self.ctx["label_color_dict"] = {
            label.name: "#" + label.color for label in repo.get_labels()
        }
        if not self.ctx["home_url"]:
            if str(repo.name).lower() == (
                str(repo.owner.login) + ".github.io"
            ).lower():
                self.ctx["home_url"] = f"https://{repo.name}"
            else:
                self.ctx["home_url"] = (
                    f"https://{repo.owner.login}.github.io/{repo.name}"
                )
        # effective comment switch: user wants comments AND giscus configured
        self.ctx["need_comment"] = bool(
            self.ctx["need_comment"] and self.ctx["giscus_repo"]
        )
        self.ctx["blog_repo_url"] = f"https://github.com/{repo_name}"
        # Resolved by _fetch_favicon before any page renders; empty = no
        # <link rel="icon">.
        self.ctx["favicon_file"] = ""
        # id -> inline SVG markup, resolved by _fetch_social_icons before
        # any page renders; empty dict = footer shows only RSS/GitHub.
        self.ctx["social_icons"] = {}
        print("GitHub Pages URL: ", self.ctx["home_url"])

        self.tz = datetime.timezone(datetime.timedelta(hours=self.ctx["utc"]))
        # stamped into every page footer: when this exact artifact was built
        self.ctx["build_time"] = datetime.datetime.now(self.tz).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.i18n = get_i18n(self.ctx["language"])
        self.renderer = Renderer(Path(__file__).resolve().parent / "templates")

        self.old_feed = ""
        rss_path = self.dist_dir / "rss.xml"
        if rss_path.exists():
            self.old_feed = rss_path.read_text(encoding="utf-8")

        # Rendered markdown, keyed on a hash of the body. Loaded
        # independently of the entry state: run_all rebuilds every post
        # from scratch but can still reuse the HTML.
        self.render_cache: dict[str, str] = {}
        self.render_cache_used: set[str] = set()
        # favicon/avatar state: source URL each cached dist/assets/*.png
        # was downloaded from, keyed by file name
        self.favicon_src: dict[str, str] = {}
        # :shortcode: -> <img> map for emoji inlining, loaded lazily by
        # _load_emoji_map() before the first page renders
        self.emoji_map: dict[str, str] = {}
        if self.state_path.exists():
            try:
                cached = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cached = {}
            if isinstance(cached.get("render_cache"), dict):
                self.render_cache = cached["render_cache"]
            raw_sources = cached.get("favicon_src", "")
            # older builds stored a single string for the favicon only
            if isinstance(raw_sources, dict):
                self.favicon_src = raw_sources
            elif raw_sources:
                self.favicon_src = {"favicon.png": raw_sources}

    # ------------------------------------------------------------------ run

    def _fetch_favicon(self):
        """Resolve [site].favicon to a local file under dist/assets/.

        Empty config downloads the blog repo owner's GitHub avatar (the
        default); a URL downloads that image; "none" disables the favicon.
        The same avatar is also fetched at a larger size as
        dist/assets/avatar.png for the site header and og:image — one
        download per size, cached the same way. Downloads are keyed on
        their source URL in internote.json, so an unchanged avatar is not
        re-fetched on every build. Any failure only warns: a flaky network
        must not fail the blog build. Fixture mode (a repo without an
        avatar_url) skips the download entirely but keeps existing files,
        so offline previews still show them.
        """
        sources = {}
        setting = str(self.ctx.get("favicon") or "").strip()
        if setting.lower() != "none":
            if setting:
                sources["favicon.png"] = setting
            else:
                avatar_url = getattr(getattr(self.repo, "owner", None), "avatar_url", "")
                if avatar_url:
                    joiner = "&" if "?" in avatar_url else "?"
                    sources["favicon.png"] = avatar_url + joiner + "size=64"
                    sources["avatar.png"] = avatar_url + joiner + "size=200"

        cached_sources = dict(self.favicon_src)
        for name, source in sources.items():
            path = self.dist_dir / "assets" / name
            if cached_sources.get(name) == source and path.exists():
                continue
            try:
                request = urllib.request.Request(
                    source, headers={"User-Agent": "Internote"}
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read()
                if not data:
                    raise ValueError("empty response")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                cached_sources[name] = source
                print("create", name, "from", source)
            except Exception as error:  # noqa: BLE001 - never fail the build
                print("warning: {} download failed ({}); {}".format(
                    name, source, error
                ))
        self.favicon_src = cached_sources

        favicon_path = self.dist_dir / "assets" / "favicon.png"
        self.ctx["favicon_file"] = (
            "assets/favicon.png" if favicon_path.exists() else ""
        )
        avatar_path = self.dist_dir / "assets" / "avatar.png"
        if avatar_path.exists():
            # full URL: the branding macro uses it as-is and og:image
            # requires an absolute address
            self.ctx["avatar_file"] = (
                self.ctx["home_url"] + "/assets/avatar.png"
            )
        elif self.ctx.get("avatar_url"):
            # No local copy (fixture mode, or every download failed): fall
            # back to the configured hotlink rather than a broken image.
            self.ctx["avatar_file"] = self.ctx["avatar_url"]
        else:
            self.ctx["avatar_file"] = ""

    def _fetch_social_icons(self):
        """Resolve [social] entries into inline SVG markup for the footer.

        Each entry's brand glyph comes from the Simple Icons CDN by slug
        and is stored under dist/assets/social/ — the markup is inlined
        server-side, so the pages carry no extra requests and no third-
        party script. Downloads share the favicon cache keyed on the
        source URL in internote.json. A failure only warns and drops that
        one icon: a flaky network must not fail the blog build.
        """
        self.ctx["social_icons"] = {}
        # The built-in RSS and GitHub buttons ride the same [[social]]
        # pipeline: one code path downloads, inlines and renders every
        # footer icon. A user entry with the same id replaces the built-in.
        user_ids = {item["id"] for item in self.ctx.get("social") or []}
        builtins = [
            item
            for item in (
                {
                    "id": "rss",
                    "title": "RSS",
                    "action": "link",
                    "url": self.ctx["home_url"] + "/rss.xml",
                },
                {
                    "id": "github",
                    "title": "GitHub",
                    "action": "link",
                    "url": self.ctx["blog_repo_url"],
                },
            )
            if item["id"] not in user_ids
        ]
        for item in builtins + (self.ctx.get("social") or []):
            name = "social/{}.svg".format(item["id"])
            source = "https://cdn.simpleicons.org/{}".format(item["id"])
            path = self.dist_dir / "assets" / name
            if not (self.favicon_src.get(name) == source and path.exists()):
                try:
                    request = urllib.request.Request(
                        source, headers={"User-Agent": "Internote"}
                    )
                    with urllib.request.urlopen(request, timeout=30) as response:
                        data = response.read()
                    if not data:
                        raise ValueError("empty response")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    self.favicon_src[name] = source
                    print("create", name, "from", source)
                except Exception as error:  # noqa: BLE001 - never fail
                    print(
                        "warning: social icon {} download failed ({}); "
                        "it is skipped".format(item["id"], error)
                    )
                    continue
            self.ctx["social_icons"][item["id"]] = path.read_text(
                encoding="utf-8"
            )

    def run_all(self):
        print("====== start create static html ======")
        self._clean()
        self._fetch_favicon()
        self._fetch_social_icons()
        self._load_emoji_map()
        for issue in self.repo.get_issues():
            self._add_entry(issue)
        for entry in list(self.ctx["post_list"].values()):
            self._create_post(entry)
        self._create_lists()
        self._create_feed()
        self._finalize()
        print("====== create static html end ======")

    def run_one(self, number_str: str):
        print("====== start create static html ======")
        if self.state_path.exists():
            self._load_state()
        else:
            self._clean()
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self._fetch_favicon()
        self._fetch_social_icons()
        self._load_emoji_map()
        issue = self.repo.get_issue(int(number_str))
        if issue.state != "open":
            self._drop_entry(issue.number, "issue is closed")
        else:
            entry = self._add_entry(issue)
            if entry is not None:
                self._create_post(entry)
        # A withdrawn post still has to reach the lists, the feed and the
        # state file, otherwise they keep linking to a page that is gone.
        self._create_lists()
        self._create_feed()
        self._finalize()
        print("====== create static html end ======")

    # -------------------------------------------------------------- prepare

    def _clean(self):
        workspace = os.environ.get("GITHUB_WORKSPACE")
        if workspace:
            for name in ("dist", "sources"):
                stale = Path(workspace) / name
                if stale.exists():
                    shutil.rmtree(stale)

        for path in (self.dist_dir, self.sources_dir):
            if path.exists():
                shutil.rmtree(path)
        self.post_dir.mkdir(parents=True)
        self.sources_dir.mkdir(parents=True)

        if self.static_dir.exists():
            for item in self.static_dir.iterdir():
                target = self.dist_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
        else:
            print("static does not exist")

        # ship packaged css so pages can reference it
        if self.assets_dir.exists():
            shutil.copytree(
                self.assets_dir, self.dist_dir / "assets",
                dirs_exist_ok=True,
            )

        if self.plugins_dir.exists():
            shutil.copytree(
                self.plugins_dir, self.dist_dir / "plugins", dirs_exist_ok=True
            )

    def _load_state(self):
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        post_list = data.get("post_list", {})
        # Pre-alias state kept single pages in a separate list; fold them in
        # so the stale-path cleanup in _add_entry migrates them to the
        # canonical post/<id>.html URL on the next incremental build.
        for key, entry in data.get("single_list", {}).items():
            post_list.setdefault(key, entry)
        self.ctx["post_list"] = post_list

    def _drop_entry(self, number: int, reason: str) -> bool:
        """Withdraw a post: remove its page and its entry from the state.

        Called when an issue stops qualifying for publication - closed,
        marked draft, or turned into a pull request. Without this the
        homepage, the search index and the feed keep pointing at a page
        that no longer exists.
        """
        key = f"P{number}"
        entry = self.ctx["post_list"].get(key)
        if entry is None:
            return False
        for path in (entry["html_dir"], entry.get("alias_dir")):
            if not path:
                continue
            page = Path(path)
            if page.exists():
                page.unlink()
        # Sub-post pages follow their parent offline (closed series = the
        # whole series goes), so sweep <issue>_<comment>.html too.
        for stale_page in self.post_dir.glob(f"{number}_*.html"):
            stale_page.unlink()
        del self.ctx["post_list"][key]
        print("withdraw #{} ({}): {}".format(number, reason, entry["html_dir"]))
        return True

    # -------------------------------------------------------------- entries

    def _add_entry(self, issue):
        # get_issues() returns pull requests alongside issues, so a PR would
        # otherwise be published as a post and pushed into the search index.
        # fetch_fixtures.py has always filtered these out, which is why this
        # only showed up on the live path.
        if getattr(issue, "pull_request", None):
            print(f"pull request #{issue.number}, skipped")
            self._drop_entry(issue.number, "is a pull request")
            return None

        raw_body = issue.body or ""
        try:
            meta, body = frontmatter.split(raw_body)
        except frontmatter.FrontMatterError as error:
            raise FrontMatterError(
                "issue #{}: {}".format(issue.number, error)
            ) from error

        if meta.get("draft"):
            # An incremental build does not clear dist, so a post that used
            # to be published would otherwise keep serving a stale page.
            self._drop_entry(issue.number, "draft")
            return None

        # Labels are optional: an issue published without any is tagged
        # `default`, so forgetting a label never silences a post.
        labels = [label.name for label in issue.labels] or ["default"]

        # The canonical URL is always post/<id>.html. `slug` never changes
        # it; the slug only mints a root-level alias page that redirects
        # there, so renames never break inbound links to the canonical URL.
        slug = str(meta.get("slug") or "").strip()
        if "slug" in meta and not slug:
            raise FrontMatterError(
                "issue #{}: front matter 'slug' must not be empty".format(
                    issue.number
                )
            )
        alias_dir = None
        if slug:
            if slug.startswith(".") or slug in RESERVED_SLUGS or re.fullmatch(
                r"page\d+", slug
            ):
                raise FrontMatterError(
                    "issue #{}: invalid front matter 'slug': {!r}".format(
                        issue.number, meta["slug"]
                    )
                )
            file_name = re.sub(r'[<>:/\\|?*\"]|[\0-\31]', "-", slug)
            alias_dir = self.dist_dir / f"{file_name}.html"

        html_dir = self.post_dir / f"{issue.number}.html"
        post_url = urllib.parse.quote(
            html_dir.relative_to(self.dist_dir).as_posix()
        )

        entry = {
            "number": issue.number,
            "html_dir": str(html_dir),
            "labels": labels,
            "post_title": issue.title,
            "post_url": post_url,
            "word_count": len(body),
            "top": 0,
            # Default is on: a page opts out with `comments = false`.
            "comments": meta.get("comments") is not False,
            "style": self.ctx["style"],
            "script": self.ctx["script"],
            "head": self.ctx["head"],
        }
        if alias_dir is not None:
            entry["slug"] = file_name
            entry["alias_dir"] = str(alias_dir)

        if body:
            period = "。" if self.ctx["language"] == "CN" else "."
            entry["description"] = (
                body.split(period)[0].replace('"', "'") + period
            )
        else:
            entry["description"] = ""

        for event in issue.get_events():
            if event.event == "pinned":
                entry["top"] = 1
            elif event.event == "unpinned":
                entry["top"] = 0
        if "pinned" in meta:
            # Front matter wins over timeline events, so an author can pin
            # without repo-maintainer access to the issue page.
            entry["top"] = 1 if meta["pinned"] else 0

        if "date" in meta:
            entry["created_at"] = frontmatter.parse_date(meta["date"])
        else:
            created = issue.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=datetime.timezone.utc)
            entry["created_at"] = int(created.timestamp())

        this_time = datetime.datetime.fromtimestamp(entry["created_at"], tz=self.tz)
        entry["created_date"] = this_time.strftime("%Y-%m-%d")
        year_colors = ["#bc4c00", "#0969da", "#1f883d", "#A333D0"]
        entry["date_label_color"] = year_colors[
            this_time.year % len(year_colors)
        ]

        updated = issue.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=datetime.timezone.utc)
        entry["updated_at"] = int(updated.timestamp())
        upd_time = datetime.datetime.fromtimestamp(entry["updated_at"], tz=self.tz)
        entry["updated_date"] = upd_time.strftime("%Y-%m-%d")

        self.sources_dir.mkdir(parents=True, exist_ok=True)
        # The stripped body is what reaches the markdown renderer, so the
        # delimiters never turn into an <hr>.
        (self.sources_dir / f"{issue.number}.md").write_text(body, encoding="utf-8")

        self._sync_sub_posts(issue, entry)

        key = f"P{issue.number}"
        # The canonical file name is stable, but the alias is not. When a
        # slug is added, renamed or removed, drop the stale files so an
        # incremental build cannot serve leftovers (the canonical page is
        # re-rendered right after by the caller).
        stale = self.ctx["post_list"].get(key)
        if stale is not None:
            for path in (stale["html_dir"], stale.get("alias_dir")):
                if not path:
                    continue
                page = Path(path)
                if page.exists():
                    page.unlink()

        self.ctx["post_list"][key] = entry
        return entry

    def _sync_sub_posts(self, issue, entry):
        """Turn collaborator comments carrying front matter into sub posts.

        A comment whose body opens with a ``+++`` block (``title``/``order``
        only) becomes a page at ``post/<issue>_<comment>.html``; its position
        under the parent *is* the relationship, so no link syntax is needed.
        Reader comments are ignored entirely. The comment count on the issue
        object decides whether ``get_comments()`` is worth a call: full
        builds re-pull every issue that has comments (editing a comment does
        not change the count, so this is the only reliable refresh), issues
        without comments cost nothing.
        """
        count = getattr(issue, "comments", 0)
        cached = self.ctx["post_list"].get(f"P{issue.number}", {}).get("subs")
        if not count and not cached:
            entry["subs"] = []
            return

        parsed = []
        for comment in issue.get_comments():
            if getattr(comment, "author_association", "NONE") not in SUB_AUTHORS:
                continue
            raw = comment.body or ""
            meta: dict = {}
            if frontmatter.has_front_matter(raw):
                try:
                    meta, sub_body = frontmatter.split_sub(raw)
                except frontmatter.FrontMatterError as error:
                    raise FrontMatterError(
                        "issue #{} comment {}: {}".format(
                            issue.number, comment.id, error
                        )
                    ) from error
                title = meta.get("title")
                if not title:
                    # No explicit title: the leading h1 carries the title
                    # semantics and is consumed out of the body so the
                    # page does not render it twice.
                    title, sub_body = frontmatter.take_leading_h1(sub_body)
                if not title:
                    raise FrontMatterError(
                        "issue #{} comment {}: a sub post needs a 'title' or "
                        "a leading '# ' heading".format(issue.number, comment.id)
                    )
            else:
                # Relaxed trigger: a comment that opens with a bare ATX h1
                # (no front matter at all) is a sub post too — the h1
                # becomes the title and is consumed. Anything else is an
                # ordinary comment and is ignored.
                title, sub_body = frontmatter.take_leading_h1(raw)
                if not title:
                    continue
            created = comment.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=datetime.timezone.utc)
            parsed.append(
                {
                    "id": str(comment.id),
                    "title": title,
                    "order": meta.get("order"),
                    "created_at": int(created.timestamp()),
                    "body": sub_body,
                }
            )

        # explicit `order` first (smaller = earlier), then comment time
        parsed.sort(
            key=lambda s: (
                s["order"] if s["order"] is not None else float("inf"),
                s["created_at"],
            )
        )

        total = len(parsed)
        kept = []
        for index, sub in enumerate(parsed):
            html_dir = self.post_dir / f"{issue.number}_{sub['id']}.html"
            sub_url = urllib.parse.quote(
                html_dir.relative_to(self.dist_dir).as_posix()
            )
            (self.sources_dir / f"{issue.number}_{sub['id']}.md").write_text(
                sub["body"], encoding="utf-8"
            )
            created_time = datetime.datetime.fromtimestamp(
                sub["created_at"], tz=self.tz
            )
            year_colors = ["#bc4c00", "#0969da", "#1f883d", "#A333D0"]
            kept.append(
                {
                    "id": sub["id"],
                    "title": sub["title"],
                    "url": sub_url,
                    "html_dir": str(html_dir),
                    "created_date": created_time.strftime("%Y-%m-%d"),
                    "date_label_color": year_colors[
                        created_time.year % len(year_colors)
                    ],
                }
            )
        # Must be set BEFORE the render loop: each sub page's ctx carries
        # the full series listing, which reads entry["subs"].
        entry["subs"] = kept
        for index, sub in enumerate(kept):
            crumb = {
                "parent_title": entry["post_title"],
                "parent_url": entry["post_url"],
                "index": index + 1,
                "total": total,
            }
            pager = {"prev": None, "next": None}
            if index > 0:
                pager["prev"] = {
                    "title": kept[index - 1]["title"],
                    "url": kept[index - 1]["url"],
                }
            if index + 1 < total:
                pager["next"] = {
                    "title": kept[index + 1]["title"],
                    "url": kept[index + 1]["url"],
                }
            self._render_sub_page(entry, parsed[index], kept[index], crumb, pager)

        # Comments that were deleted (or lost their front matter) must not
        # keep serving stale pages on an incremental build.
        live = {Path(s["html_dir"]).name for s in kept}
        for stale_page in self.post_dir.glob(f"{issue.number}_*.html"):
            if stale_page.name not in live:
                stale_page.unlink()
                print("withdraw sub post", stale_page.name)

    def _render_sub_page(self, entry, parsed, kept, crumb, pager):
        sub_body = self._decorate_body(entry, self._render_body(parsed["body"]))
        page = dict(self.ctx)
        page["post"] = {
            "title": kept["title"],
            "url": self.ctx["home_url"] + "/" + kept["url"],
            # a sub post IS a comment on the parent issue: that issue is
            # where its content is edited
            "issue_url": self.ctx["blog_repo_url"] + "/issues/" + str(entry["number"]),
            "description": "",
            "body": sub_body,
            # Sub pages carry giscus too; the parent's comments = false
            # opt-out applies to the whole series.
            "comments": entry["comments"],
            # _decorate_body may have appended alert CSS / MathJax to the
            # entry copies; ctx["style"] would silently drop them.
            "style": entry["style"],
            "script": entry["script"],
            "head": self.ctx["head"],
            "top": 0,
            "created_date": kept["created_date"],
            "date_label_color": kept["date_label_color"],
            "updated_date": kept["created_date"],
            "labels": entry["labels"],
            "footer_text": self.ctx["footer_text"],
            "highlight": 0,
            # Sub pages now carry the full series listing too (top + bottom
            # of the page), not just crumb/pager.
            "series": {
                "title": entry["post_title"],
                "parts": [
                    {"title": s["title"], "url": s["url"]} for s in entry["subs"]
                ],
            }
            if entry.get("subs")
            else None,
            "series_crumb": crumb,
            "series_pager": pager,
        }

        # Same code-block detection as _create_post: highlight=1 pages link
        # the starry-night stylesheet and the code-copy plugin needs its
        # copy/check glyphs in window.icons.
        if '<pre class="notranslate">' in sub_body:
            if '<div class="highlight' in sub_body:
                page["post"]["highlight"] = 1
            else:
                page["post"]["highlight"] = 2
        keys = ["sun", "moon", "sync", "home", "github", "rss", "pencil"]
        if page["post"]["highlight"] != 0:
            keys.extend(["copy", "check"])
        # FAB buttons live on every post page (toc overlay + scroll), so
        # their glyphs must reach window.icons here as well.
        keys.extend(["search", "tag", "bars", "arrow-up", "arrow-down"])
        icon_list = {key: ICONS.get(key) for key in keys}
        context = {
            "site": page,
            "post": page["post"],
            "post_list": {},
            "i18n": self.i18n,
            "icons": icon_list,
        }
        self.renderer.render_to("post", context, Path(kept["html_dir"]))
        print("create sub post %s" % kept["url"])

    def _render_body(self, body: str) -> str:
        """Render markdown to HTML, reusing the previous build's result.

        The key is a hash of the *stripped* body, so editing front matter
        invalidates the entry even though the prose is untouched, and the
        cache is safe to keep across full rebuilds. Without this, a full
        build spends one GitHub /markdown call per post even when nothing
        changed - which is every scheduled run.
        """
        key = hashlib.sha256(body.encode("utf-8")).hexdigest()
        cached = self.render_cache.get(key)
        if cached is not None:
            self.render_cache_used.add(key)
            return cached
        html = self.markdown(body)
        self.render_cache[key] = html
        self.render_cache_used.add(key)
        return html

    # ---------------------------------------------------------------- pages

    def _decorate_body(self, entry, post_body):
        """Post-process rendered markdown for BOTH parent and sub pages.

        Three GitHub-look fixes the /markdown API output still needs:
        - math: <math-renderer> wrappers are stripped and MathJax loaded;
        - alerts: the markdown-alert markup ships unstyled, so the colour
          CSS is injected per type actually present in the body;
        - emoji: the API does not convert :shortcode:, so shortcodes are
          replaced with GitHub's emoji images (see _load_emoji_map).
        Mutates entry["style"]/entry["script"]; returns the new body.
        """
        if "<math-renderer" in post_body:
            post_body = re.sub(r"<math-renderer.*?>", "", post_body)
            post_body = re.sub(r"</math-renderer>", "", post_body)
            entry["script"] = entry["script"] + MATHJAX_SCRIPT

        if '<p class="markdown-alert-title">' in post_body:
            entry["style"] = entry["style"] + ALERT_BASE_STYLE
            for alert, style in ALERT_STYLES.items():
                if f"markdown-alert-{alert}" in post_body:
                    entry["style"] += (
                        f".markdown-alert.markdown-alert-{alert} {{"
                        f"border-left-color:var(--borderColor-{style}-emphasis,"
                        f" var(--color-{style}-emphasis));"
                        f"background-color:var(--color-{style}-subtle);}}"
                        f".markdown-alert.markdown-alert-{alert} "
                        f".markdown-alert-title {{"
                        f"color: var(--fgColor-{style},"
                        f"var(--color-{style}-fg));}}"
                    )

        if ":" in post_body and self.emoji_map:
            post_body = re.sub(
                r":([a-z0-9_+-]+):",
                lambda m: self.emoji_map.get(
                    m.group(1), m.group(0)
                ),
                post_body,
            )

        return post_body

    def _load_emoji_map(self):
        """Load the :shortcode: -> <img> mapping for emoji inlining.

        The GitHub /markdown endpoint leaves emoji shortcodes untouched
        (only github.com pages convert them), so the generator does the
        conversion itself from the public emoji API list, cached in
        internote.json like the other downloads. A failure only warns:
        pages then show the raw shortcode instead of the image.
        """
        if self.state_path.exists():
            try:
                cached = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(cached.get("emoji_map"), dict) and cached["emoji_map"]:
                    self.emoji_map = cached["emoji_map"]
                    return
            except json.JSONDecodeError:
                pass
        try:
            request = urllib.request.Request(
                "https://api.github.com/emojis",
                headers={"User-Agent": "Internote"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
            self.emoji_map = {
                name: '<img class="emoji" alt=":{}:" height="20" width="20" src="{}">'.format(
                    name, url
                )
                for name, url in raw.items()
            }
            print("create emoji map:", len(self.emoji_map), "shortcodes")
        except Exception as error:  # noqa: BLE001 - never fail the build
            print("warning: emoji map download failed ({}); "
                  "emoji shortcodes stay as text".format(error))
            self.emoji_map = {}

    def _create_post(self, entry):
        md_path = self.sources_dir / f"{entry['number']}.md"
        post_body = self._render_body(md_path.read_text(encoding="utf-8"))
        post_body = self._decorate_body(entry, post_body)

        page = dict(self.ctx)
        page["post"] = {
            "title": entry["post_title"],
            "url": self.ctx["home_url"] + "/" + entry["post_url"],
            "issue_url": self.ctx["blog_repo_url"] + "/issues/" + str(entry["number"]),
            "description": entry["description"],
            "body": post_body,
            "comments": entry["comments"],
            "style": entry["style"],
            "script": entry["script"],
            "head": entry["head"],
            "top": entry["top"],
            "created_date": entry["created_date"],
            "date_label_color": entry["date_label_color"],
            "updated_date": entry["updated_date"],
            "labels": entry["labels"],
            "footer_text": self.ctx["footer_text"],
            "highlight": 0,
            # All three series keys exist on every post page (None when
            # not applicable): the renderer uses StrictUndefined, so even
            # an `{% if %}` truth test on a missing key would raise.
            "series": {
                "title": entry["post_title"],
                "parts": [
                    {"title": s["title"], "url": s["url"]} for s in entry["subs"]
                ],
            }
            if entry.get("subs")
            else None,
            "series_crumb": None,
            "series_pager": None,
        }

        if '<pre class="notranslate">' in post_body:
            if '<div class="highlight' in post_body:
                page["post"]["highlight"] = 1
            else:
                page["post"]["highlight"] = 2
            keys = ["sun", "moon", "sync", "home", "github", "rss", "pencil", "copy", "check"]
        else:
            page["post"]["highlight"] = 0
            keys = ["sun", "moon", "sync", "home", "github", "rss", "pencil"]

        # Every page header links to the tag cloud, so `tag` is never optional,
        # and the nav search button needs its magnifier glyph since search.js
        # fetches the local index on every page. FAB buttons live on post
        # pages only (toc + scroll up/down).
        keys.extend(["search", "tag", "bars", "arrow-up", "arrow-down"])

        icon_list = {key: ICONS.get(key) for key in keys}
        context = {
            "site": page,
            "post": page["post"],
            "post_list": {},
            "i18n": self.i18n,
            "icons": icon_list,
        }
        self.renderer.render_to("post", context, entry["html_dir"])
        print(
            "create postPage title=%s file=%s"
            % (entry["post_title"], entry["html_dir"])
        )

        alias_dir = entry.get("alias_dir")
        if alias_dir:
            # `slug` mints a root-level alias that redirects to the canonical
            # post/<id>.html page: meta refresh covers no-JS crawlers,
            # location.replace covers everything else, canonical+noindex
            # keep the alias itself out of search results.
            target = self.ctx["home_url"] + "/" + entry["post_url"]
            alias_context = {
                "site": self.ctx,
                "post": {"title": entry["post_title"], "url": target},
            }
            self.renderer.render_to("alias", alias_context, Path(alias_dir))
            print(
                "create alias %s -> %s"
                % (Path(alias_dir).name, entry["post_url"])
            )

    def _create_lists(self):
        nav_keys = ["sun", "moon", "sync", "tag", "search", "rss", "github", "upload", "post"]
        nav_icon = {key: ICONS.get(key) for key in nav_keys}
        # tag.html does not link to itself, but its empty state and rows are
        # JS-built, so `tag` and `post` must both reach window.icons. The
        # index is JS-built too, so it needs `post`/`upload` for the cards.
        tag_icon = {
            key: ICONS.get(key)
            for key in ["sun", "moon", "sync", "home", "search", "tag", "post", "rss", "github"]
        }

        # The conventional `about` alias earns a nav link on the index.
        about = next(
            (e for e in self.ctx["post_list"].values() if e.get("slug") == "about"),
            None,
        )
        self.ctx["about"] = (
            {"url": about["post_url"], "title": about["post_title"]}
            if about
            else None
        )

        # index.html is a shell: the card list and pagination are rendered
        # client-side from search-index.json, so there is exactly one list
        # page no matter how many posts exist.
        self._render_list(self.dist_dir / "index.html", nav_icon)

        tag_context = {
            "site": self.ctx,
            "i18n": self.i18n,
            "icons": tag_icon,
        }
        self.renderer.render_to("tag", tag_context, self.dist_dir / "tag.html")
        print("create tag.html")

    def _render_list(self, html_dir, nav_icon):
        context = {
            "site": self.ctx,
            "i18n": self.i18n,
            "icons": nav_icon,
        }
        self.renderer.render_to("post-list", context, html_dir)
        print("create " + str(html_dir))

    # ----------------------------------------------------------------- feed

    def _create_feed(self):
        posts_sorted = dict(
            sorted(
                self.ctx["post_list"].items(),
                key=lambda item: item[1]["created_at"],
                reverse=False,
            )
        )
        entries = list(posts_sorted.values())
        new_xml = build_feed(self.ctx, entries)

        if self.old_feed and strip_build_date(new_xml) == strip_build_date(
            self.old_feed
        ):
            print("====== rss xml no update ======")
            (self.dist_dir / "rss.xml").write_text(
                self.old_feed, encoding="utf-8"
            )
            return

        print("====== create rss xml ======")
        (self.dist_dir / "rss.xml").write_text(new_xml, encoding="utf-8")

    # --------------------------------------------------------------- output

    def _finalize(self):
        # Drop cache entries for bodies that were not rendered this run, so
        # it cannot grow without bound as posts are edited or removed.
        pruned = {k: v for k, v in self.render_cache.items() if k in self.render_cache_used}
        self.render_cache = pruned
        state = {
            "post_list": self.ctx["post_list"],
            "render_cache": pruned,
            "favicon_src": self.favicon_src,
            "emoji_map": self.emoji_map,
        }
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )

        self._write_search_index()
        self._write_readme()

    def _write_search_index(self):
        """Write dist/search-index.json, the site's single client-side data file.

        Consumed by the search dialog (plugins/search.js), the homepage list
        (post-list.j2.html) and the tag page (tag.j2.html), so it carries
        everything the listings need: `{label_colors: {name: "#hex"}, posts:
        [{title, labels, date, date_color, top, url}]}` — no body text, no
        third-party service, no keys. Pinned posts sort first, then date
        descending, so every client renders the same order for free.
        """
        records = [
            {
                "title": entry["post_title"],
                "labels": entry["labels"],
                "date": entry["created_date"],
                "date_color": entry["date_label_color"],
                "top": entry.get("top", 0),
                "url": entry["post_url"],
                # Sub posts never enter the index themselves, but the card
                # shows a badge so readers know the series has more parts.
                "subs": len(entry.get("subs") or ()),
            }
            for entry in self.ctx["post_list"].values()
            # The `about` page already has a dedicated header nav button;
            # listing it again on the index, tag pages and search only
            # duplicates the entry point. Its canonical page, alias and
            # feed entry are unaffected.
            if entry.get("slug") != "about"
        ]
        records.sort(key=lambda r: (r["top"], r["date"]), reverse=True)
        index = {
            "label_colors": self.ctx["label_color_dict"],
            "posts": records,
        }
        (self.dist_dir / "search-index.json").write_text(
            json.dumps(index, ensure_ascii=False), encoding="utf-8"
        )

    def _write_readme(self):
        workspace = os.environ.get("GITHUB_WORKSPACE")
        if not workspace:
            return
        if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
            return

        words = sum(
            entry.get("word_count", 0)
            for entry in self.ctx["post_list"].values()
        )
        now = datetime.datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")
        home = self.ctx["home_url"]
        title = self.ctx["title"]
        text = f"""\
# {title}

> {home}

- 文章：{len(self.ctx['post_list'])} 篇 · [标签页]({home}/tag.html)
- 字数：{words}
- 构建：{now}

Powered by [Internote](https://github.com/interset-wq/InterNote)
"""
        (Path(workspace) / "README.md").write_text(
            text, encoding="utf-8"
        )
        print("====== update readme file ======")
