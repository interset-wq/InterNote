# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_SUFFIX = ".j2.html"
PKG_TEMPLATES = Path(__file__).resolve().parent / "templates"


class Renderer:
    def __init__(self, templates_dir: str | Path = PKG_TEMPLATES):
        self.templates_dir = Path(templates_dir)
        # autoescape stays off: post bodies are pre-rendered HTML from the
        # GitHub API. trim_blocks/lstrip_blocks keep {% if %} blocks from
        # leaking blank lines into the output.
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template: str, context: dict) -> str:
        name = template.removesuffix(TEMPLATE_SUFFIX)
        return self.env.get_template(name + TEMPLATE_SUFFIX).render(**context)

    def render_to(self, template: str, context: dict, dest: str | Path) -> None:
        output = self.render(template, context)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output, encoding="utf-8")
