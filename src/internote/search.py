# -*- coding: utf-8 -*-
"""Build-time sync of a hosted search index.

Deliberately SDK-free. The Algolia Python client would add aiohttp, requests,
urllib3, python-dateutil and async-timeout for what amounts to a handful of
REST calls, and this project keeps its dependency list short. Everything here
is stdlib urllib.

Records are built from the markdown source in `sources/`, not from the
rendered HTML. The rendered HTML never reaches the entry dict - `_create_post`
passes it straight to the template - so the only way to get it would be to
cache it on the entry, which would bloat `internote.json`. That file is
committed back to the blog repo, so its size matters.

Nothing in this module runs unless ALGOLIA_ADMIN_KEY is exported, so tests,
fixture builds and local previews never touch the network.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ADMIN_KEY_ENV = "ALGOLIA_ADMIN_KEY"

# Applied on every sync so the index describes itself and a settings change
# lands on the next build instead of needing a one-off dashboard edit.
# attributesForFaceting was here on the assumption a label filter would be
# built later; nothing reads it, so it is not sent.
INDEX_SETTINGS = {
    "searchableAttributes": ["title", "labels", "body"],
    "attributesToSnippet": ["body:25"],
}

# Fence markers go, the code between them stays: code is searchable content.
_FENCE = re.compile(r"^\s*(?:```|~~~).*$", re.MULTILINE)
_SCRIPT_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_QUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_ORDERED = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$", re.MULTILINE)
_MARKER = re.compile(r"[*_~`]+")
_WHITESPACE = re.compile(r"\s+")


def markdown_to_text(markdown: str) -> str:
    """Reduce a markdown body to the prose a reader could actually see."""
    if not markdown:
        return ""
    text = _FENCE.sub(" ", markdown)
    text = _SCRIPT_STYLE.sub(" ", text)
    text = _HTML_TAG.sub(" ", text)
    # Images keep their alt text, links keep their label.
    text = _IMAGE.sub(r" \1 ", text)
    text = _LINK.sub(r" \1 ", text)
    text = _RULE.sub(" ", text)
    text = _HEADING.sub(" ", text)
    text = _QUOTE.sub(" ", text)
    text = _BULLET.sub(" ", text)
    text = _ORDERED.sub(" ", text)
    text = _MARKER.sub("", text)
    # Unescape last, so an escaped &lt;div&gt; cannot become a fake tag after
    # the tag pass has already run.
    text = html.unescape(text)
    return _WHITESPACE.sub(" ", text).strip()


def _body_text(sources_dir: Path, number: int) -> str:
    path = sources_dir / ("%s.md" % number)
    try:
        return markdown_to_text(path.read_text(encoding="utf-8"))
    except OSError:
        return ""


def build_records(
    post_list: dict, single_list: dict, home_url: str, sources_dir: Path
) -> list[dict]:
    """One Algolia record per post.

    Merges both lists. post-list.json historically walked post_list only, which
    left single pages such as about.html unsearchable; the RSS feed already
    merges the two.
    """
    records = [
        _record(entry, "post", home_url, sources_dir) for entry in post_list.values()
    ]
    for entry in single_list.values():
        # Single pages are named after their label rather than an issue
        # number, so key them the same way to keep objectIDs meaningful.
        label = (entry.get("labels") or ["page"])[0]
        records.append(
            _record(entry, "page", home_url, sources_dir, object_id="page-%s" % label)
        )
    return records


def _record(
    entry: dict,
    prefix: str,
    home_url: str,
    sources_dir: Path,
    object_id: str | None = None,
) -> dict:
    number = entry.get("number")
    if object_id is None:
        object_id = "%s-%s" % (prefix, number if number is not None else "unknown")

    post_url = entry.get("post_url") or ""
    base = home_url.rstrip("/")
    return {
        "objectID": object_id,
        "title": entry.get("post_title", ""),
        "body": _body_text(sources_dir, number) if number is not None else "",
        "labels": list(entry.get("labels") or []),
        # post_url is stored relative and percent-encoded, so it is useless to
        # anything not sitting inside dist/.
        "url": ("%s/%s" % (base, post_url)) if post_url else base + "/",
        "date": entry.get("created_date", ""),
        "wordCount": entry.get("word_count", 0),
    }


def _request(url: str, payload: dict, headers: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        request.add_header(name, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


class AlgoliaIndex:
    """Minimal Algolia index writer.

    Uses the temporary-index pattern: write into a scratch index, then move it
    over the live name. A clear-and-refill would leave the index visibly empty
    to anyone searching during a publish.
    """

    def __init__(self, app_id: str, admin_key: str, index_name: str):
        self.app_id = app_id
        self.admin_key = admin_key
        self.index_name = index_name
        self.tmp_name = "%s_tmp" % index_name
        self.base = "https://%s.algolia.net/1/indexes" % app_id
        self.headers = {
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": admin_key,
            "Content-Type": "application/json",
        }

    def replace_all(self, records: list[dict]) -> None:
        self._copy_settings()
        self._batch(records)
        self._move()

    def _copy_settings(self) -> None:
        _request(
            "%s/%s/operation" % (self.base, self.index_name),
            {
                "operation": "copy",
                "destination": self.tmp_name,
                "scope": ["settings", "synonyms", "rules"],
            },
            self.headers,
        )
        # copy carries settings across from the live index, but set them
        # explicitly too so a brand new index does not keep Algolia defaults.
        _request(
            "%s/%s/settings" % (self.base, self.tmp_name),
            INDEX_SETTINGS,
            self.headers,
        )

    def _batch(self, records: list[dict]) -> None:
        if not records:
            # An empty batch is a no-op, so clear explicitly; otherwise a move
            # could carry stale records forward.
            _request("%s/%s/clear" % (self.base, self.tmp_name), {}, self.headers)
            return
        payload = {
            "requests": [{"action": "addObject", "body": record} for record in records]
        }
        _request("%s/%s/batch" % (self.base, self.tmp_name), payload, self.headers)

    def _move(self) -> None:
        _request(
            "%s/%s/operation" % (self.base, self.tmp_name),
            {"operation": "move", "destination": self.index_name},
            self.headers,
        )


def sync(
    post_list: dict,
    single_list: dict,
    home_url: str,
    sources_dir: Path,
    app_id: str,
    api_key: str,
    index_name: str,
    admin_key: str | None = None,
) -> bool:
    """Push the current site to Algolia.

    Returns True when the index was written. Returns False without touching the
    network when search is unconfigured or no admin key is exported.

    A transport or HTTP failure is logged and swallowed: a search outage must
    not stop the site from being published.
    """
    if not (app_id and api_key and index_name):
        print(
            "[search] skipped: [search] needs app_id, api_key and index_name"
        )
        return False

    key = admin_key if admin_key is not None else os.environ.get(ADMIN_KEY_ENV, "")
    if not key:
        print(
            "[search] skipped: %s is not set, leaving the index untouched"
            % ADMIN_KEY_ENV
        )
        return False

    records = build_records(post_list, single_list, home_url, sources_dir)
    try:
        AlgoliaIndex(app_id, key, index_name).replace_all(records)
    except urllib.error.HTTPError as error:
        print(
            "[search] WARNING: Algolia rejected the sync (HTTP %s). Search will "
            "serve stale content until a later build succeeds." % error.code
        )
        return False
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        print(
            "[search] WARNING: could not reach Algolia (%s). Search will serve "
            "stale content until a later build succeeds." % error
        )
        return False

    print("[search] indexed %d record(s) into '%s'" % (len(records), index_name))
    return True