# -*- coding: utf-8 -*-
from internote.feed import build_feed, strip_build_date

CTX = {
    "title": "My Blog",
    "sub_title": "desc",
    "home_url": "https://x.github.io/InterNote",
    "avatar_url": "https://example.com/a.png",
}

ENTRIES = [
    {
        "post_title": "Second",
        "post_url": "post/2.html",
        "description": "Second intro.",
        "created_at": 1767225600,  # 2026-01-01 00:00:00 UTC
    },
    {
        "post_title": "First",
        "post_url": "post/1.html",
        "description": "First intro.",
        "created_at": 1735689600,  # 2025-01-01 00:00:00 UTC
    },
]


def test_build_feed_contains_channel_and_items():
    xml = build_feed(CTX, ENTRIES)

    assert "<title>My Blog</title>" in xml
    assert "<description>desc</description>" in xml
    assert "https://x.github.io/InterNote" in xml
    assert "<title>Second</title>" in xml
    assert "<title>First</title>" in xml
    assert "post/2.html" in xml


def test_build_feed_pubdate_format():
    xml = build_feed(CTX, ENTRIES)

    assert "<pubDate>Thu, 01 Jan 2026 00:00:00 +0000</pubDate>" in xml
    assert "<pubDate>Wed, 01 Jan 2025 00:00:00 +0000</pubDate>" in xml


def test_strip_build_date_removes_line():
    xml = build_feed(CTX, ENTRIES)
    assert "<lastBuildDate>" in xml

    stripped = strip_build_date(xml)
    assert "<lastBuildDate>" not in stripped


def test_strip_build_date_idempotent_on_missing():
    assert strip_build_date("<rss></rss>") == "<rss></rss>"
