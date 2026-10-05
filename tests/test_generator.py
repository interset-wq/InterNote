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


def issue(
    number=1,
    title="Title",
    body="Body text.",
    labels=("blog",),
    state="open",
    pull_request=False,
):
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
        "pull_request": pull_request,
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

    def test_about_url_routes_to_single_page(self, tmp_path):
        build(tmp_path, [issue(body='+++\nurl = "about"\n+++\nAbout.')])
        assert state_of(tmp_path)["post_list"] == {}
        assert sorted(state_of(tmp_path)["single_list"]) == ["P1"]
        assert (tmp_path / "dist" / "about.html").exists()

    def test_unlabelled_issue_publishes_as_default(self, tmp_path):
        # Labels are optional: a forgotten label must not silence a post.
        build(tmp_path, [issue(labels=())])
        entry = state_of(tmp_path)["post_list"]["P1"]
        assert entry["labels"] == ["default"]

    def test_url_slug_replaces_the_issue_number(self, tmp_path):
        build(tmp_path, [issue(body='+++\nurl = "hello"\n+++\nBody.')])
        entry = state_of(tmp_path)["post_list"]["P1"]
        assert entry["post_url"] == "post/hello.html"
        assert (tmp_path / "dist" / "post" / "hello.html").exists()

    def test_about_label_without_url_is_a_normal_post(self, tmp_path):
        # Routing is front-matter driven; the label name alone means nothing.
        build(tmp_path, [issue(labels=("about",))])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]
        assert state_of(tmp_path)["single_list"] == {}

    def test_empty_url_is_rejected(self, tmp_path):
        with pytest.raises(Exception, match="must not be empty"):
            build(tmp_path, [issue(body='+++\nurl = ""\n+++\nBody.')])

    def test_dot_url_is_rejected(self, tmp_path):
        with pytest.raises(Exception, match="url"):
            build(tmp_path, [issue(body='+++\nurl = ".hidden"\n+++\nBody.')])

    def test_moving_between_lists_cleans_the_old_location(self, tmp_path):
        build(tmp_path, [issue(body='+++\nurl = "about"\n+++\nBody.')])
        assert (tmp_path / "dist" / "about.html").exists()
        # the url front matter is removed: the page moves back under post/
        build(tmp_path, [issue()], incremental="1")
        assert state_of(tmp_path)["single_list"] == {}
        assert not (tmp_path / "dist" / "about.html").exists()
        assert (tmp_path / "dist" / "post" / "1.html").exists()


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
        listing = (tmp_path / "dist" / "search-index.json").read_text(encoding="utf-8")
        assert '"post/1.html"' not in listing
        rss = (tmp_path / "dist" / "rss.xml").read_text(encoding="utf-8")
        assert "post/1.html" not in rss

    def test_removing_all_labels_falls_back_to_default(self, tmp_path):
        self._publish_then_rebuild(tmp_path, issue(number=1, labels=()))
        assert (tmp_path / "dist" / "post" / "1.html").exists()
        assert state_of(tmp_path)["post_list"]["P1"]["labels"] == ["default"]

    def test_closed_issue_removes_every_reference(self, tmp_path):
        self._publish_then_rebuild(tmp_path, issue(number=1, state="closed"))
        assert not (tmp_path / "dist" / "post" / "1.html").exists()
        assert state_of(tmp_path)["post_list"] == {}

    def test_single_page_withdrawal_also_cleans_up(self, tmp_path):
        build(tmp_path, [issue(body='+++\nurl = "about"\n+++\nBody.')])
        assert (tmp_path / "dist" / "about.html").exists()
        build(
            tmp_path,
            [issue(body='+++\nurl = "about"\ndraft = true\n+++\nBody.')],
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


class TestRenderCache:
    """Rendering is the only network call in a build; unchanged posts must
    not be re-rendered."""

    def _counting_build(self, tmp_path, issues, root=None):
        calls = []

        def markdown(text):
            calls.append(text)
            return "<p>{}</p>".format(text)

        repo, _ = make_repo(tmp_path, issues)
        cfg = load_config(write_config(tmp_path))
        gen = Generator(
            cfg, repo, repo_name="owner/blog", markdown=markdown, root=root or tmp_path
        )
        return gen, calls

    def test_second_full_build_renders_nothing(self, tmp_path):
        issues = [issue(number=1, body="one"), issue(number=2, body="two")]
        gen, calls = self._counting_build(tmp_path, issues)
        gen.run_all()
        assert len(calls) == 2

        # same bodies, brand new Generator as a fresh process would have
        gen2, calls2 = self._counting_build(tmp_path, issues)
        gen2.run_all()
        assert calls2 == []

    def test_identical_bodies_render_once(self, tmp_path):
        gen, calls = self._counting_build(
            tmp_path, [issue(number=1, body="same"), issue(number=2, body="same")]
        )
        gen.run_all()
        assert calls == ["same"]

    def test_edited_body_is_re_rendered(self, tmp_path):
        self._counting_build(tmp_path, [issue(number=1, body="first")])[0].run_all()
        gen, calls = self._counting_build(tmp_path, [issue(number=1, body="second")])
        gen.run_all()
        assert calls == ["second"]

    def test_front_matter_change_does_not_re_render(self, tmp_path):
        # The key is a hash of the *stripped* body, and rendering only ever
        # sees the prose - head/style/script are applied from the entry
        # afterwards. So editing front matter costs no API call.
        plain = [issue(number=1, body="Same prose.")]
        self._counting_build(tmp_path, plain)[0].run_all()

        styled = [issue(number=1, body='+++\nstyle = ".x{}"\n+++\nSame prose.')]
        gen, calls = self._counting_build(tmp_path, styled)
        gen.run_all()
        assert calls == []
        # and the injection still applied
        assert ".x{}" in (tmp_path / "dist" / "post" / "1.html").read_text(
            encoding="utf-8"
        )

    def test_cache_is_pruned_to_entries_used_this_run(self, tmp_path):
        self._counting_build(
            tmp_path, [issue(number=1, body="one"), issue(number=2, body="two")]
        )[0].run_all()
        assert len(state_of(tmp_path)["render_cache"]) == 2

        # post 2 removed, so its cached html must not linger
        self._counting_build(tmp_path, [issue(number=1, body="one")])[0].run_all()
        assert len(state_of(tmp_path)["render_cache"]) == 1

    def test_withdrawn_post_drops_its_cache_entry(self, tmp_path):
        self._counting_build(tmp_path, [issue(number=1, body="one")])[0].run_all()
        assert len(state_of(tmp_path)["render_cache"]) == 1
        self._counting_build(
            tmp_path, [issue(number=1, body="+++\ndraft = true\n+++\none")]
        )[0].run_all()
        assert state_of(tmp_path)["render_cache"] == {}

    def test_corrupt_state_does_not_break_the_build(self, tmp_path):
        self._counting_build(tmp_path, [issue(number=1, body="one")])[0].run_all()
        (tmp_path / "internote.json").write_text("{ not json", encoding="utf-8")
        gen, _ = self._counting_build(tmp_path, [issue(number=1, body="one")])
        gen.run_all()
        # the cache is discarded rather than crashing, and the page is built
        assert (tmp_path / "dist" / "post" / "1.html").exists()
        assert "P1" in state_of(tmp_path)["post_list"]


class TestPullRequestsAreNotPosts:
    """get_issues() returns pull requests as well as issues. scripts/
    fetch_fixtures.py has always filtered them; the live path did not, so a PR
    would be published *and* pushed into the search index."""

    def test_pull_request_is_skipped_on_a_full_build(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2, pull_request=True)])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]
        assert not (tmp_path / "dist" / "post" / "2.html").exists()

    def test_pull_request_is_not_in_the_listing(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2, title="PR", pull_request=True)])
        assert "PR" not in index_of(tmp_path)

    def test_pull_request_is_not_in_the_feed(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2, title="PR", pull_request=True)])
        rss = (tmp_path / "dist" / "rss.xml").read_text(encoding="utf-8")
        assert "PR" not in rss

    def test_pull_request_is_not_in_the_search_index(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2, title="PR", pull_request=True)])
        index = json.loads(
            (tmp_path / "dist" / "search-index.json").read_text(encoding="utf-8")
        )
        assert all(record["title"] != "PR" for record in index["posts"])

    def test_a_pull_request_with_the_about_slug_is_still_skipped(self, tmp_path):
        """Routing happens after the PR check, so a PR carrying
        `url = "about"` could otherwise have claimed about.html."""
        build(
            tmp_path,
            [issue(number=1, pull_request=True, body='+++\nurl = "about"\n+++\nBody.')],
        )
        assert state_of(tmp_path)["single_list"] == {}
        assert not (tmp_path / "dist" / "about.html").exists()

    def test_issue_without_pull_request_attribute_still_builds(self, tmp_path):
        """Guards the getattr default: anything duck-typed without the
        attribute must not be silently dropped."""
        build(tmp_path, [issue(number=1)])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]


class TestClosedIssuesUnpublish:
    """The `closed` trigger is what makes this work in CI: there is no cron
    to sweep unpublishes any more."""

    def test_closing_an_issue_removes_every_trace(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2)])
        assert (tmp_path / "dist" / "post" / "2.html").exists()

        build(tmp_path, [issue(number=1), issue(number=2, state="closed")], incremental="2")

        assert not (tmp_path / "dist" / "post" / "2.html").exists()
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1"]
        assert "post/2.html" not in (
            tmp_path / "dist" / "search-index.json"
        ).read_text(encoding="utf-8")
        assert index_of(tmp_path).count('post/2.html') == 0

    def test_closing_a_single_page_removes_it(self, tmp_path):
        build(tmp_path, [issue(body='+++\nurl = "about"\n+++\nBody.')])
        assert (tmp_path / "dist" / "about.html").exists()

        build(
            tmp_path,
            [issue(body='+++\nurl = "about"\n+++\nBody.', state="closed")],
            incremental="1",
        )
        assert not (tmp_path / "dist" / "about.html").exists()
        assert state_of(tmp_path)["single_list"] == {}

    def test_closing_drops_it_from_the_search_index_too(self, tmp_path):
        about = '+++\nurl = "about"\n+++\nBody.'
        build(tmp_path, [issue(number=1), issue(number=2, body=about)])

        build(
            tmp_path,
            [issue(number=1), issue(number=2, body=about, state="closed")],
            incremental="2",
        )
        index = json.loads(
            (tmp_path / "dist" / "search-index.json").read_text(encoding="utf-8")
        )
        assert all(record["url"] != "about.html" for record in index["posts"])


class TestIncrementalKeepsOthers:
    def test_other_posts_survive_an_incremental_rebuild(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2)])
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1", "P2"]
        build(tmp_path, [issue(number=1), issue(number=2)], incremental="1")
        assert sorted(state_of(tmp_path)["post_list"]) == ["P1", "P2"]
        assert (tmp_path / "dist" / "post" / "2.html").exists()


class TestSearchIndexFile:
    """dist/search-index.json feeds the client-side search plugin."""

    def test_full_build_writes_index_with_both_lists(self, tmp_path):
        build(
            tmp_path,
            [
                issue(number=1, labels=("a", "b")),
                issue(number=4, labels=("about",), body='+++\nurl = "about"\n+++\nAbout.'),
            ],
        )
        index = json.loads(
            (tmp_path / "dist" / "search-index.json").read_text(encoding="utf-8")
        )
        by_url = {record["url"]: record for record in index["posts"]}
        assert set(by_url) == {"post/1.html", "about.html"}
        assert by_url["post/1.html"]["labels"] == ["a", "b"]
        assert by_url["post/1.html"]["date"] == "2026-01-02"
        assert by_url["post/1.html"]["date_color"]
        assert isinstance(index["label_colors"], dict)

    def test_incremental_rebuild_keeps_index_current(self, tmp_path):
        build(tmp_path, [issue(number=1), issue(number=2)])
        # Incremental rebuilds only re-render one issue; the other entry, and
        # its search record, survive.
        build(tmp_path, [issue(number=1)], incremental="1")
        index = json.loads(
            (tmp_path / "dist" / "search-index.json").read_text(encoding="utf-8")
        )
        assert sorted(record["url"] for record in index["posts"]) == [
            "post/1.html",
            "post/2.html",
        ]
