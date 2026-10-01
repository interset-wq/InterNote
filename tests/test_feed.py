# -*- coding: utf-8 -*-
import pytest

from internote.feed import build_feed, strip_build_date

SITE = {
    "title": "Test Blog",
    "sub_title": "notes",
    "home_url": "https://example.com",
    "avatar_url": "https://example.com/a.png",
}

ENTRY = {
    "post_url": "post/1.html",
    "post_title": "First post",
    "description": "Summary.",
    "created_at": 1767322800,
}


class TestBuildFeed:
    def test_emits_rss_with_title_and_link(self):
        xml = build_feed(SITE, [ENTRY])
        assert "<rss" in xml
        assert "Test Blog" in xml
        assert "https://example.com/post/1.html" in xml

    def test_entry_title_and_description_present(self):
        xml = build_feed(SITE, [ENTRY])
        assert "First post" in xml
        assert "Summary." in xml

    def test_empty_sub_title_falls_back_to_site_title(self):
        # feedgen raises "Required fields not set (description)" on an empty
        # description, and sub_title defaults to "".
        site = dict(SITE, sub_title="")
        xml = build_feed(site, [ENTRY])
        assert "Test Blog" in xml

    def test_no_entries_is_still_valid(self):
        assert "<rss" in build_feed(SITE, [])


class TestStripBuildDate:
    def test_removes_the_element(self):
        assert "lastBuildDate" not in strip_build_date(
            "<rss><lastBuildDate>x</lastBuildDate></rss>"
        )

    def test_leaves_other_content(self):
        assert "keep" in strip_build_date(
            "<rss><lastBuildDate>x</lastBuildDate><t>keep</t></rss>"
        )

    def test_is_idempotent(self):
        once = strip_build_date("<rss><lastBuildDate>x</lastBuildDate></rss>")
        assert strip_build_date(once) == once
