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
    token: str = typer.Argument(..., help="GitHub personal access token"),
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
    client = GithubClient(token, repo)
    generator = Generator(
        cfg,
        client.repo,
        repo_name=repo,
        markdown=client.markdown_to_html,
    )
    if issue_number is None:
        generator.run_all()
    else:
        generator.run_one(issue_number)


if __name__ == "__main__":
    app()
