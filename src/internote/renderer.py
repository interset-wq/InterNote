# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_SUFFIX = ".j2.html"


class Renderer:
    def __init__(self, templates_dir: str | Path = "templates"):
        self.templates_dir = Path(templates_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
        )

    def render(self, template: str, context: dict) -> str:
        name = template.removesuffix(TEMPLATE_SUFFIX)
        return self.env.get_template(name + TEMPLATE_SUFFIX).render(**context)

    def render_to(self, template: str, context: dict, dest: str | Path) -> None:
        output = self.render(template, context)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output, encoding="utf-8")
