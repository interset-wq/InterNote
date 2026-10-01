# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import time

from feedgen.feed import FeedGenerator


def build_feed(site: dict, entries: list[dict]) -> str:
    feed = FeedGenerator()
    feed.title(site["title"])
    # feedgen rejects an empty description, and sub_title defaults to "".
    feed.description(site["sub_title"] or site["title"])
    feed.link(href=site["home_url"])
    feed.image(url=site["avatar_url"], title="avatar", link=site["home_url"])
    feed.copyright(site["title"])
    feed.managingEditor(site["title"])
    feed.webMaster(site["title"])
    feed.ttl("60")

    for entry in entries:
        url = site["home_url"] + "/" + entry["post_url"]
        item = feed.add_item()
        item.guid(url, permalink=True)
        item.title(entry["post_title"])
        item.description(entry["description"])
        item.link(href=url)
        item.pubDate(
            time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(entry["created_at"]))
        )

    out = feed.rss_str(pretty=False)
    return out.decode("utf-8") if isinstance(out, bytes) else out


def strip_build_date(xml: str) -> str:
    return re.sub(r"<lastBuildDate>.*?</lastBuildDate>", "", xml)
