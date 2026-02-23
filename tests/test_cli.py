"""Tests for fission CLI."""

from click.testing import CliRunner

from fission.cli import main


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_doctor() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert "Python" in result.output
