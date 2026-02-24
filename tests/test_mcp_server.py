"""Tests for Fission MCP Server tools."""

import json
from pathlib import Path

from fission.mcp_server import (
    check_dependencies,
    export_manufacturing,
    extract_pcb_schema,
    generate_case,
    modify_enclosure_config,
    run_design_checks,
    schema_spec,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PCB = str(FIXTURES / "sample.kicad_pcb")


def _make_schema_json() -> str:
    """テスト用スキーマJSONを生成."""
    return extract_pcb_schema(SAMPLE_PCB)


# ---------------------------------------------------------------------------
# extract_pcb_schema
# ---------------------------------------------------------------------------


def test_extract_pcb_schema() -> None:
    """KiCad PCBからスキーマJSONが抽出される."""
    result = extract_pcb_schema(SAMPLE_PCB)
    data = json.loads(result)
    assert data["project"] == "sample"
    assert data["pcb"]["outline"]["width"] == 80.0
    assert len(data["pcb"]["mount_holes"]) == 4


def test_extract_pcb_schema_invalid_file() -> None:
    """存在しないファイルでエラー."""
    try:
        extract_pcb_schema("/nonexistent/board.kicad_pcb")
        assert False, "Should have raised"
    except (FileNotFoundError, ValueError):
        pass


# ---------------------------------------------------------------------------
# generate_case
# ---------------------------------------------------------------------------


def test_generate_case_step(tmp_path: Path) -> None:
    """スキーマJSONからSTEPファイルを生成."""
    schema_json = _make_schema_json()
    out = str(tmp_path / "case.step")
    result = generate_case(schema_json, out, format="step")
    assert result["success"] is True
    assert Path(result["path"]).exists()


def test_generate_case_stl(tmp_path: Path) -> None:
    """スキーマJSONからSTLファイルを生成."""
    schema_json = _make_schema_json()
    out = str(tmp_path / "case.stl")
    result = generate_case(schema_json, out, format="stl")
    assert result["success"] is True
    assert Path(result["path"]).exists()


def test_generate_case_invalid_json() -> None:
    """不正なJSONでエラーが返る (例外ではなく)."""
    result = generate_case("{invalid}", "/tmp/out.step")
    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# export_manufacturing
# ---------------------------------------------------------------------------


def test_export_manufacturing_skip_gerbers(tmp_path: Path) -> None:
    """--skip_gerbers でスキーマ+ケースが生成される."""
    out_dir = str(tmp_path / "fab")
    result = export_manufacturing(
        SAMPLE_PCB, out_dir, skip_gerbers=True, skip_case=False
    )
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) == 2  # schema + enclosure
    assert all(s["success"] for s in result["steps"])


def test_export_manufacturing_skip_all(tmp_path: Path) -> None:
    """skip_gerbers + skip_case でスキーマのみ."""
    out_dir = str(tmp_path / "fab")
    result = export_manufacturing(
        SAMPLE_PCB, out_dir, skip_gerbers=True, skip_case=True
    )
    assert len(result["steps"]) == 1
    assert result["steps"][0]["name"] == "Fission Schema"


# ---------------------------------------------------------------------------
# run_design_checks
# ---------------------------------------------------------------------------


def test_run_design_checks_schema_level() -> None:
    """スキーマレベルのチェックがパスする."""
    result = run_design_checks(SAMPLE_PCB, levels=["schema"])
    assert result["pass_count"] > 0
    assert result["has_failures"] is False


def test_run_design_checks_all_levels() -> None:
    """全レベルのチェックが実行される."""
    result = run_design_checks(SAMPLE_PCB)
    assert result["pass_count"] > 10
    assert isinstance(result["results"], list)


def test_run_design_checks_json_input(tmp_path: Path) -> None:
    """JSONファイルを入力として受け付ける."""
    schema_json = _make_schema_json()
    json_file = tmp_path / "schema.json"
    json_file.write_text(schema_json, encoding="utf-8")
    result = run_design_checks(str(json_file), levels=["schema"])
    assert result["has_failures"] is False


# ---------------------------------------------------------------------------
# modify_enclosure_config
# ---------------------------------------------------------------------------


def test_modify_wall_thickness() -> None:
    """壁厚が変更される."""
    schema_json = _make_schema_json()
    updated = modify_enclosure_config(schema_json, wall_thickness=3.0)
    data = json.loads(updated)
    assert data["enclosure"]["wall_thickness"] == 3.0


def test_modify_clearance() -> None:
    """クリアランスが変更される."""
    schema_json = _make_schema_json()
    updated = modify_enclosure_config(schema_json, clearance=0.5)
    data = json.loads(updated)
    assert data["enclosure"]["clearance"] == 0.5


def test_modify_material() -> None:
    """素材が変更される."""
    schema_json = _make_schema_json()
    updated = modify_enclosure_config(schema_json, material="ABS")
    data = json.loads(updated)
    assert data["enclosure"]["material"] == "ABS"


def test_modify_multiple_fields() -> None:
    """複数フィールドの同時変更."""
    schema_json = _make_schema_json()
    updated = modify_enclosure_config(
        schema_json, wall_thickness=2.5, clearance=0.8, material="PETG"
    )
    data = json.loads(updated)
    assert data["enclosure"]["wall_thickness"] == 2.5
    assert data["enclosure"]["clearance"] == 0.8
    assert data["enclosure"]["material"] == "PETG"


def test_modify_no_changes() -> None:
    """引数なしでも元のJSONが返る."""
    schema_json = _make_schema_json()
    updated = modify_enclosure_config(schema_json)
    original = json.loads(schema_json)
    result = json.loads(updated)
    assert original["enclosure"] == result["enclosure"]


# ---------------------------------------------------------------------------
# check_dependencies
# ---------------------------------------------------------------------------


def test_check_dependencies() -> None:
    """依存ライブラリ情報が返る."""
    result = check_dependencies()
    assert "dependencies" in result
    names = [d["name"] for d in result["dependencies"]]
    assert "Python" in names
    assert "build123d" in names


def test_check_dependencies_python_ok() -> None:
    """Python >= 3.10 がOK判定."""
    result = check_dependencies()
    python = next(d for d in result["dependencies"] if d["name"] == "Python")
    assert python["ok"] is True


# ---------------------------------------------------------------------------
# schema_spec resource
# ---------------------------------------------------------------------------


def test_schema_spec() -> None:
    """有効なJSON Schemaが返る."""
    result = schema_spec()
    data = json.loads(result)
    assert "properties" in data
    assert "project" in data["properties"]
    assert "pcb" in data["properties"]
