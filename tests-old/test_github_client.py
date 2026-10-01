# -*- coding: utf-8 -*-
import pytest
import requests

from internote.github_client import markdown_to_html


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_markdown_to_html_posts_to_github_api(monkeypatch):
    captured = {}

    def fake_post(url, json, headers):
        captured.update(url=url, json=json, headers=headers)
        return FakeResponse("<p>hi</p>")

    monkeypatch.setattr("internote.github_client.requests.post", fake_post)

    out = markdown_to_html("hello", token="tok")

    assert out == "<p>hi</p>"
    assert captured["url"] == "https://api.github.com/markdown"
    assert captured["json"] == {"text": "hello", "mode": "gfm"}
    assert captured["headers"]["Authorization"] == "token tok"


def test_markdown_to_html_wraps_request_errors(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("internote.github_client.requests.post", fake_post)

    with pytest.raises(Exception, match="markdown2html"):
        markdown_to_html("x", token="t")
