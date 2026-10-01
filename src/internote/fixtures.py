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


class _CommentList:
    def __init__(self, total: int):
        self.totalCount = total


class FixtureIssue:
    def __init__(self, raw: dict):
        self.number = raw["number"]
        self.title = raw["title"]
        self.body = raw["body"]
        self.body_html = raw["body_html"]
        self.labels = [SimpleNamespace(**lb) for lb in raw["labels"]]
        self.created_at = datetime.fromisoformat(raw["created_at"])
        self.updated_at = datetime.fromisoformat(raw["updated_at"])
        self._comments_total = raw["comments_total"]
        self._events = raw["events"]

    def get_comments(self):
        return _CommentList(self._comments_total)

    def get_events(self):
        return [SimpleNamespace(**ev) for ev in self._events]


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
    html_by_body = {issue.body: issue.body_html for issue in repo._issues}

    def markdown(text: str) -> str:
        html = html_by_body.get(text)
        if html is None:
            print("warning: body not in fixture, using raw text")
            return text
        return html

    return repo, markdown
