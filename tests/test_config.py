# -*- coding: utf-8 -*-
import pathlib

import pytest
from pydantic import ValidationError

from internote.config import InternoteConfig, load_config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

MINIMAL = """
[site]
title = "Blog"
"""


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


class TestRequired:
    def test_site_title_is_required(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, "[site]\navatar_url = 'x'\n"))

    def test_title_only_is_valid(self, tmp_path):
        cfg = load_config(write(tmp_path, MINIMAL))
        assert cfg.site.title == "Blog"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "absent.toml")


class TestForbidUnknownKeys:
    """extra="forbid" is what makes a stale key a hard build failure, so a
    renamed or removed option cannot linger unnoticed in a blog repo."""

    def test_unknown_top_level_section(self, tmp_path):
        with pytest.raises(ValidationError, match="theme"):
            load_config(write(tmp_path, MINIMAL + "\n[theme]\nmode = 'dark'\n"))

    def test_unknown_key_in_layout(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(
                write(tmp_path, MINIMAL + "\n[layout]\nshow_sourse = true\n")
            )

    def test_removed_show_source_is_rejected(self, tmp_path):
        # it used to be a documented option; a blog repo may still set it
        with pytest.raises(ValidationError, match="show_source"):
            load_config(write(tmp_path, MINIMAL + "\n[layout]\nshow_source = true\n"))

    def test_removed_single_labels_is_rejected(self, tmp_path):
        # single-page routing moved to front matter `url`; a blog repo may
        # still carry the old key, which must fail the build loudly
        with pytest.raises(ValidationError, match="single_labels"):
            load_config(write(tmp_path, MINIMAL + "\n[layout]\nsingle_labels = ['about']\n"))

    def test_unknown_key_in_site(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, MINIMAL + "\nfoo = 1\n"))

    def test_misspelled_key_is_rejected(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, MINIMAL + "\n[comments]\nenabled2 = true\n"))


class TestTypes:
    def test_posts_per_page_must_be_int(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, MINIMAL + "\n[layout]\nposts_per_page = 'ten'\n"))

    def test_utc_must_be_int(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, MINIMAL + "\nutc = 'eight'\n"))

    @pytest.mark.parametrize("value", ["dark", "blue", "", "AUTO"])
    def test_language_is_restricted(self, tmp_path, value):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, MINIMAL + "\nlanguage = '{}'\n".format(value)))

    def test_language_accepts_cn_and_en(self, tmp_path):
        for lang in ("CN", "EN"):
            cfg = load_config(write(tmp_path, MINIMAL + "\nlanguage = '{}'\n".format(lang)))
            assert cfg.site.language == lang

    def test_comments_enabled_rejects_a_non_boolean(self, tmp_path):
        with pytest.raises(ValidationError):
            load_config(write(tmp_path, MINIMAL + "\n[comments]\nenabled = 'maybe'\n"))

    @pytest.mark.parametrize(
        "raw,expected",
        [("true", True), ("false", False), ("'yes'", True), ("'no'", False), ("0", False)],
    )
    def test_comments_enabled_accepts_pydantic_truthy_strings(
        self, tmp_path, raw, expected
    ):
        # pydantic lax mode coerces these; pinned so the leniency is a
        # documented decision rather than a surprise
        cfg = load_config(
            write(tmp_path, MINIMAL + "\n[comments]\nenabled = %s\n" % raw)
        )
        assert cfg.comments.enabled is expected


class TestDefaults:
    def test_optional_values_have_defaults(self, tmp_path):
        ctx = load_config(write(tmp_path, MINIMAL)).context()
        assert ctx["sub_title"] == ""
        assert ctx["posts_per_page"] == 10
        assert ctx["language"] == "CN"
        assert ctx["utc"] == 8
        assert ctx["need_comment"] is True

    def test_sections_default_when_absent(self, tmp_path):
        cfg = load_config(write(tmp_path, MINIMAL))
        assert cfg.comments.enabled is True
        assert cfg.giscus.repo == ""

    def test_explicit_values_win(self, tmp_path):
        cfg = load_config(
            write(tmp_path, MINIMAL + "\n[layout]\nposts_per_page = 3\n")
        )
        assert cfg.layout.posts_per_page == 3


class TestContext:
    def test_exposes_the_keys_templates_read(self, tmp_path):
        ctx = load_config(write(tmp_path, MINIMAL)).context()
        for key in (
            "title",
            "sub_title",
            "avatar_url",
            "home_url",
            "language",
            "utc",
            "posts_per_page",
            "start_date",
            "icp",
            "footer_text",
            "head",
            "style",
            "script",
            "index_script",
            "index_style",
            "all_head",
            "need_comment",
            "comment_label_color",
            "giscus_repo",
            "giscus_repo_id",
            "giscus_category",
            "giscus_category_id",
            "day_theme",
            "night_theme",
            "single_list",
            "label_color_dict",
        ):
            assert key in ctx, key

    def test_context_is_json_serialisable_shapes(self, tmp_path):
        ctx = load_config(write(tmp_path, MINIMAL)).context()
        assert isinstance(ctx["posts_per_page"], int)

    def test_direct_validation_without_a_file(self):
        cfg = InternoteConfig.model_validate({"site": {"title": "T"}})
        assert cfg.context()["title"] == "T"


class TestSampleConfig:
    def test_the_shipped_sample_is_valid(self, tmp_path):
        sample = tmp_path / "config.sample.toml"
        sample.write_text(
            (REPO_ROOT / "config.sample.toml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        cfg = load_config(sample)
        assert cfg.site.title
