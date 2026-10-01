# -*- coding: utf-8 -*-
"""Generator behaviour, built entirely offline from a fixture repo."""
import json

import pytest

from internote import fixtures
from internote.config import load_config
from internote.generator import Generator

CONFIG = """
[site]
title = "Test"
sub_title = "sub"
avatar_url = "https://example.com/a.png"
home_url = "https://example.com"
language = "CN"
utc = 8

[layout]
posts_per_page = 10
single_labels = ["about"]
start_date = "2026-01-01"

[comments]
enabled = false
"""


class FakeLabel:
    def __init__(self, name, color="ededed"):
        self.name = name
        self.color = color


def write_config(tmp_path, extra=""):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG + extra, encoding="utf-8")
    return path


def make_repo(tmp_path, issues, labels=None):
    """Build a FixtureRepo from plain dicts."""
    data = {
        "repo": "owner/blog",
        "labels": [
            {"name": lb, "color": "ededed"} for lb in (labels or ["blog"])
        ],
        "issues": issues,
    }
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return fixtures.load_repo(path)


def issue(number=1, title="Title", body="Body text.", labels=("blog",), state="open"):
    return {
        "number": number,
        "title": title,
        "body": body,
        "body_html": "<p>{}</p>".format(body),
        "labels": [{"name": name, "color": "ededed"} for name in labels],
        "created_at": "2026-01-02T03:04:05Z",
        "updated_at": "2026-01-02T03:04:05Z",
        "comments_total": 0,
        "events": [],
        "state": state,
    }


def build(tmp_path, issues, labels=None, incremental=None):
    repo, markdown = make_repo(tmp_path, issues, labels)
    cfg = load_config(write_config(tmp_path))
    gen = Generator(cfg, repo, repo_name="owner/blog", markdown=markdown, root=tmp_path)
    if incremental:
        gen.run_one(incremental)
    else:
        gen.run_all()
    return gen


def state_of(tmp_path):
    return json.loads((tmp_path / "internote.json").read_text(encoding="utf-8"))


def index_of(tmp_path):
    return (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")


class TestEntryPlacement:
    def test_post_lands_in_post_list(self, tmp_path):
        build(tmp_path, [issue()])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]
        assert state_of(tmp_path)["single_list"] == {}

    def test_single_label_routes_to_single_list(self, tmp_path):
        build(tmp_path, [issue(labels=("about",))])
        assert state_of(tmp_path)["post_list"] == {}
        assert sorted(state_of(tmp_path)["single_list"]) == ["P1"]

    def test_unlabelled_issue_is_skipped(self, tmp_path):
        build(tmp_path, [issue(labels=())])
        assert state_of(tmp_path)["post_list"] == {}
        assert state_of(tmp_path)["single_list"] == {}

    def test_first_label_decides_single_page_routing(self, tmp_path):
        build(tmp_path, [issue(labels=("blog", "about"))])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]


class TestFrontMatterOverrides:
    def test_title_and_date_overridden(self, tmp_path):
        build(
            tmp_path,
            [issue(body='+++\ntitle = "Custom"\ndate = 2021-03-04T00:00:00+00:00\n+++\nBody.')],
        )
        entry = state_of(tmp_path)["post_list"]["P1"]
        assert entry["post_title"] == "Custom"
        assert entry["created_date"] == "2021-03-04"

    def test_date_falls_back_to_issue_created_at(self, tmp_path):
        build(tmp_path, [issue(body="+++\ntitle = 'x'\n+++\nBody.")])
        assert state_of(tmp_path)["post_list"]["P1"]["created_date"] == "2026-01-02"

    def test_delimiters_are_stripped_from_sources(self, tmp_path):
        build(tmp_path, [issue(body='+++\ntitle = "x"\n+++\nBody.')])
        written = (tmp_path / "sources" / "1.md").read_text(encoding="utf-8")
        assert not written.startswith("+++")

    def test_draft_post_is_not_published(self, tmp_path):
        build(tmp_path, [issue(body="+++\ndraft = true\n+++\nBody.")])
        assert state_of(tmp_path)["post_list"] == {}
        assert not (tmp_path / "dist" / "post" / "1.html").exists()


class TestWithdrawal:
    """A post that stops being published must disappear everywhere."""

    def _publish_then_rebuild(self, tmp_path, replacement):
        build(tmp_path, [issue(number=1, body="Body one.")])
        assert (tmp_path / "dist" / "post" / "1.html").exists()
        build(tmp_path, [replacement], incremental="1")
        return tmp_path

    def test_draft_removes_page_and_every_reference(self, tmp_path):
        self._publish_then_rebuild(
            tmp_path, issue(number=1, body="+++\ndraft = true\n+++\nBody one.")
        )
        assert not (tmp_path / "dist" / "post" / "1.html").exists()
        assert state_of(tmp_path)["post_list"] == {}
        assert "Body one." not in index_of(tmp_path)
        listing = (tmp_path / "dist" / "post-list.json").read_text(encoding="utf-8")
        assert '"P1"' not in listing
        rss = (tmp_path / "dist" / "rss.xml").read_text(encoding="utf-8")
        assert "post/1.html" not in rss

    def test_removing_the_last_label_removes_every_reference(self, tmp_path):
        self._publish_then_rebuild(tmp_path, issue(number=1, labels=()))
        assert not (tmp_path / "dist" / "post" / "1.html").exists()
        assert state_of(tmp_path)["post_list"] == {}
        assert '"P1"' not in (tmp_path / "dist" / "post-list.json").read_text(
            encoding="utf-8"
        )

    def test_closed_issue_removes_every_reference(self, tmp_path):
        self._publish_then_rebuild(tmp_path, issue(number=1, state="closed"))
        assert not (tmp_path / "dist" / "post" / "1.html").exists()
        assert state_of(tmp_path)["post_list"] == {}

    def test_single_page_withdrawal_also_cleans_up(self, tmp_path):
        build(tmp_path, [issue(labels=("about",))])
        assert (tmp_path / "dist" / "about.html").exists()
        build(
            tmp_path,
            [issue(labels=("about",), body="+++\ndraft = true\n+++\nBody.")],
            incremental="1",
        )
        assert not (tmp_path / "dist" / "about.html").exists()
        assert state_of(tmp_path)["single_list"] == {}

    def test_republishing_restores_the_post(self, tmp_path):
        build(tmp_path, [issue()])
        build(tmp_path, [issue(body="+++\ndraft = true\n+++\nBody.")], incremental="1")
        assert state_of(tmp_path)["post_list"] == {}
        build(tmp_path, [issue()], incremental="1")
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]
        assert (tmp_path / "dist" / "post" / "1.html").exists()


class TestIncrementalKeepsOthers:
    def test_other_posts_survive_an_incremental_rebuild(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2)])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1", "P2"]
        build(tmp_path, [issue(number=1), issue(number=2)], incremental="1")
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1", "P2"]
        assert (tmp_path / "dist" / "post" / "2.html").exists()
