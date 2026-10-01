# -*- coding: utf-8 -*-
"""Shared test doubles.

RecordingUrlopen lives here rather than in either test module so that
test_search.py and test_generator.py can both assert on the exact HTTP
calls a build makes without `tests` needing to be an importable package.
"""
import io
import json


class RecordingUrlopen:
    """Stands in for urllib.request.urlopen and records what was sent.

    Pass `fail_with` to simulate a transport or HTTP failure.
    """

    def __init__(self, fail_with=None):
        self.calls = []
        self.fail_with = fail_with

    def __call__(self, request, timeout=None):
        self.calls.append(
            {
                "url": request.full_url,
                "payload": json.loads(request.data.decode("utf-8")),
                "headers": dict(request.header_items()),
                "method": request.get_method(),
            }
        )
        if self.fail_with is not None:
            raise self.fail_with

        body = json.dumps({"taskID": 1, "objectIDs": ["a"]}).encode("utf-8")

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
                return False

        return FakeResponse(body)

    @property
    def paths(self):
        return [call["url"].split("/1/indexes/")[1] for call in self.calls]

    def batch(self):
        """The request bodies of the single addObject batch call."""
        for call in self.calls:
            if call["url"].endswith("/batch"):
                return call["payload"]["requests"]
        raise AssertionError("no batch call was made")