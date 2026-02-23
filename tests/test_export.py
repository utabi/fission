"""Tests for manufacturing file export."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from fission.cli import main
from fission.export import ExportResult, StepResult, run_full_export

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PCB = FIXTURES / "sample.kicad_pcb"


def test_export_schema_json(tmp_path: Path) -> None:
    """スキーマJSONが生成される."""
    from fission.export import export_schema_json

    result = export_schema_json(SAMPLE_PCB, tmp_path)
    assert result.success
    assert (tmp_path / "sample.json").exists()


def test_export_enclosure(tmp_path: Path) -> None:
    """ケースSTEP/STLが生成される."""
    from fission.export import export_enclosure

    result = export_enclosure(SAMPLE_PCB, tmp_path)
    assert result.success
    assert (tmp_path / "enclosure.step").exists()
    assert (tmp_path / "enclosure.stl").exists()


def test_full_export_skip_gerbers(tmp_path: Path) -> None:
    """--no-gerbers でkicad-cli不要のエクスポート."""
    result = run_full_export(
        SAMPLE_PCB,
        tmp_path,
        skip_gerbers=True,
        skip_case=False,
    )
    # スキーマ + ケースの2ステップのみ
    assert len(result.steps) == 2
    assert all(s.success for s in result.steps)
    assert (tmp_path / "sample.json").exists()
    assert (tmp_path / "enclosure.step").exists()


def test_full_export_skip_case(tmp_path: Path) -> None:
    """--no-case でケース生成スキップ."""
    result = run_full_export(
        SAMPLE_PCB,
        tmp_path,
        skip_gerbers=True,
        skip_case=True,
    )
    # スキーマのみ
    assert len(result.steps) == 1
    assert result.steps[0].name == "Fission Schema"
    assert result.steps[0].success


def test_full_export_no_kicad(tmp_path: Path) -> None:
    """kicad-cliがない場合、Gerber系はエラーになるがスキーマ/ケースは成功."""
    with patch("fission.export.shutil.which", return_value=None):
        result = run_full_export(SAMPLE_PCB, tmp_path)
    gerber_steps = [s for s in result.steps if s.name in ("Gerber", "Drill", "Pick & Place", "PCB 3D STEP")]
    assert all(not s.success for s in gerber_steps)
    schema_step = next(s for s in result.steps if s.name == "Fission Schema")
    assert schema_step.success
    enclosure_step = next(s for s in result.steps if s.name == "Enclosure")
    assert enclosure_step.success


def test_export_result_all_ok() -> None:
    """ExportResult.all_okの動作."""
    r = ExportResult(steps=[
        StepResult(name="A", success=True),
        StepResult(name="B", success=True),
    ])
    assert r.all_ok
    r.steps.append(StepResult(name="C", success=False, message="fail"))
    assert not r.all_ok


# --- CLI ---


def test_cli_export_skip_gerbers(tmp_path: Path) -> None:
    """CLI: fission export --no-gerbers."""
    out = tmp_path / "fab"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["export", str(SAMPLE_PCB), "-o", str(out), "--no-gerbers"],
    )
    assert result.exit_code == 0
    assert (out / "sample.json").exists()
    assert (out / "enclosure.step").exists()


def test_cli_export_skip_all(tmp_path: Path) -> None:
    """CLI: fission export --no-gerbers --no-case (スキーマのみ)."""
    out = tmp_path / "fab"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["export", str(SAMPLE_PCB), "-o", str(out), "--no-gerbers", "--no-case"],
    )
    assert result.exit_code == 0
    assert (out / "sample.json").exists()
    assert not (out / "enclosure.step").exists()
