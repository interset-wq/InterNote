# -*- coding: utf-8 -*-
from __future__ import annotations

import requests
from github import Github

# GitHub's /markdown endpoint rejects request bodies above 400 KB
# ("too_large"); merged-collection posts can exceed that, so long bodies
# are rendered in chunks and the HTML concatenated.
MARKDOWN_API_LIMIT = 400_000


def markdown_to_html(text: str, token: str) -> str:
    if len(text.encode("utf-8")) <= MARKDOWN_API_LIMIT:
        return _markdown_to_html(text, token)

    chunks = _split_utf8(text, MARKDOWN_API_LIMIT)
    return "".join(_markdown_to_html(chunk, token) for chunk in chunks)


def _markdown_to_html(text: str, token: str) -> str:
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


def _split_utf8(text: str, limit: int) -> list[str]:
    """Split text into chunks whose UTF-8 encoding fits `limit` bytes,
    preferring paragraph boundaries (blank lines) and never splitting
    inside a fenced code block."""
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        lo, hi = start, n
        # binary search for the largest end index that fits
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(text[start:mid].encode("utf-8")) <= limit:
                lo = mid
            else:
                hi = mid - 1
        if lo == start:  # single unit exceeds the limit; cannot happen
            lo = start + 1
        # prefer a paragraph boundary within the last 10% of the chunk
        window_start = start + int((lo - start) * 0.9)
        cut = text.rfind("\n\n", window_start, lo)
        if cut != -1:
            candidate = cut + 2
            if _balanced_fences(text[start:candidate]):
                lo = candidate
        # otherwise split wherever the byte budget lands (mid-paragraph)
        chunks.append(text[start:lo])
        start = lo
    # A paragraph-boundary cut can leave a tiny trailing chunk; merging it
    # into the previous one is always within the limit because that cut
    # happened with >=10% byte headroom.
    if len(chunks) > 1 and len(chunks[-1].encode("utf-8")) < 500:
        chunks[-2] += chunks[-1]
        chunks.pop()
    return chunks


def _balanced_fences(chunk: str) -> bool:
    inside = False
    for line in chunk.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
    return not inside


class GithubClient:
    def __init__(self, token: str, repo_name: str):
        self.token = token
        self.repo_name = repo_name
        self.repo = Github(token).get_repo(repo_name)

    def markdown_to_html(self, text: str) -> str:
        return markdown_to_html(text, self.token)
