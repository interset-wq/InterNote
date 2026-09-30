# -*- coding: utf-8 -*-
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

PRIMER_CSS_DEFAULT = (
    "<link href='https://mirrors.sustech.edu.cn/cdnjs/ajax/libs/"
    "Primer/21.0.7/primer.css' rel='stylesheet' />"
)


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    sub_title: str = ""
    avatar_url: str = ""
    display_title: str = ""
    favicon_url: str = ""
    og_image: str = ""
    home_url: str = ""
    version: str = "last"
    language: Literal["CN", "EN", "RU"] = "CN"
    utc: int = 8


class ThemeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["manual", "fix"] = "manual"
    day: str = "light"
    night: str = "dark"
    year_colors: list[str] = ["#bc4c00", "#0969da", "#1f883d", "#A333D0"]
    primer_css: str = PRIMER_CSS_DEFAULT


class LayoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    one_page_list_num: int = 15
    single_page: list[str] = []
    start_site: str = ""
    filing_num: str = ""
    bottom_text: str = ""
    show_post_source: bool = True
    head: str = ""
    style: str = ""
    script: str = ""
    index_script: str = ""
    index_style: str = ""
    all_head: str = ""


class NavConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exlink: dict[str, str] = {}
    icon_list: dict[str, str] = {}


class CommentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    label_color: str = "#006b75"


class GiscusConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str = ""
    repo_id: str = ""
    category: str = ""
    category_id: str = ""


class FeaturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    toc: bool = False
    visit_counter: Literal["off", "vercount", "busuanzi"] = "off"


class FeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: str = "sentence"


class InternoteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: SiteConfig
    theme: ThemeConfig = ThemeConfig()
    layout: LayoutConfig = LayoutConfig()
    nav: NavConfig = NavConfig()
    comments: CommentsConfig = CommentsConfig()
    giscus: GiscusConfig = GiscusConfig()
    features: FeaturesConfig = FeaturesConfig()
    feed: FeedConfig = FeedConfig()

    def context(self) -> dict:
        site = self.site
        return {
            "title": site.title,
            "sub_title": site.sub_title,
            "avatar_url": site.avatar_url,
            "display_title": site.display_title or site.title,
            "favicon_url": site.favicon_url or site.avatar_url,
            "og_image": site.og_image or site.avatar_url,
            "home_url": site.home_url,
            "version": site.version,
            "language": site.language,
            "utc": site.utc,
            "theme_mode": self.theme.mode,
            "day_theme": self.theme.day,
            "night_theme": self.theme.night,
            "year_color_list": self.theme.year_colors,
            "primer_css": self.theme.primer_css,
            "one_page_list_num": self.layout.one_page_list_num,
            "single_page": self.layout.single_page,
            "start_site": self.layout.start_site,
            "filing_num": self.layout.filing_num,
            "bottom_text": self.layout.bottom_text,
            "show_post_source": self.layout.show_post_source,
            "head": self.layout.head,
            "style": self.layout.style,
            "script": self.layout.script,
            "index_script": self.layout.index_script,
            "index_style": self.layout.index_style,
            "all_head": self.layout.all_head,
            "exlink": self.nav.exlink,
            "icon_list": self.nav.icon_list,
            "need_comment": self.comments.enabled,
            "comment_label_color": self.comments.label_color,
            "giscus_repo": self.giscus.repo,
            "giscus_repo_id": self.giscus.repo_id,
            "giscus_category": self.giscus.category,
            "giscus_category_id": self.giscus.category_id,
            "toc": self.features.toc,
            "visit_counter": self.features.visit_counter,
            "rss_split": self.feed.split,
            "post_list": {},
            "single_list": {},
            "label_color_dict": {},
        }


def load_config(path: str | Path) -> InternoteConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return InternoteConfig.model_validate(data)
