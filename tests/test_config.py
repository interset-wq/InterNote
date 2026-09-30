# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from pydantic import ValidationError

from internote.config import InternoteConfig, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE = REPO_ROOT / "config.sample.toml"

MINIMAL = """
[site]
title = "My Blog"
"""


def test_minimal_config_loads_with_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(MINIMAL, encoding="utf-8")

    cfg = load_config(path)

    assert cfg.site.title == "My Blog"
    assert cfg.features.toc is False
    assert cfg.features.visit_counter == "off"
    assert cfg.comments.enabled is True
    assert cfg.site.language == "CN"
    assert cfg.site.utc == 8
    assert cfg.site.version == "last"
    assert cfg.layout.one_page_list_num == 15
    assert cfg.layout.show_post_source is True
    assert cfg.giscus.repo == ""
    assert cfg.feed.split == "sentence"


def test_title_is_required(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[site]\nsub_title = 'x'\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_unknown_key_rejected(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(MINIMAL + "\nbogus_key = 1\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_invalid_visit_counter_rejected(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        MINIMAL + '\n[features]\nvisit_counter = "google"\n', encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        load_config(path)


def test_invalid_language_rejected(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(MINIMAL + 'language = "XX"\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_russian_language_rejected(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(MINIMAL + 'language = "RU"\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_flat_context_uses_snake_case(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(MINIMAL, encoding="utf-8")

    ctx = load_config(path).context()

    assert ctx["title"] == "My Blog"
    assert ctx["theme_mode"] == "manual"
    assert ctx["day_theme"] == "light"
    assert ctx["night_theme"] == "dark"
    assert ctx["year_color_list"][0] == "#bc4c00"
    assert ctx["need_comment"] is True
    assert ctx["comment_label_color"] == "#006b75"
    assert ctx["giscus_repo"] == ""
    assert ctx["giscus_repo_id"] == ""
    assert ctx["giscus_category"] == ""
    assert ctx["giscus_category_id"] == ""
    assert ctx["toc"] is False
    assert ctx["visit_counter"] == "off"
    assert ctx["rss_split"] == "sentence"
    assert ctx["single_list"] == {}
    assert ctx["post_list"] == {}
    assert ctx["label_color_dict"] == {}

    camel = [k for k in ctx if any(c.isupper() for c in k)]
    assert camel == []
    assert "url_mode" not in ctx
    assert "i18n" not in ctx  # language selection lives in renderer, not config


def test_giscus_section_roundtrip(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        MINIMAL
        + """
[giscus]
repo = "user/blog"
repo_id = "R_1"
category = "General"
category_id = "DIC_1"
""",
        encoding="utf-8",
    )

    cfg = load_config(path)
    assert cfg.giscus.repo == "user/blog"
    assert cfg.giscus.category_id == "DIC_1"


def test_sample_config_loads():
    cfg = load_config(SAMPLE)
    assert cfg.site.title != ""
    ctx = cfg.context()
    assert ctx["visit_counter"] in ("off", "vercount", "busuanzi")
