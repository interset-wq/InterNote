# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import urllib.parse
from pathlib import Path

from . import frontmatter
from .config import InternoteConfig
from .constants import ICONS, get_i18n
from .feed import build_feed, strip_build_date
from .frontmatter import FrontMatterError
from .renderer import Renderer

MATHJAX_SCRIPT = (
    '<script>MathJax = {tex: {inlineMath: [["$", "$"]]}};</script>'
    '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>'
)

ALERT_BASE_STYLE = (
    "<style>.markdown-alert{padding:0.5rem 1rem;margin-bottom:1rem;"
    "border-left:.25em solid var(--borderColor-default,var(--color-border-default));}"
    ".markdown-alert .markdown-alert-title {display:flex;"
    "font-weight:var(--base-text-weight-medium,500);align-items:center;line-height:1;}"
    ".markdown-alert>:first-child {margin-top:0;}"
    ".markdown-alert>:last-child {margin-bottom:0;}</style>"
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
        print("GitHub Pages URL: ", self.ctx["home_url"])

        self.tz = datetime.timezone(datetime.timedelta(hours=self.ctx["utc"]))
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
        if self.state_path.exists():
            try:
                cached = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cached = {}
            if isinstance(cached.get("render_cache"), dict):
                self.render_cache = cached["render_cache"]

    # ------------------------------------------------------------------ run

    def run_all(self):
        print("====== start create static html ======")
        self._clean()
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
            "post_title": meta.get("title") or issue.title,
            "post_url": post_url,
            "comment_num": issue.get_comments().totalCount,
            "word_count": len(body),
            "top": 0,
            # Default is on: a page opts out with `comments = false`.
            "comments": not meta.get("comments") is False,
            "style": self.ctx["style"] + meta.get("style", ""),
            "script": self.ctx["script"] + meta.get("script", ""),
            "head": self.ctx["head"] + meta.get("head", ""),
        }
        if alias_dir is not None:
            entry["slug"] = file_name
            entry["alias_dir"] = str(alias_dir)

        if meta.get("description"):
            entry["description"] = meta["description"]
        elif body:
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

    def _create_post(self, entry):
        md_path = self.sources_dir / f"{entry['number']}.md"
        post_body = self._render_body(md_path.read_text(encoding="utf-8"))

        if "<math-renderer" in post_body:
            post_body = re.sub(r"<math-renderer.*?>", "", post_body)
            post_body = re.sub(r"</math-renderer>", "", post_body)
            entry["script"] = entry["script"] + MATHJAX_SCRIPT

        if '<p class="markdown-alert-title">' in post_body:
            entry["style"] = entry["style"] + ALERT_BASE_STYLE
            for alert, style in ALERT_STYLES.items():
                if f"markdown-alert-{alert}" in post_body:
                    entry["style"] += (
                        f"<style>.markdown-alert.markdown-alert-{alert} {{"
                        f"border-left-color:var(--borderColor-{style}-emphasis,"
                        f" var(--color-{style}-emphasis));"
                        f"background-color:var(--color-{style}-subtle);}}"
                        f".markdown-alert.markdown-alert-{alert} "
                        f".markdown-alert-title {{"
                        f"color: var(--fgColor-{style},"
                        f"var(--color-{style}-fg));}}</style>"
                    )

        page = dict(self.ctx)
        page["post"] = {
            "title": entry["post_title"],
            "url": self.ctx["home_url"] + "/" + entry["post_url"],
            "description": entry["description"],
            "body": post_body,
            "comment_num": entry["comment_num"],
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
        }

        if '<pre class="notranslate">' in post_body:
            if '<div class="highlight' in post_body:
                page["post"]["highlight"] = 1
            else:
                page["post"]["highlight"] = 2
            keys = ["sun", "moon", "sync", "home", "github", "rss", "copy", "check"]
        else:
            page["post"]["highlight"] = 0
            keys = ["sun", "moon", "sync", "home", "github", "rss"]

        # Every page header links to the tag cloud, so `tag` is never optional,
        # and the nav search button needs its magnifier glyph since search.js
        # fetches the local index on every page.
        keys.extend(["search", "tag"])

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
            }
            for entry in self.ctx["post_list"].values()
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

        comments = sum(
            entry.get("comment_num", 0)
            for entry in self.ctx["post_list"].values()
        )
        words = sum(
            entry.get("word_count", 0)
            for entry in self.ctx["post_list"].values()
        )
        now = datetime.datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")
        home = self.ctx["home_url"]
        lines = [
            f"# {self.ctx['title']} :link: {home} \r\n",
            f"### :page_facing_up: [{len(self.ctx['post_list'])}]({home}/tag.html) \r\n",
            f"### :speech_balloon: {comments} \r\n",
            f"### :hibiscus: {words} \r\n",
            f"### :alarm_clock: {now} \r\n",
            "### Powered by :heart: [Internote]"
            "(https://github.com/interset-wq/InterNote)\r\n",
        ]
        (Path(workspace) / "README.md").write_text(
            "".join(lines), encoding="utf-8"
        )
        print("====== update readme file ======")
