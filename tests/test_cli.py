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


# --- generate-case ---


def _make_schema_json(tmp_path: Path) -> Path:
    """extractでスキーマJSONを生成."""
    out = tmp_path / "schema.json"
    runner = CliRunner()
    result = runner.invoke(main, ["extract", SAMPLE_PCB, "-o", str(out)])
    assert result.exit_code == 0
    return out


def test_generate_case_step(tmp_path: Path) -> None:
    """generate-case でSTEPファイルが生成される."""
    schema_json = _make_schema_json(tmp_path)
    out = tmp_path / "case.step"
    runner = CliRunner()
    result = runner.invoke(main, ["generate-case", str(schema_json), "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert out.stat().st_size > 0


def test_generate_case_stl(tmp_path: Path) -> None:
    """generate-case でSTLファイルが生成される."""
    schema_json = _make_schema_json(tmp_path)
    out = tmp_path / "case.stl"
    runner = CliRunner()
    result = runner.invoke(main, ["generate-case", str(schema_json), "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()


def test_generate_case_split(tmp_path: Path) -> None:
    """--split で分割STLが生成される."""
    schema_json = _make_schema_json(tmp_path)
    out = tmp_path / "case.stl"
    runner = CliRunner()
    result = runner.invoke(main, ["generate-case", str(schema_json), "-o", str(out), "--split"])
    assert result.exit_code == 0
    assert (tmp_path / "case_top.stl").exists()
    assert (tmp_path / "case_bottom.stl").exists()
