"""製造ファイル一括エクスポート (kicad-cli ラッパー + ケース生成)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StepResult:
    """個別ステップの実行結果."""

    name: str
    success: bool
    message: str = ""
    files: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    """エクスポート全体の結果."""

    steps: list[StepResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(s.success for s in self.steps)


def _run_cmd(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """コマンドを実行."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def export_gerbers(pcb_path: Path, output_dir: Path) -> StepResult:
    """Gerberファイルを生成."""
    gerber_dir = output_dir / "gerbers"
    gerber_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = _run_cmd([
            "kicad-cli",
            "pcb",
            "export",
            "gerbers",
            "--output",
            str(gerber_dir) + "/",
            "--board-plot-params",
            str(pcb_path),
        ])
        if result.returncode != 0:
            return StepResult(
                name="Gerber",
                success=False,
                message=result.stderr.strip() or f"exit code {result.returncode}",
            )
        files = [f.name for f in gerber_dir.iterdir() if f.is_file()]
        return StepResult(name="Gerber", success=True, files=files)
    except subprocess.TimeoutExpired:
        return StepResult(name="Gerber", success=False, message="timeout")
    except FileNotFoundError:
        return StepResult(name="Gerber", success=False, message="kicad-cli not found")


def export_drill(pcb_path: Path, output_dir: Path) -> StepResult:
    """ドリルファイルを生成."""
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = _run_cmd([
            "kicad-cli",
            "pcb",
            "export",
            "drill",
            "--output",
            str(output_dir) + "/",
            "--format",
            "excellon",
            "--excellon-units",
            "mm",
            "--generate-map",
            str(pcb_path),
        ])
        if result.returncode != 0:
            return StepResult(
                name="Drill",
                success=False,
                message=result.stderr.strip() or f"exit code {result.returncode}",
            )
        files = [
            f.name for f in output_dir.iterdir() if f.is_file() and f.suffix in (".drl", ".pdf")
        ]
        return StepResult(name="Drill", success=True, files=files)
    except subprocess.TimeoutExpired:
        return StepResult(name="Drill", success=False, message="timeout")
    except FileNotFoundError:
        return StepResult(name="Drill", success=False, message="kicad-cli not found")


def export_pos(pcb_path: Path, output_dir: Path) -> StepResult:
    """ピック＆プレースファイルを生成."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{pcb_path.stem}.pos"

    try:
        result = _run_cmd([
            "kicad-cli",
            "pcb",
            "export",
            "pos",
            "--output",
            str(out_file),
            "--format",
            "csv",
            "--units",
            "mm",
            str(pcb_path),
        ])
        if result.returncode != 0:
            return StepResult(
                name="Pick & Place",
                success=False,
                message=result.stderr.strip() or f"exit code {result.returncode}",
            )
        files = [out_file.name] if out_file.exists() else []
        return StepResult(name="Pick & Place", success=True, files=files)
    except subprocess.TimeoutExpired:
        return StepResult(name="Pick & Place", success=False, message="timeout")
    except FileNotFoundError:
        return StepResult(name="Pick & Place", success=False, message="kicad-cli not found")


def export_pcb_step(pcb_path: Path, output_dir: Path) -> StepResult:
    """PCBの3D STEPファイルを生成."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{pcb_path.stem}_3d.step"

    try:
        result = _run_cmd([
            "kicad-cli",
            "pcb",
            "export",
            "step",
            "--output",
            str(out_file),
            "--force",
            str(pcb_path),
        ])
        if result.returncode != 0:
            return StepResult(
                name="PCB 3D STEP",
                success=False,
                message=result.stderr.strip() or f"exit code {result.returncode}",
            )
        files = [out_file.name] if out_file.exists() else []
        return StepResult(name="PCB 3D STEP", success=True, files=files)
    except subprocess.TimeoutExpired:
        return StepResult(name="PCB 3D STEP", success=False, message="timeout")
    except FileNotFoundError:
        return StepResult(name="PCB 3D STEP", success=False, message="kicad-cli not found")


def export_schema_json(pcb_path: Path, output_dir: Path) -> StepResult:
    """FissionスキーマJSONを生成."""
    from fission.kicad.parser import parse_kicad_pcb

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{pcb_path.stem}.json"

    try:
        schema = parse_kicad_pcb(pcb_path)
        out_file.write_text(schema.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return StepResult(name="Fission Schema", success=True, files=[out_file.name])
    except Exception as e:
        return StepResult(name="Fission Schema", success=False, message=str(e))


def export_enclosure(pcb_path: Path, output_dir: Path) -> StepResult:
    """ケース STEP/STL を生成."""
    from fission.case.generator import CaseGenerator
    from fission.kicad.parser import parse_kicad_pcb

    output_dir.mkdir(parents=True, exist_ok=True)
    step_file = output_dir / "enclosure.step"
    stl_file = output_dir / "enclosure.stl"

    try:
        schema = parse_kicad_pcb(pcb_path)
        gen = CaseGenerator(schema)
        gen.export_step(step_file)
        gen.export_stl(stl_file)
        return StepResult(
            name="Enclosure",
            success=True,
            files=[step_file.name, stl_file.name],
        )
    except Exception as e:
        return StepResult(name="Enclosure", success=False, message=str(e))


def run_full_export(
    pcb_path: Path,
    output_dir: Path,
    *,
    skip_gerbers: bool = False,
    skip_case: bool = False,
) -> ExportResult:
    """製造ファイルを一括生成.

    Args:
        pcb_path: .kicad_pcb ファイル
        output_dir: 出力ディレクトリ
        skip_gerbers: Gerber/Drill/PnP/STEP をスキップ
        skip_case: ケース生成をスキップ
    """
    result = ExportResult()

    # kicad-cli の存在確認
    has_kicad = shutil.which("kicad-cli") is not None

    if not skip_gerbers:
        if not has_kicad:
            result.steps.append(
                StepResult(name="Gerber", success=False, message="kicad-cli not found")
            )
            result.steps.append(
                StepResult(name="Drill", success=False, message="kicad-cli not found")
            )
            result.steps.append(
                StepResult(name="Pick & Place", success=False, message="kicad-cli not found")
            )
            result.steps.append(
                StepResult(name="PCB 3D STEP", success=False, message="kicad-cli not found")
            )
        else:
            result.steps.append(export_gerbers(pcb_path, output_dir))
            result.steps.append(export_drill(pcb_path, output_dir))
            result.steps.append(export_pos(pcb_path, output_dir))
            result.steps.append(export_pcb_step(pcb_path, output_dir))

    # Fission スキーマ（kicad-cli不要）
    result.steps.append(export_schema_json(pcb_path, output_dir))

    # ケース生成（kicad-cli不要）
    if not skip_case:
        result.steps.append(export_enclosure(pcb_path, output_dir))

    return result
