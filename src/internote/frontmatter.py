# -*- coding: utf-8 -*-
"""TOML front matter, stripped from issue bodies before rendering.

A post may open with a block fenced by ``+++``:

    +++
    title = "A different title"
    date = 2026-01-01T10:00:00+08:00
    draft = false
    +++
    The body starts here.

TOML rather than YAML so the parser stays on the standard library. The
delimiter is ``+++`` rather than ``---`` because ``---`` is also a Markdown
thematic break, which makes it ambiguous at the top of a body.

Front matter must be removed *before* the body is handed to the markdown
renderer, otherwise GitHub turns the delimiters into an ``<hr>``. Every
mistake here raises: a silently ignored field is worse than a build
failure, and the author has no other signal that a key was misspelled.
"""
from __future__ import annotations

import datetime
import tomllib

DELIMITER = "+++"

#: Keys a post may set. ``labels`` is deliberately absent: GitHub issue
#: labels are authoritative because the tag pages and label colours are
#: derived from them (an issue with no label is published as ``default``).
#: ``slug`` never changes the canonical post/<id>.html URL; it only mints
#: a root-level alias page that redirects there. The title is always the
#: issue title and the description is always derived from the body, so
#: neither can be overridden here.
FIELDS = frozenset({"date", "draft", "comments", "pinned", "slug"})

#: Keys a *sub-post comment* may set. A sub post is a collaborator
#: comment on an issue; its body is the page content. The title falls
#: back to the first ``# `` heading in the body (an h1 already carries
#: title semantics), so ``title`` is optional; a comment with neither a
#: title nor an h1 fails the build rather than showing an empty row in
#: the series listing.
SUB_FIELDS = frozenset({"title", "order"})


class FrontMatterError(ValueError):
    """Raised when a front matter block cannot be parsed."""


def has_front_matter(text: str) -> bool:
    """True when *text* opens with a delimiter line.

    GitHub stores issue bodies with CRLF line endings, so the delimiter
    may be followed by ``\\r`` before the ``\\n``; both are accepted.
    """
    return text.startswith((DELIMITER + "\n", DELIMITER + "\r\n")) or (
        text.rstrip("\r\n") == DELIMITER
    )


def split(text: str, fields: frozenset = FIELDS) -> tuple[dict, str]:
    """Split leading front matter off *text*.

    Returns ``(meta, body)``; ``meta`` is empty and *body* is *text*
    unchanged when there is no front matter. Idempotent: a body that has
    already been stripped does not start with the delimiter, so splitting
    it again is a no-op. *fields* names the allowed keys (sub-post
    comments pass :data:`SUB_FIELDS`).
    """
    if not has_front_matter(text):
        return {}, text

    lines = text.split("\n")
    block: list[str] = []
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            end = index
            break
        # CRLF bodies leave a stray \r on every line; tomllib rejects a
        # basic string followed by a lone carriage return.
        block.append(lines[index].rstrip("\r"))

    if end is None:
        # A body consisting of nothing but the delimiter is not front
        # matter; anything else opened a block and forgot to close it.
        if not any(line.strip() for line in block):
            return {}, ""
        raise FrontMatterError(
            "front matter opened with {!r} but was never closed".format(DELIMITER)
        )

    body = "\n".join(lines[end + 1 :])
    if not block:
        return {}, body

    try:
        meta = tomllib.loads("\n".join(block))
    except tomllib.TOMLDecodeError as error:
        raise FrontMatterError("invalid TOML in front matter: {}".format(error)) from error

    unknown = sorted(set(meta) - fields)
    if unknown:
        raise FrontMatterError(
            "unknown front matter key(s) {}; allowed: {}".format(
                ", ".join(unknown), ", ".join(sorted(FIELDS))
            )
        )

    _check_types(meta)
    return meta, body


def split_sub(text: str) -> tuple[dict, str]:
    """Split front matter off a *sub-post comment* body.

    Same delimiter and parsing as :func:`split` but validates against
    :data:`SUB_FIELDS` (``title``/``order`` only — post keys like
    ``date`` or ``slug`` make no sense for a comment page).
    """
    meta, body = split(text, fields=SUB_FIELDS)
    if "title" in meta and not isinstance(meta["title"], str):
        raise FrontMatterError(
            "sub-post front matter 'title' must be a string, got {}".format(
                type(meta["title"]).__name__
            )
        )
    if "order" in meta and not isinstance(meta["order"], int):
        raise FrontMatterError(
            "sub-post front matter 'order' must be an integer, got {}".format(
                type(meta["order"]).__name__
            )
        )
    return meta, body


def take_leading_h1(text: str) -> tuple[str, str]:
    """Split a leading ATX h1 off *text*: ``(title, rest)``.

    The h1 carries title semantics, so when it becomes the page title it
    is consumed out of the body instead of rendering twice. Returns
    ``("", text)`` when the first non-empty line is not an ``# `` heading
    — a ``##`` heading, a code fence or plain prose all qualify, so an
    ordinary comment never trips this. Setext headings are not recognised.
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and len(stripped) > 2:
            return stripped[2:].strip(), "\n".join(lines[index + 1 :])
        return "", text
    return "", text


def _check_types(meta: dict) -> None:
    if "slug" in meta and not isinstance(meta["slug"], str):
        raise FrontMatterError(
            "front matter 'slug' must be a string, got {}".format(
                type(meta["slug"]).__name__
            )
        )
    if "draft" in meta and not isinstance(meta["draft"], bool):
        raise FrontMatterError(
            "front matter 'draft' must be a boolean, got {}".format(
                type(meta["draft"]).__name__
            )
        )
    for key in ("comments", "pinned"):
        if key in meta and not isinstance(meta[key], bool):
            raise FrontMatterError(
                "front matter {!r} must be a boolean, got {}".format(
                    key, type(meta[key]).__name__
                )
            )
    if "date" in meta and not isinstance(
        meta["date"], (datetime.datetime, datetime.date, int, str)
    ):
        raise FrontMatterError(
            "front matter 'date' must be a TOML datetime, a unix timestamp or an "
            "ISO string, got {}".format(type(meta["date"]).__name__)
        )


def parse_date(value: object) -> int:
    """Convert a front matter ``date`` into a unix timestamp (seconds)."""
    if isinstance(value, bool):  # bool is an int subclass; reject it
        raise FrontMatterError("front matter 'date' must not be a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, datetime.datetime):
        moment = value
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        return int(moment.timestamp())
    if isinstance(value, datetime.date):
        return int(
            datetime.datetime(
                value.year, value.month, value.day, tzinfo=datetime.timezone.utc
            ).timestamp()
        )
    if isinstance(value, str):
        text = value.strip()
        try:
            moment = datetime.datetime.fromisoformat(text)
        except ValueError as error:
            raise FrontMatterError(
                "front matter 'date' is not an ISO 8601 datetime: {}".format(error)
            ) from error
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        return int(moment.timestamp())
    raise FrontMatterError(
        "front matter 'date' must be a TOML datetime, a unix timestamp or an "
        "ISO string, got {}".format(type(value).__name__)
    )