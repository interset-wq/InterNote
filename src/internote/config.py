# -*- coding: utf-8 -*-
from __future__ import annotations

import re

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    sub_title: str = ""
    avatar_url: str = ""
    # Empty = use the blog repo owner's GitHub avatar (downloaded at build
    # time); a URL = use that image; "none" = no favicon at all.
    favicon: str = ""
    home_url: str = ""
    language: Literal["CN", "EN"] = "CN"
    utc: int = 8


class LayoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    posts_per_page: int = 10
    start_date: str = ""
    icp: str = ""
    footer_text: str = ""
    head: str = ""
    style: str = ""
    script: str = ""
    index_script: str = ""
    index_style: str = ""
    all_head: str = ""


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


class SocialLink(BaseModel):
    """One footer social icon. `id` names the Simple Icons glyph
    (https://simpleicons.org slugs); the action decides what clicking
    does and which other field is required."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = ""
    action: Literal["link", "copy", "qrcode"] = "link"
    url: str = ""
    username: str = ""
    qrcode: str = ""

    @model_validator(mode="after")
    def _check_action_fields(self):
        if not re.fullmatch(r"[a-z0-9-]+", self.id):
            # also keeps the id safe to embed in a download URL / file name
            raise ValueError(
                "social id must be a Simple Icons slug (lowercase letters, "
                "digits, hyphens), got {!r}".format(self.id)
            )
        needed = {"link": "url", "copy": "username", "qrcode": "qrcode"}[
            self.action
        ]
        if not getattr(self, needed):
            raise ValueError(
                "social {!r} with action {!r} requires {!r}".format(
                    self.id, self.action, needed
                )
            )
        return self


class InternoteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: SiteConfig
    layout: LayoutConfig = LayoutConfig()
    comments: CommentsConfig = CommentsConfig()
    giscus: GiscusConfig = GiscusConfig()
    social: list[SocialLink] = []

    def context(self) -> dict:
        site = self.site
        layout = self.layout
        return {
            "title": site.title,
            "sub_title": site.sub_title,
            "avatar_url": site.avatar_url,
            "favicon": site.favicon,
            "home_url": site.home_url,
            "language": site.language,
            "utc": site.utc,
            "posts_per_page": layout.posts_per_page,
            "start_date": layout.start_date,
            "icp": layout.icp,
            "footer_text": layout.footer_text,
            "head": layout.head,
            "style": layout.style,
            "script": layout.script,
            "index_script": layout.index_script,
            "index_style": layout.index_style,
            "all_head": layout.all_head,
            "need_comment": self.comments.enabled,
            "comment_label_color": self.comments.label_color,
            "giscus_repo": self.giscus.repo,
            "giscus_repo_id": self.giscus.repo_id,
            "giscus_category": self.giscus.category,
            "giscus_category_id": self.giscus.category_id,
            "social": [link.model_dump() for link in self.social],
            "theme_mode": "manual",
            "day_theme": "light",
            "night_theme": "dark",
            "post_list": {},
            "label_color_dict": {},
        }


def load_config(path: str | Path) -> InternoteConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return InternoteConfig.model_validate(data)
