# -*- coding: utf-8 -*-
"""Tests for the Algolia search index sync.

Everything here is offline. The three-step swap is asserted against the
RecordingUrlopen stub in conftest.py, and the no-key path is asserted by
asserting no HTTP call happens at all.
"""
import urllib.error
from pathlib import Path

import pytest
from conftest import RecordingUrlopen

from internote import search as search_module
from internote.search import (
    INDEX_SETTINGS,
    AlgoliaIndex,
    build_records,
    markdown_to_text,
    sync,
)


@pytest.fixture
def stub(monkeypatch):
    recorder = RecordingUrlopen()
    monkeypatch.setattr(search_module.urllib.request, "urlopen", recorder)
    return recorder


@pytest.fixture
def sources(tmp_path):
    def write(number, body):
        (tmp_path / ("%s.md" % number)).write_text(body, encoding="utf-8")

    write(1, "# Hello\n\n这是**一篇**测试文章。\n")
    write(2, "Second post body.\n")
    write(4, "About this site.\n")
    return tmp_path


def entry(number, title, url, labels, date="2026-09-30", words=10):
    return {
        "number": number,
        "post_title": title,
        "post_url": url,
        "labels": labels,
        "created_date": date,
        "word_count": words,
    }


class TestMarkdownToText:
    def test_empty(self):
        assert markdown_to_text("") == ""

    def test_headings_and_emphasis_are_stripped(self):
        assert markdown_to_text("## Title\n\nsome **bold** text") == (
            "Title some bold text"
        )

    def test_code_content_is_kept_but_fences_are_not(self):
        out = markdown_to_text("```python\nprint('hi')\n```")
        assert "print('hi')" in out
        assert "```" not in out
        assert "python" not in out.split("print")[0].replace("print", "")

    def test_links_keep_their_label(self):
        assert markdown_to_text("see [the docs](https://example.com/a)") == (
            "see the docs"
        )

    def test_images_keep_alt_text(self):
        assert markdown_to_text("![a cat](cat.png)") == "a cat"

    def test_html_is_removed(self):
        assert markdown_to_text("<div><span>hi</span></div>") == "hi"

    def test_script_and_style_contents_are_dropped(self):
        out = markdown_to_text("<script>var secret=1</script>keep<style>.a{}</style>")
        assert "secret" not in out
        assert ".a{}" not in out
        assert out == "keep"

    def test_entities_are_decoded(self):
        assert markdown_to_text("a &amp; b &lt;tag&gt;") == "a & b <tag>"

    def test_raw_script_tags_are_removed_but_escaped_ones_survive_as_text(self):
        """A raw <script> is markup and must not be indexed. An escaped
        &lt;script&gt; is text the author meant to show, so it stays and
        decodes - harmless because the dialog never assigns innerHTML."""
        assert markdown_to_text("<script>alert(1)</script>") == ""
        assert markdown_to_text("&lt;script&gt;alert(1)&lt;/script&gt;") == (
            "<script>alert(1)</script>"
        )

    def test_dialog_never_assigns_inner_html(self):
        """The safety net for the case above: post bodies are attacker-influenced
        text, so the dialog may only build DOM from text nodes."""
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "internote"
            / "plugins"
            / "search.js"
        ).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("//")
        )
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML"):
            assert forbidden not in code, "%s must not appear in search.js" % forbidden

    def test_whitespace_collapses(self):
        assert markdown_to_text("a\n\n\n   b\t\tc") == "a b c"

    def test_list_bullets_removed(self):
        assert markdown_to_text("- one\n- two") == "one two"

    def test_chinese_paragraphs_do_not_run_together(self):
        out = markdown_to_text("第一段。\n\n第二段。")
        assert out == "第一段。 第二段。"


class TestBuildRecords:
    def test_merges_both_lists(self, sources):
        """The bug this closes: post-list.json walked post_list only, so
        single pages like about.html were never searchable."""
        records = build_records(
            {"P1": entry(1, "Hello", "post/1.html", ["a"])},
            {"P4": entry(4, "About", "about.html", ["about"])},
            "https://example.com",
            sources,
        )
        assert sorted(r["objectID"] for r in records) == ["page-about", "post-1"]

    def test_record_fields(self, sources):
        record = build_records(
            {"P1": entry(1, "Hello", "post/1.html", ["a", "b"], words=99)},
            {},
            "https://example.com",
            sources,
        )[0]
        assert record["title"] == "Hello"
        assert record["labels"] == ["a", "b"]
        assert record["wordCount"] == 99
        assert record["date"] == "2026-09-30"
        assert "测试文章" in record["body"]

    def test_url_is_absolute_against_home_url(self, sources):
        record = build_records(
            {"P1": entry(1, "T", "post/1.html", [])}, {}, "https://example.com", sources
        )[0]
        assert record["url"] == "https://example.com/post/1.html"

    def test_trailing_slash_on_home_url_is_not_doubled(self, sources):
        record = build_records(
            {"P1": entry(1, "T", "post/1.html", [])},
            {},
            "https://example.com/",
            sources,
        )[0]
        assert record["url"] == "https://example.com/post/1.html"

    def test_single_page_object_id_uses_the_label(self, sources):
        record = build_records(
            {}, {"P9": entry(9, "About", "about.html", ["about"])}, "", sources
        )[0]
        assert record["objectID"] == "page-about"

    def test_missing_source_file_gives_empty_body(self, tmp_path):
        record = build_records(
            {"P7": entry(7, "T", "post/7.html", [])}, {}, "https://x.com", tmp_path
        )[0]
        assert record["body"] == ""

    def test_post_and_page_namespaces_cannot_collide(self, sources):
        """Issue 4 is both a post number and a label name."""
        records = build_records(
            {"P4": entry(4, "Post", "post/4.html", ["other"])},
            {"P4b": entry(4, "Page", "about.html", ["about"])},
            "https://x.com",
            sources,
        )
        ids = [r["objectID"] for r in records]
        assert len(ids) == len(set(ids))


class TestSyncIsOptIn:
    def test_no_admin_key_means_no_network(self, monkeypatch, sources, capsys):
        monkeypatch.delenv("ALGOLIA_ADMIN_KEY", raising=False)

        def explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("urlopen must not be called without a key")

        monkeypatch.setattr(search_module.urllib.request, "urlopen", explode)
        assert (
            sync({}, {}, "https://x.com", sources, "APP", "KEY", "idx") is False
        )
        assert "ALGOLIA_ADMIN_KEY" in capsys.readouterr().out

    def test_unconfigured_credentials_skip_without_network(self, monkeypatch, sources):
        monkeypatch.setenv("ALGOLIA_ADMIN_KEY", "admin")

        def explode(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("urlopen must not be called without app_id")

        monkeypatch.setattr(search_module.urllib.request, "urlopen", explode)
        assert sync({}, {}, "https://x.com", sources, "", "", "") is False

    def test_explicit_key_argument_beats_the_environment(self, monkeypatch, sources):
        monkeypatch.delenv("ALGOLIA_ADMIN_KEY", raising=False)
        monkeypatch.setattr(
            search_module.urllib.request, "urlopen", RecordingUrlopen()
        )
        assert (
            sync({}, {}, "https://x.com", sources, "APP", "K", "idx", admin_key="a")
            is True
        )


class TestIndexSwap:
    def test_three_steps_in_order(self, stub, sources):
        records = build_records(
            {"P1": entry(1, "T", "post/1.html", [])}, {}, "https://x.com", sources
        )
        AlgoliaIndex("APP", "admin", "posts").replace_all(records)

        assert stub.paths == [
            "posts/operation",
            "posts_tmp/settings",
            "posts_tmp/batch",
            "posts_tmp/operation",
        ]
        assert stub.calls[0]["payload"]["operation"] == "copy"
        assert stub.calls[0]["payload"]["destination"] == "posts_tmp"
        assert stub.calls[1]["payload"] == INDEX_SETTINGS
        assert stub.calls[-1]["payload"] == {
            "operation": "move",
            "destination": "posts",
        }

    def test_batch_uses_add_object_with_the_record_body(self, stub, sources):
        records = build_records(
            {"P1": entry(1, "T", "post/1.html", [])}, {}, "https://x.com", sources
        )
        AlgoliaIndex("APP", "admin", "posts").replace_all(records)

        batch = stub.calls[2]["payload"]["requests"]
        assert len(batch) == 1
        assert batch[0]["action"] == "addObject"
        assert batch[0]["body"]["objectID"] == "post-1"

    def test_every_call_is_a_post(self, stub, sources):
        AlgoliaIndex("APP", "admin", "posts").replace_all([])
        assert {call["method"] for call in stub.calls} == {"POST"}

    def test_admin_key_travels_in_the_header(self, stub, sources):
        AlgoliaIndex("APP", "secret-admin", "posts").replace_all([])
        headers = stub.calls[0]["headers"]
        assert headers["X-algolia-api-key"] == "secret-admin"
        assert headers["X-algolia-application-id"] == "APP"

    def test_empty_site_clears_the_scratch_index(self, stub):
        """An empty batch is a no-op, so without an explicit clear a move
        could resurrect records from a previous build."""
        AlgoliaIndex("APP", "admin", "posts").replace_all([])
        assert stub.paths == [
            "posts/operation",
            "posts_tmp/settings",
            "posts_tmp/clear",
            "posts_tmp/operation",
        ]

    def test_query_endpoint_is_never_written_to(self, stub, sources):
        AlgoliaIndex("APP", "admin", "posts").replace_all([])
        assert all("query" not in path for path in stub.paths)


class TestFailuresAreNotFatal:
    def test_http_error_warns_and_returns_false(
        self, monkeypatch, sources, capsys
    ):
        monkeypatch.setenv("ALGOLIA_ADMIN_KEY", "admin")
        monkeypatch.setattr(
            search_module.urllib.request,
            "urlopen",
            RecordingUrlopen(fail_with=urllib.error.HTTPError("u", 403, "no", {}, None)),
        )
        assert sync({}, {}, "https://x.com", sources, "APP", "K", "idx") is False
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "403" in out

    def test_network_error_warns_and_returns_false(
        self, monkeypatch, sources, capsys
    ):
        monkeypatch.setenv("ALGOLIA_ADMIN_KEY", "admin")
        monkeypatch.setattr(
            search_module.urllib.request,
            "urlopen",
            RecordingUrlopen(fail_with=urllib.error.URLError("dns")),
        )
        assert sync({}, {}, "https://x.com", sources, "APP", "K", "idx") is False
        assert "WARNING" in capsys.readouterr().out

    def test_success_reports_the_record_count(self, monkeypatch, sources, capsys):
        monkeypatch.setenv("ALGOLIA_ADMIN_KEY", "admin")
        monkeypatch.setattr(
            search_module.urllib.request, "urlopen", RecordingUrlopen()
        )
        ok = sync(
            {"P1": entry(1, "T", "post/1.html", [])},
            {"P4": entry(4, "About", "about.html", ["about"])},
            "https://x.com",
            sources,
            "APP",
            "K",
            "idx",
        )
        assert ok is True
        assert "2 record(s)" in capsys.readouterr().out


class TestIndexSettings:
    def test_searchable_attributes_put_title_first(self):
        assert INDEX_SETTINGS["searchableAttributes"] == [
            "title",
            "labels",
            "body",
        ]

    def test_snippet_is_configured(self):
        assert INDEX_SETTINGS["attributesToSnippet"] == ["body:25"]