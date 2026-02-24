"""Fission MCP Server — AIエージェント向けツール群."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP  
mcp = FastMCP("Fission")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _load_schema(input_path: str) -> Any:
    """ファイルパスからFissionSchemaを読み込む (.kicad_pcb or .json)."""
    from fission.schema import FissionSchema

    path = Path(input_path)
    if path.suffix == ".kicad_pcb":
        from fission.kicad.parser import parse_kicad_pcb

        return parse_kicad_pcb(path)
    elif path.suffix == ".json":
        return FissionSchema.model_validate_json(path.read_text(encoding="utf-8"))
    else:
        msg = f"未対応のファイル形式: {path.suffix} (.kicad_pcb または .json を指定してください)"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def extract_pcb_schema(pcb_path: str) -> str:
    """KiCad PCBファイルからFissionスキーマJSONを抽出する.

    Args:
        pcb_path: .kicad_pcb ファイルのパス

    Returns:
        FissionスキーマのJSON文字列
    """
    from fission.kicad.parser import parse_kicad_pcb

    schema = parse_kicad_pcb(pcb_path)
    return schema.model_dump_json(indent=2)


@mcp.tool()
def generate_case(
    schema_json: str,
    output_path: str,
    format: str = "step",
) -> dict[str, Any]:
    """FissionスキーマJSONからケースSTEP/STLを生成する.

    Args:
        schema_json: FissionスキーマのJSON文字列
        output_path: 出力ファイルパス
        format: 出力形式 ("step" or "stl")

    Returns:
        {"success": True, "path": "..."} または {"success": False, "error": "..."}
    """
    from fission.case.generator import CaseGenerator
    from fission.schema import FissionSchema

    try:
        schema = FissionSchema.model_validate_json(schema_json)
        gen = CaseGenerator(schema)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if format.lower() == "stl":
            gen.export_stl(out)
        else:
            gen.export_step(out)

        return {"success": True, "path": str(out)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def export_manufacturing(
    pcb_path: str,
    output_dir: str = "output",
    skip_gerbers: bool = False,
    skip_case: bool = False,
) -> dict[str, Any]:
    """PCBファイルから製造ファイルを一括生成する.

    Args:
        pcb_path: .kicad_pcb ファイルのパス
        output_dir: 出力ディレクトリ
        skip_gerbers: Gerber/Drill/PnP生成をスキップ
        skip_case: ケース生成をスキップ

    Returns:
        {"all_ok": True/False, "steps": [...]} 各ステップの成否
    """
    from fission.export import run_full_export

    result = run_full_export(
        Path(pcb_path),
        Path(output_dir),
        skip_gerbers=skip_gerbers,
        skip_case=skip_case,
    )
    return {
        "all_ok": result.all_ok,
        "steps": [asdict(s) for s in result.steps],
    }


@mcp.tool()
def run_design_checks(
    input_path: str,
    levels: list[str] | None = None,
    stl_path: str | None = None,
) -> dict[str, Any]:
    """PCBスキーマのレイヤー整合性を検証する.

    Args:
        input_path: .kicad_pcb ファイルまたは .json スキーマファイル
        levels: チェックレベル ("schema", "geometry", "mesh") のリスト。省略時は全て
        stl_path: メッシュ検証に使用する既存STLファイル

    Returns:
        {"has_failures": ..., "pass_count": ..., "results": [...]}
    """
    from fission.check import CheckLevel, run_checks

    schema = _load_schema(input_path)

    check_levels: set[CheckLevel] | None = None
    if levels:
        check_levels = {CheckLevel(lv) for lv in levels}

    stl = Path(stl_path) if stl_path else None
    report = run_checks(schema, levels=check_levels, stl_path=stl)

    return {
        "has_failures": report.has_failures,
        "has_warnings": report.has_warnings,
        "pass_count": report.pass_count,
        "fail_count": report.fail_count,
        "warn_count": report.warn_count,
        "results": [asdict(r) for r in report.results],
    }


@mcp.tool()
def modify_enclosure_config(
    schema_json: str,
    wall_thickness: float | None = None,
    clearance: float | None = None,
    material: str | None = None,
) -> str:
    """ケース設定を変更して更新済みスキーマJSONを返す.

    Args:
        schema_json: 現在のFissionスキーマJSON
        wall_thickness: 壁厚 (mm)
        clearance: クリアランス (mm)
        material: 素材名 (例: "PLA", "ABS", "PETG")

    Returns:
        更新後のFissionスキーマJSON文字列
    """
    from fission.schema import FissionSchema

    schema = FissionSchema.model_validate_json(schema_json)

    if wall_thickness is not None:
        schema.enclosure.wall_thickness = wall_thickness
    if clearance is not None:
        schema.enclosure.clearance = clearance
    if material is not None:
        schema.enclosure.material = material

    return schema.model_dump_json(indent=2)


@mcp.tool()
def check_dependencies() -> dict[str, Any]:
    """Fissionの依存ライブラリの状態を確認する.

    Returns:
        {"dependencies": [{"name": ..., "version": ..., "ok": True/False}, ...]}
    """
    deps: list[dict[str, Any]] = []

    # Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    deps.append({
        "name": "Python",
        "version": py_ver,
        "ok": sys.version_info >= (3, 10),
    })

    # build123d
    try:
        import build123d  
        deps.append({
            "name": "build123d",
            "version": getattr(build123d, "__version__", "unknown"),
            "ok": True,
        })
    except ImportError:
        deps.append({"name": "build123d", "version": "not installed", "ok": False})

    # trimesh
    try:
        import trimesh  
        deps.append({
            "name": "trimesh",
            "version": getattr(trimesh, "__version__", "unknown"),
            "ok": True,
        })
    except ImportError:
        deps.append({"name": "trimesh", "version": "not installed", "ok": False})

    # kicad-cli
    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli:
        try:
            result = subprocess.run(
                ["kicad-cli", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            deps.append({
                "name": "kicad-cli",
                "version": result.stdout.strip(),
                "ok": True,
            })
        except (subprocess.TimeoutExpired, FileNotFoundError):
            deps.append({"name": "kicad-cli", "version": "error", "ok": False})
    else:
        deps.append({"name": "kicad-cli", "version": "not found", "ok": False})

    return {"dependencies": deps}


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("fission://schema-spec")
def schema_spec() -> str:
    """FissionSchemaのJSON Schema定義.

    AIがFissionのデータ構造を理解するための参照資料。
    """
    from fission.schema import FissionSchema

    return json.dumps(FissionSchema.model_json_schema(), indent=2)


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------


def main() -> None:
    """MCPサーバーをstdioトランスポートで起動."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
