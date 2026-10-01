# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
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

POST_LIST_FIELDS = {
    "post_title",
    "post_url",
    "labels",
    "created_date",
    "date_label_color",
    "comment_num",
    "top",
}


def _list_item(entry: dict) -> dict:
    """Convert a stored entry to the template's list-item shape."""
    return {
        "title": entry["post_title"],
        "url": entry["post_url"],
        "labels": entry["labels"],
        "created_date": entry["created_date"],
        "date_label_color": entry["date_label_color"],
        "comment_num": entry.get("comment_num", 0),
        "top": entry.get("top", 0),
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

    # ------------------------------------------------------------------ run

    def run_all(self):
        print("====== start create static html ======")
        self._clean()
        for issue in self.repo.get_issues():
            self._add_entry(issue)
        for entry in list(self.ctx["post_list"].values()):
            self._create_post(entry)
        for entry in list(self.ctx["single_list"].values()):
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
        self.ctx["post_list"] = data.get("post_list", {})
        self.ctx["single_list"] = data.get("single_list", {})

    def _drop_entry(self, number: int, reason: str) -> bool:
        """Withdraw a post: remove its page and its entry from the state.

        Called when an issue stops qualifying for publication - closed,
        stripped of its last label, or marked draft. Without this the
        homepage, the search index and the feed keep pointing at a page
        that no longer exists.
        """
        key = f"P{number}"
        for list_name in ("post_list", "single_list"):
            entry = self.ctx[list_name].get(key)
            if entry is None:
                continue
            page = Path(entry["html_dir"])
            if page.exists():
                page.unlink()
            del self.ctx[list_name][key]
            print("withdraw #{} ({}): {}".format(number, reason, entry["html_dir"]))
            return True
        return False

    # -------------------------------------------------------------- entries

    def _add_entry(self, issue):
        if len(issue.labels) < 1:
            self._drop_entry(issue.number, "no labels")
            return None
        labels = [label.name for label in issue.labels]

        if labels[0] in self.ctx["single_labels"]:
            list_name = "single_list"
            file_name = re.sub(r'[<>:/\\|?*\"]|[\0-\31]', "-", labels[0])
            html_dir = self.dist_dir / f"{file_name}.html"
        else:
            list_name = "post_list"
            html_dir = self.post_dir / f"{issue.number}.html"

        post_url = urllib.parse.quote(
            html_dir.relative_to(self.dist_dir).as_posix()
        )

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

        entry = {
            "number": issue.number,
            "html_dir": str(html_dir),
            "labels": labels,
            "post_title": meta.get("title") or issue.title,
            "post_url": post_url,
            "source_url": f"https://github.com/{self.repo_name}/issues/{issue.number}",
            "comment_num": issue.get_comments().totalCount,
            "word_count": len(body),
            "top": 0,
            "style": self.ctx["style"] + meta.get("style", ""),
            "script": self.ctx["script"] + meta.get("script", ""),
            "head": self.ctx["head"] + meta.get("head", ""),
        }

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

        self.ctx[list_name][f"P{issue.number}"] = entry
        return entry

    # ---------------------------------------------------------------- pages

    def _create_post(self, entry):
        md_path = self.sources_dir / f"{entry['number']}.md"
        post_body = self.markdown(md_path.read_text(encoding="utf-8"))

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
            "style": entry["style"],
            "script": entry["script"],
            "head": entry["head"],
            "top": entry["top"],
            "source_url": entry["source_url"],
            "created_date": entry["created_date"],
            "date_label_color": entry["date_label_color"],
            "updated_date": entry["updated_date"],
            "labels": entry["labels"],
            "footer_text": self.ctx["footer_text"],
            "highlight": 0,
        }

        if entry["labels"][0] in self.ctx["single_labels"]:
            page["post"]["footer_text"] = ""

        if '<pre class="notranslate">' in post_body:
            if '<div class="highlight' in post_body:
                page["post"]["highlight"] = 1
            else:
                page["post"]["highlight"] = 2
            keys = ["sun", "moon", "sync", "home", "github", "rss", "copy", "check"]
        else:
            page["post"]["highlight"] = 0
            keys = ["sun", "moon", "sync", "home", "github", "rss"]

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

    def _create_lists(self):
        posts = dict(
            sorted(
                self.ctx["post_list"].items(),
                key=lambda item: (item[1]["top"], item[1]["created_at"]),
                reverse=True,
            )
        )
        nav_keys = ["sun", "moon", "sync", "search", "rss", "github", "upload", "post"]
        nav_keys = list(
            dict.fromkeys(nav_keys + self.ctx["single_labels"])
        )
        nav_icon = {key: ICONS.get(key) for key in nav_keys}
        tag_icon = {
            key: ICONS.get(key)
            for key in ["sun", "moon", "sync", "home", "search", "post", "rss", "github"]
        }

        page_size = self.ctx["posts_per_page"]
        post_num = len(posts)
        page_flag = 0
        while True:
            top_num = page_flag * page_size
            print("topNum=%d postNum=%d" % (top_num, post_num))
            if post_num <= page_size:
                if page_flag == 0:
                    one_page = dict(list(posts.items())[:post_num])
                    html_dir = self.dist_dir / "index.html"
                    self.ctx["prev_url"] = "disabled"
                    self.ctx["next_url"] = "disabled"
                else:
                    one_page = dict(
                        list(posts.items())[top_num : top_num + post_num]
                    )
                    html_dir = self.dist_dir / f"page{page_flag + 1}.html"
                    self.ctx["prev_url"] = (
                        "/index.html"
                        if page_flag == 1
                        else f"/page{page_flag}.html"
                    )
                    self.ctx["next_url"] = "disabled"
                self._render_list(one_page, html_dir, nav_icon)
                break
            else:
                one_page = dict(
                    list(posts.items())[top_num : top_num + page_size]
                )
                post_num = post_num - page_size
                if page_flag == 0:
                    html_dir = self.dist_dir / "index.html"
                    self.ctx["prev_url"] = "disabled"
                    self.ctx["next_url"] = "/page2.html"
                else:
                    html_dir = self.dist_dir / f"page{page_flag + 1}.html"
                    self.ctx["prev_url"] = (
                        "/index.html"
                        if page_flag == 1
                        else f"/page{page_flag}.html"
                    )
                    self.ctx["next_url"] = f"/page{page_flag + 2}.html"
                self._render_list(one_page, html_dir, nav_icon)
            page_flag = page_flag + 1

        tag_context = {
            "site": self.ctx,
            "posts": {k: _list_item(v) for k, v in one_page.items()},
            "i18n": self.i18n,
            "icons": tag_icon,
        }
        self.renderer.render_to("tag", tag_context, self.dist_dir / "tag.html")
        print("create tag.html")

    def _render_list(self, one_page, html_dir, nav_icon):
        context = {
            "site": self.ctx,
            "posts": {k: _list_item(v) for k, v in one_page.items()},
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
        entries = list(self.ctx["single_list"].values()) + list(
            posts_sorted.values()
        )
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
        state = {
            "post_list": self.ctx["post_list"],
            "single_list": self.ctx["single_list"],
        }
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )

        stripped = {
            key: {field: value for field, value in entry.items() if field in POST_LIST_FIELDS}
            for key, entry in self.ctx["post_list"].items()
        }
        stripped["label_color_dict"] = self.ctx["label_color_dict"]
        (self.dist_dir / "post-list.json").write_text(
            json.dumps(stripped, ensure_ascii=False), encoding="utf-8"
        )

        self._write_readme()

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
