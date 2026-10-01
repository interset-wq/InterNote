# -*- coding: utf-8 -*-
from __future__ import annotations

import typer

from .config import load_config
from .generator import Generator
from .github_client import GithubClient

app = typer.Typer(
    add_completion=False,
    help="InterNote - static blog generator based on GitHub Issues.",
)


@app.command()
def main(
    token: str = typer.Argument(
        None, help="GitHub personal access token (not needed with --fixtures)"
    ),
    repo: str = typer.Argument(..., help="Repository in owner/name form"),
    issue_number: str = typer.Option(
        None,
        "--issue-number",
        "--issue_number",
        help="Only rebuild the single issue with this number",
    ),
    config: str = typer.Option(
        "config.toml", "--config", "-c", help="Path to the config file"
    ),
    fixtures: str = typer.Option(
        None,
        "--fixtures",
        help="Build offline from a fixture JSON (scripts/fetch_fixtures.py)",
    ),
) -> None:
    """Build the static site from GitHub Issues."""
    if issue_number is not None:
        issue_number = issue_number.strip()
        if not issue_number:
            issue_number = None
    if issue_number is not None and not issue_number.isdigit():
        raise typer.BadParameter(
            "issue number must be numeric", param_hint="--issue-number"
        )

    cfg = load_config(config)
    if fixtures:
        from .fixtures import load_repo

        repo_obj, markdown = load_repo(fixtures)
    else:
        if not token:
            raise typer.BadParameter(
                "token is required unless --fixtures is given"
            )
        client = GithubClient(token, repo)
        repo_obj = client.repo
        markdown = client.markdown_to_html
    generator = Generator(cfg, repo_obj, repo_name=repo, markdown=markdown)
    if issue_number is None:
        generator.run_all()
    else:
        generator.run_one(issue_number)


if __name__ == "__main__":
    app()
