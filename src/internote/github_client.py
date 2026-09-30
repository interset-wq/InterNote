# -*- coding: utf-8 -*-
from __future__ import annotations

import requests
from github import Github


def markdown_to_html(text: str, token: str) -> str:
    payload = {"text": text, "mode": "gfm"}
    headers = {"Authorization": "token {}".format(token)}
    try:
        response = requests.post(
            "https://api.github.com/markdown", json=payload, headers=headers
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        raise Exception("markdown2html error: {}".format(e)) from e


class GithubClient:
    def __init__(self, token: str, repo_name: str):
        self.token = token
        self.repo_name = repo_name
        self.repo = Github(token).get_repo(repo_name)

    def markdown_to_html(self, text: str) -> str:
        return markdown_to_html(text, self.token)
