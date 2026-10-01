# -*- coding: utf-8 -*-
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from internote.config import load_config
from internote.generator import Generator

REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG_TOML = """
[site]
title = "TestBlog"
sub_title = "sub title"
avatar_url = "https://example.com/a.png"
language = "CN"

[layout]
posts_per_page = 15
single_labels = ["about"]
footer_text = "BOTTOM"

[features]
visit_counter = "vercount"
"""


class FakeIssue:
    def __init__(
        self,
        number,
        title,
        body,
        labels=("daily",),
        created_at=None,
        state="open",
        pinned=False,
        comments=0,
        updated_at=None,
    ):
        self.number = number
        self.title = title
        self.body = body
        self.state = state
        self.labels = [SimpleNamespace(name=n, color="ff0000") for n in labels]
        self.created_at = created_at or datetime(
            2026, 1, number, tzinfo=timezone.utc
        )
        self.updated_at = updated_at or self.created_at
        self._pinned = pinned
        self._comments = comments

    def get_events(self):
        if self._pinned:
            return [SimpleNamespace(event="pinned")]
        return []

    def get_comments(self):
        return SimpleNamespace(totalCount=self._comments)


class FakeRepo:
    def __init__(self, issues, name="InterNote", owner="interset-wq"):
        self.name = name
        self.owner = SimpleNamespace(login=owner)
        self.issues = list(issues)

    def get_labels(self):
        return [SimpleNamespace(name="daily", color="0969da")]

    def get_issues(self):
        return self.issues

    def get_issue(self, number):
        for issue in self.issues:
            if issue.number == number:
                return issue
        raise KeyError(number)


@pytest.fixture
def workspace(tmp_path: Path):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    (tmp_path / "config.toml").write_text(CONFIG_TOML, encoding="utf-8")
    return tmp_path


def make_generator(root: Path, repo: FakeRepo) -> Generator:
    config = load_config(root / "config.toml")
    return Generator(
        config,
        repo,
        repo_name=f"{repo.owner.login}/{repo.name}",
        markdown=lambda text: f"<p>{text}</p>",
        root=root,
    )


def two_post_repo():
    return FakeRepo(
        [
            FakeIssue(3, "First Post", "第一句。second sentence"),
            FakeIssue(7, "Second Post", "hello world"),
        ]
    )


def test_run_all_generates_full_site(workspace: Path):
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    dist = workspace / "dist"
    assert (dist / "post" / "3.html").exists()
    assert (dist / "post" / "7.html").exists()
    assert (dist / "index.html").exists()
    assert (dist / "tag.html").exists()
    assert (dist / "rss.xml").exists()
    assert (dist / "post-list.json").exists()
    assert (workspace / "internote.json").exists()
    assert (workspace / "sources" / "3.md").read_text(encoding="utf-8") == (
        "第一句。second sentence"
    )
    index = (dist / "index.html").read_text(encoding="utf-8")
    assert "First Post" in index
    assert "Second Post" in index


def test_post_list_urls_use_issue_number(workspace: Path):
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    data = json.loads(
        (workspace / "dist" / "post-list.json").read_text(encoding="utf-8")
    )
    assert data["P3"]["post_url"] == "post/3.html"
    assert data["P7"]["post_url"] == "post/7.html"
    assert data["P3"]["post_title"] == "First Post"
    assert "postTitle" not in data["P3"]
    assert "html_dir" not in data["P3"]
    assert "description" not in data["P3"]
    assert data["label_color_dict"] == {"daily": "#0969da"}


def test_state_keeps_full_entries(workspace: Path):
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    state = json.loads((workspace / "internote.json").read_text(encoding="utf-8"))
    entry = state["post_list"]["P3"]
    html_dir = Path(entry["html_dir"])
    assert html_dir.parent.name == "post"
    assert html_dir.name == "3.html"
    assert entry["description"] == "第一句。"
    assert entry["word_count"] == len("第一句。second sentence")
    assert entry["comment_num"] == 0


def test_pagination(workspace: Path):
    cfg_path = workspace / "config.toml"
    cfg_path.write_text(
        CONFIG_TOML.replace("posts_per_page = 15", "posts_per_page = 1"),
        encoding="utf-8",
    )
    repo = FakeRepo(
        [
            FakeIssue(1, "Alpha", "a"),
            FakeIssue(2, "Beta", "b"),
            FakeIssue(3, "Gamma", "c"),
        ]
    )
    gen = make_generator(workspace, repo)
    gen.run_all()

    dist = workspace / "dist"
    assert (dist / "index.html").exists()
    assert (dist / "page2.html").exists()
    assert (dist / "page3.html").exists()
    index = (dist / "index.html").read_text(encoding="utf-8")
    assert "/page2.html" in index
    assert "Gamma" in index  # newest first
    assert "Alpha" not in index


def test_single_page_generated(workspace: Path):
    repo = FakeRepo(
        [
            FakeIssue(3, "Post", "body", labels=("daily",)),
            FakeIssue(4, "About Me", "about body", labels=("about",)),
        ]
    )
    gen = make_generator(workspace, repo)
    gen.run_all()

    dist = workspace / "dist"
    assert (dist / "about.html").exists()
    assert not (dist / "post" / "4.html").exists()
    about = (dist / "about.html").read_text(encoding="utf-8")
    post = (dist / "post" / "3.html").read_text(encoding="utf-8")
    assert "BOTTOM" not in about  # single page clears bottom_text
    assert "BOTTOM" in post
    state = json.loads((workspace / "internote.json").read_text(encoding="utf-8"))
    assert "P4" in state["single_list"]
    assert "P4" not in state["post_list"]


def test_pinned_post_sorts_first(workspace: Path):
    repo = FakeRepo(
        [
            FakeIssue(1, "Older Pinned", "x", pinned=True),
            FakeIssue(9, "Newer Normal", "y"),
        ]
    )
    gen = make_generator(workspace, repo)
    gen.run_all()

    index = (workspace / "dist" / "index.html").read_text(encoding="utf-8")
    assert index.index("Older Pinned") < index.index("Newer Normal")


def test_run_one_updates_single_post(workspace: Path):
    repo = two_post_repo()
    gen = make_generator(workspace, repo)
    gen.run_all()

    repo.issues.append(FakeIssue(9, "Third Post", "new body"))
    gen2 = make_generator(workspace, repo)
    gen2.run_one("9")

    assert (workspace / "dist" / "post" / "9.html").exists()
    index = (workspace / "dist" / "index.html").read_text(encoding="utf-8")
    assert "Third Post" in index
    state = json.loads((workspace / "internote.json").read_text(encoding="utf-8"))
    assert set(state["post_list"]) == {"P3", "P7", "P9"}


def test_run_one_skips_closed_issue(workspace: Path):
    repo = FakeRepo([FakeIssue(3, "Closed", "x", state="closed")])
    gen = make_generator(workspace, repo)
    gen.run_one("3")
    assert not (workspace / "dist" / "post" / "3.html").exists()


def test_plugins_and_static_copied_to_dist(workspace: Path):
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    assert (workspace / "dist" / "plugins" / "tocbot.js").exists()
    assert (workspace / "dist" / "plugins" / "vercount.js").exists()
    assert (workspace / "dist" / "robots.txt").exists()


def test_features_enabled_in_html(workspace: Path):
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    home = "https://interset-wq.github.io/InterNote"
    post = (workspace / "dist" / "post" / "3.html").read_text(encoding="utf-8")
    index = (workspace / "dist" / "index.html").read_text(encoding="utf-8")
    assert f"{home}/plugins/tocbot.js" in post
    assert f"{home}/plugins/vercount.js" in index
    assert "giscus.app" not in post  # giscus not configured in test config


def test_readme_stats_written(workspace: Path, monkeypatch):
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    readme = (workspace / "README.md").read_text(encoding="utf-8")
    assert "# TestBlog" in readme
    assert "tag.html" in readme
    assert "Powered by" in readme
    assert "Internote" in readme


def test_readme_skipped_on_schedule(workspace: Path, monkeypatch):
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    gen = make_generator(workspace, two_post_repo())
    gen.run_all()

    assert not (workspace / "README.md").exists()


def test_timestamp_override_from_body(workspace: Path):
    body = 'intro text\n## {"timestamp": 1700000000}'
    repo = FakeRepo([FakeIssue(5, "Dated", body)])
    gen = make_generator(workspace, repo)
    gen.run_all()

    state = json.loads((workspace / "internote.json").read_text(encoding="utf-8"))
    assert state["post_list"]["P5"]["created_at"] == 1700000000
    # UTC+8: 1700000000 -> 2023-11-15
    assert state["post_list"]["P5"]["created_date"] == "2023-11-15"


def test_updated_date_from_issue(workspace: Path):
    updated = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)
    repo = FakeRepo([FakeIssue(5, "Edited", "body", updated_at=updated)])
    gen = make_generator(workspace, repo)
    gen.run_all()

    state = json.loads((workspace / "internote.json").read_text(encoding="utf-8"))
    entry = state["post_list"]["P5"]
    assert entry["updated_at"] == int(updated.timestamp())
    # UTC+8: 2026-03-15 09:30 -> 17:30 same day
    assert entry["updated_date"] == "2026-03-15"


def test_unlabeled_issue_is_skipped(workspace: Path):
    repo = FakeRepo([FakeIssue(6, "No Label", "x", labels=())])
    gen = make_generator(workspace, repo)
    gen.run_all()

    assert not (workspace / "dist" / "post" / "6.html").exists()
    state = json.loads((workspace / "internote.json").read_text(encoding="utf-8"))
    assert state["post_list"] == {}


def test_run_all_with_no_issues_creates_sources_dir(workspace: Path):
    gen = make_generator(workspace, FakeRepo([]))
    gen.run_all()

    assert (workspace / "sources").is_dir()
    assert (workspace / "dist" / "index.html").exists()
    assert (workspace / "internote.json").exists()


def test_run_one_on_virgin_workspace_sets_up_full_site(workspace: Path):
    repo = FakeRepo([FakeIssue(3, "First", "body")])
    gen = make_generator(workspace, repo)
    gen.run_one("3")

    dist = workspace / "dist"
    assert (dist / "post" / "3.html").exists()
    assert (dist / "index.html").exists()
    assert (dist / "plugins" / "tocbot.js").exists()
    assert (dist / "rss.xml").exists()
    assert (workspace / "sources" / "3.md").exists()


def test_run_one_recreates_sources_dir_when_missing(workspace: Path):
    repo = two_post_repo()
    gen = make_generator(workspace, repo)
    gen.run_all()
    # 空 sources 目录不会被 git 追踪，模拟检出后缺失
    shutil.rmtree(workspace / "sources")

    repo.issues.append(FakeIssue(6, "No Label", "x", labels=()))
    gen2 = make_generator(workspace, repo)
    gen2.run_one("6")

    assert (workspace / "sources").is_dir()


def test_footer_icon_keys_and_blog_repo_url(workspace: Path):
    repo = two_post_repo()
    gen = make_generator(workspace, repo)
    gen.run_all()

    assert gen.ctx["blog_repo_url"] == "https://github.com/interset-wq/InterNote"

    index = (workspace / "dist" / "index.html").read_text(encoding="utf-8")
    post = (workspace / "dist" / "post" / "3.html").read_text(encoding="utf-8")
    tag = (workspace / "dist" / "tag.html").read_text(encoding="utf-8")

    assert 'id="icon-github"' in index
    assert 'id="icon-rss"' in index
    assert "window.icons" in index
    assert "window.icons" in post
    assert "window.icons" in tag


def test_tocbot_placeholder_not_full_viewport():
    src = (REPO_ROOT / "src" / "internote" / "plugins" / "tocbot.js").read_text(
        encoding="utf-8"
    )
    assert "window.innerHeight + 'px'" not in src


def test_toc_not_created_without_headings():
    src = (REPO_ROOT / "src" / "internote" / "plugins" / "tocbot.js").read_text(
        encoding="utf-8"
    )
    assert "if (headings.length > 0)" in src
