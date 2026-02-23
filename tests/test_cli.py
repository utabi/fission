"""Tests for fission CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from fission.cli import main

SAMPLE_PCB = str(Path(__file__).parent / "fixtures" / "sample.kicad_pcb")


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_doctor() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert "Python" in result.output


def test_extract_stdout() -> None:
    """fission extract がstdoutに正しいJSONを出力する."""
    runner = CliRunner()
    result = runner.invoke(main, ["extract", SAMPLE_PCB])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["project"] == "sample"
    assert data["pcb"]["outline"]["width"] == 80.0
    assert len(data["pcb"]["mount_holes"]) == 4


def test_extract_output_file(tmp_path: Path) -> None:
    """--output オプションでファイル出力される."""
    out_file = tmp_path / "result.json"
    runner = CliRunner()
    result = runner.invoke(main, ["extract", SAMPLE_PCB, "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["project"] == "sample"


def test_extract_compact() -> None:
    """--compact でインデントなしのJSON."""
    runner = CliRunner()
    result = runner.invoke(main, ["extract", SAMPLE_PCB, "--compact"])
    assert result.exit_code == 0
    # compact = 改行なし（1行）
    lines = [line for line in result.output.strip().split("\n") if line.strip()]
    assert len(lines) == 1


def test_extract_nonexistent_file() -> None:
    """存在しないファイルでエラー終了."""
    runner = CliRunner()
    result = runner.invoke(main, ["extract", "/nonexistent/board.kicad_pcb"])
    assert result.exit_code != 0
