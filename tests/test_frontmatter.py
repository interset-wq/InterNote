# -*- coding: utf-8 -*-
import datetime

import pytest

from internote.frontmatter import (
    FrontMatterError,
    has_front_matter,
    parse_date,
    split,
)


def block(body: str) -> str:
    return "+++\n" + body.strip("\n") + "\n+++\n" + body


class TestSplit:
    def test_no_front_matter_returns_body_unchanged(self):
        text = "# Title\n\nbody text\n"
        assert split(text) == ({}, text)

    def test_parses_every_supported_field(self):
        text = (
            "+++\n"
            "date = 2026-01-01T00:00:00+00:00\n"
            'slug = "hello"\n'
            "draft = false\n"
            "comments = true\n"
            "pinned = true\n"
            "+++\n"
            "body\n"
        )
        meta, body = split(text)
        assert meta["slug"] == "hello"
        assert meta["draft"] is False
        assert meta["comments"] is True
        assert meta["pinned"] is True
        assert meta["date"].year == 2026
        assert body == "body\n"

    def test_github_crlf_bodies_are_parsed(self):
        # GitHub stores issue bodies with CRLF endings; the block must
        # still be detected and the TOML must survive the stray \r.
        text = (
            "+++\r\n"
            'slug = "hello"\r\n'
            "date = 2025-07-31T10:18:38+08:00\r\n"
            "+++\r\n"
            "\r\n"
            "body\r\n"
        )
        meta, body = split(text)
        assert meta["slug"] == "hello"
        assert meta["date"].year == 2025
        assert body.startswith("\r\nbody")

    def test_delimiters_are_not_left_in_the_body(self):
        _, body = split("+++\nslug = 'x'\n+++\nreal content\n")
        assert body == "real content\n"
        assert "+++" not in body

    def test_body_is_stripped_before_the_markdown_renderer(self):
        # GitHub would turn a leading --- into an <hr>; that is why the
        # split has to happen first.
        _, body = split("+++\nslug = 'x'\n+++\n# Heading\n")
        assert not body.lstrip().startswith("+++")

    def test_is_idempotent(self):
        once = split("+++\nslug = 'x'\n+++\nbody\n")[1]
        assert split(once) == ({}, once)

    def test_empty_block_is_allowed(self):
        assert split("+++\n+++\nbody\n") == ({}, "body\n")

    def test_delimiter_only_body(self):
        assert split("+++") == ({}, "")


class TestRejections:
    def test_unterminated_block_raises(self):
        with pytest.raises(FrontMatterError, match="never closed"):
            split("+++\nslug = 'x'\nbody without closing\n")

    def test_invalid_toml_raises(self):
        with pytest.raises(FrontMatterError, match="invalid TOML"):
            split("+++\nslug = \n+++\nbody\n")

    def test_unknown_key_raises(self):
        with pytest.raises(FrontMatterError, match="unknown front matter key"):
            split("+++\ntitel = 'typo'\n+++\nbody\n")

    def test_labels_key_is_rejected(self):
        with pytest.raises(FrontMatterError, match="labels"):
            split('+++\nlabels = ["a"]\n+++\nbody\n')

    def test_removed_title_key_is_rejected(self):
        # title/description/head/style/script were removed from the schema;
        # stale bodies using them must fail loudly instead of being ignored.
        with pytest.raises(FrontMatterError, match="unknown front matter key"):
            split('+++\ntitle = "Custom"\n+++\nbody\n')

    def test_unknown_key_message_lists_allowed_keys(self):
        with pytest.raises(FrontMatterError) as info:
            split("+++\nbogus = 1\n+++\nbody\n")
        assert "slug" in str(info.value)

    def test_non_string_slug_raises(self):
        with pytest.raises(FrontMatterError, match="must be a string"):
            split("+++\nslug = 42\n+++\nbody\n")

    def test_non_boolean_draft_raises(self):
        with pytest.raises(FrontMatterError, match="must be a boolean"):
            split('+++\ndraft = "yes"\n+++\nbody\n')

    def test_non_boolean_pinned_raises(self):
        with pytest.raises(FrontMatterError, match="must be a boolean"):
            split('+++\npinned = "yes"\n+++\nbody\n')

    def test_bad_date_type_raises(self):
        # date = 2026-01-01 is a TOML local date and is accepted; an array
        # is not a date in any supported form.
        with pytest.raises(FrontMatterError, match="date"):
            split("+++\ndate = [2026, 1, 1]\n+++\nbody\n")

    def test_toml_local_date_is_accepted(self):
        meta, _ = split("+++\ndate = 2026-01-02\n+++\nbody\n")
        assert parse_date(meta["date"]) == parse_date(datetime.date(2026, 1, 2))


class TestHasFrontMatter:
    def test_detects_leading_delimiter(self):
        assert has_front_matter("+++\n")
        assert has_front_matter("+++")

    def test_detects_crlf_delimiter(self):
        assert has_front_matter("+++\r\nslug = 'x'\r\n+++\r\n")
        assert has_front_matter("+++\r\n")

    def testignores_a_delimiter_that_is_not_first(self):
        assert not has_front_matter("body\n+++\nslug = 'x'\n+++\n")
        assert not has_front_matter("text\n+++\n")


class TestParseDate:
    def test_toml_datetime(self):
        value = datetime.datetime(2026, 1, 2, 3, 4, tzinfo=datetime.timezone.utc)
        assert parse_date(value) == int(value.timestamp())

    def test_toml_local_datetime_is_treated_as_utc(self):
        naive = datetime.datetime(2026, 1, 2, 3, 4)
        aware = naive.replace(tzinfo=datetime.timezone.utc)
        assert parse_date(naive) == int(aware.timestamp())

    def test_toml_local_date(self):
        assert parse_date(datetime.date(2026, 1, 2)) == int(
            datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc).timestamp()
        )

    def test_unix_seconds_pass_through(self):
        assert parse_date(1700000000) == 1700000000

    def test_iso_string_with_offset(self):
        assert parse_date("2026-01-02T03:04:05+00:00") == int(
            datetime.datetime(
                2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc
            ).timestamp()
        )

    def test_iso_string_without_offset_is_utc(self):
        assert parse_date("2026-01-02T03:04:05") == parse_date(
            datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
        )

    def test_bad_iso_string_raises(self):
        with pytest.raises(FrontMatterError, match="ISO 8601"):
            parse_date("not a date")

    def test_boolean_is_rejected(self):
        # bool subclasses int, so without the guard True would become 1.
        with pytest.raises(FrontMatterError, match="boolean"):
            parse_date(True)
