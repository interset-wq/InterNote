# -*- coding: utf-8 -*-
"""Fetch GitHub Issues via the gh CLI into a fixture JSON.

The fixture lets the generator build fully offline (markdown is
pre-rendered at fetch time) and gives unit tests stable, real-shaped
data:

    python scripts/fetch_fixtures.py <owner/repo> \
        -o tests/fixtures/<owner>__<name>.json

Requires an authenticated gh CLI; no token is passed through args.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _gh(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ("gh", *args), input=stdin, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(
            "gh {} failed: {}".format(" ".join(args), result.stderr.strip())
        )
    return result.stdout


def _gh_json(path: str):
    return json.loads(_gh("api", path))


def _gh_markdown(text: str) -> str:
    payload = json.dumps({"text": text, "mode": "gfm"})
    return _gh("api", "markdown", "--method", "POST", "--input", "-", stdin=payload)


def fetch(repo: str) -> dict:
    issues = _gh_json("repos/{}/issues?state=open&per_page=100".format(repo))
    data = {
        "repo": repo,
        "labels": [
            {"name": lb["name"], "color": lb["color"]}
            for lb in _gh_json("repos/{}/labels?per_page=100".format(repo))
        ],
        "issues": [],
    }
    for issue in issues:
        if "pull_request" in issue:
            continue
        number = issue["number"]
        comments = _gh_json(
            "repos/{}/issues/{}/comments?per_page=100".format(repo, number)
        )
        events = _gh_json(
            "repos/{}/issues/{}/events?per_page=100".format(repo, number)
        )
        body = issue["body"] or ""
        data["issues"].append(
            {
                "number": number,
                "title": issue["title"],
                "body": body,
                "body_html": _gh_markdown(body),
                "labels": [
                    {"name": lb["name"], "color": lb["color"]}
                    for lb in issue["labels"]
                ],
                "created_at": issue["created_at"],
                "updated_at": issue["updated_at"],
                "comments_total": len(comments),
                "events": [{"event": ev["event"]} for ev in events],
            }
        )
        print("fetched issue #{}: {}".format(number, issue["title"]))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch issues via gh api into a fixture JSON"
    )
    parser.add_argument("repo", help="repository in owner/name form")
    parser.add_argument(
        "-o",
        "--out",
        default="tests/fixtures/fixture.json",
        help="output path (default: tests/fixtures/fixture.json)",
    )
    args = parser.parse_args()
    data = fetch(args.repo)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote {} ({} issues)".format(out, len(data["issues"])))


if __name__ == "__main__":
    main()
