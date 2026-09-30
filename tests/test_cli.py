# -*- coding: utf-8 -*-
from typer.testing import CliRunner

from internote import cli

runner = CliRunner()


def install_fakes(monkeypatch, events):
    class FakeClient:
        def __init__(self, token, repo):
            events["client"] = (token, repo)
            self.repo = "REPO_OBJECT"
            self.markdown_to_html = lambda text: f"<p>{text}</p>"

    class FakeGenerator:
        def __init__(self, config, repo, *, repo_name, markdown, root="."):
            events["gen"] = (config, repo, repo_name, markdown, root)

        def run_all(self):
            events["run"] = "all"

        def run_one(self, number):
            events["run"] = ("one", number)

    def fake_load_config(path):
        events["config"] = path
        return "CONFIG_OBJECT"

    monkeypatch.setattr(cli, "GithubClient", FakeClient)
    monkeypatch.setattr(cli, "Generator", FakeGenerator)
    monkeypatch.setattr(cli, "load_config", fake_load_config)


def test_cli_runs_full_build(monkeypatch, tmp_path):
    events = {}
    install_fakes(monkeypatch, events)
    result = runner.invoke(
        cli.app,
        ["TOKEN", "owner/blog", "--config", str(tmp_path / "config.toml")],
    )
    assert result.exit_code == 0, result.output
    assert events["client"] == ("TOKEN", "owner/blog")
    assert events["config"] == str(tmp_path / "config.toml")
    assert events["gen"][0] == "CONFIG_OBJECT"
    assert events["gen"][1] == "REPO_OBJECT"
    assert events["gen"][2] == "owner/blog"
    assert events["gen"][3]("x") == "<p>x</p>"
    assert events["run"] == "all"


def test_cli_single_issue_dashed_option(monkeypatch, tmp_path):
    events = {}
    install_fakes(monkeypatch, events)
    result = runner.invoke(
        cli.app, ["TOKEN", "owner/blog", "--issue-number", "5"]
    )
    assert result.exit_code == 0, result.output
    assert events["run"] == ("one", "5")


def test_cli_single_issue_underscore_option(monkeypatch, tmp_path):
    events = {}
    install_fakes(monkeypatch, events)
    result = runner.invoke(
        cli.app, ["TOKEN", "owner/blog", "--issue_number", "7"]
    )
    assert result.exit_code == 0, result.output
    assert events["run"] == ("one", "7")


def test_cli_rejects_non_numeric_issue(monkeypatch, tmp_path):
    events = {}
    install_fakes(monkeypatch, events)
    result = runner.invoke(
        cli.app, ["TOKEN", "owner/blog", "--issue-number", "abc"]
    )
    assert result.exit_code != 0
    assert "run" not in events


def test_cli_defaults_config_to_config_toml(monkeypatch, tmp_path):
    events = {}
    install_fakes(monkeypatch, events)
    result = runner.invoke(cli.app, ["TOKEN", "owner/blog"])
    assert result.exit_code == 0, result.output
    assert events["config"] == "config.toml"
