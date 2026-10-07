# -*- coding: utf-8 -*-
"""Load a fixture JSON (see scripts/fetch_fixtures.py) as a fake repo.

FixtureRepo mirrors the PyGithub surface the Generator actually uses,
so local builds and unit tests run fully offline.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from . import frontmatter


class FixtureIssue:
    def __init__(self, raw: dict):
        self.number = raw["number"]
        self.title = raw["title"]
        self.body = raw["body"]
        self.body_html = raw["body_html"]
        self.labels = [SimpleNamespace(**lb) for lb in raw["labels"]]
        self.created_at = datetime.fromisoformat(raw["created_at"])
        self.updated_at = datetime.fromisoformat(raw["updated_at"])
        # Generator.run_one branches on this; PyGithub's Issue always has it.
        self.state = raw.get("state", "open")
        # PyGithub exposes a PullRequest object here for PRs and None for
        # issues. Generator._add_entry skips anything truthy.
        self.pull_request = (
            SimpleNamespace(number=raw["number"]) if raw.get("pull_request") else None
        )
        # PyGithub exposes the comment count as a plain int; the generator
        # uses it to decide whether comments must be fetched at all.
        self.comments = raw.get("comments_total", len(raw.get("comments", [])))
        self._events = raw["events"]
        # Sub-post comments: the generator renders their bodies through the
        # same markdown pipeline, so keep them raw for the html lookup too.
        self._comments = raw.get("comments", [])

    def get_events(self):
        return [SimpleNamespace(**ev) for ev in self._events]

    def get_comments(self):
        return [
            SimpleNamespace(
                id=raw["id"],
                body=raw["body"],
                author_association=raw.get("author_association", "NONE"),
                created_at=datetime.fromisoformat(raw["created_at"]),
                updated_at=datetime.fromisoformat(raw["updated_at"]),
            )
            for raw in self._comments
        ]


class FixtureRepo:
    def __init__(self, data: dict):
        owner, _, name = data["repo"].partition("/")
        self.repo_name = data["repo"]
        self.name = name
        self.owner = SimpleNamespace(login=owner)
        self._labels = [SimpleNamespace(**lb) for lb in data["labels"]]
        self._issues = [FixtureIssue(raw) for raw in data["issues"]]

    def get_labels(self):
        return list(self._labels)

    def get_issues(self):
        return list(self._issues)

    def get_issue(self, number):
        for issue in self._issues:
            if issue.number == int(number):
                return issue
        raise KeyError(number)


def load_repo(path: str | Path):
    """Return (repo, markdown_fn) built from a fixture JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    repo = FixtureRepo(data)
    # The generator strips front matter before calling markdown(), so the
    # lookup is keyed on the stripped body. The fixture keeps the raw body
    # so the front matter is still readable as post metadata.
    html_by_body = {}
    for issue in repo._issues:
        try:
            _, cleaned = frontmatter.split(issue.body)
        except frontmatter.FrontMatterError:
            cleaned = issue.body
        html_by_body[cleaned] = issue.body_html
        # Sub-post comments may carry a pre-rendered body_html (the fetch
        # script renders it); without one markdown() falls back to raw text.
        for raw in issue._comments:
            try:
                _, cleaned = frontmatter.split(raw["body"])
            except frontmatter.FrontMatterError:
                cleaned = raw["body"]
            if raw.get("body_html"):
                html_by_body[cleaned] = raw["body_html"]

    def markdown(text: str) -> str:
        html = html_by_body.get(text)
        if html is None:
            print("warning: body not in fixture, using raw text")
            return text
        return html

    return repo, markdown
