"""レイヤー整合性検証 (PCB↔ケース↔メッシュ)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from fission.schema import EdgeSide, FissionSchema

# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------


class CheckStatus(str, Enum):
    """チェック結果のステータス."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class CheckLevel(str, Enum):
    """チェックレベル."""

    SCHEMA = "schema"
    GEOMETRY = "geometry"
    MESH = "mesh"


@dataclass
class CheckResult:
    """個別チェックの結果."""

    name: str
    status: CheckStatus
    message: str = ""


@dataclass
class CheckReport:
    """全チェック結果の集約."""

    results: list[CheckResult] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return any(r.status == CheckStatus.FAIL for r in self.results)

    @property
    def has_warnings(self) -> bool:
        return any(r.status == CheckStatus.WARN for r in self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.WARN)

    @property
    def skip_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.SKIP)


# ---------------------------------------------------------------------------
# ライブラリ可用性チェック
# ---------------------------------------------------------------------------

_BUILD123D_AVAILABLE: bool | None = None
_TRIMESH_AVAILABLE: bool | None = None


def _has_build123d() -> bool:
    global _BUILD123D_AVAILABLE  # noqa: PLW0603
    if _BUILD123D_AVAILABLE is None:
        try:
            import build123d  # noqa: F401

            _BUILD123D_AVAILABLE = True
        except ImportError:
            _BUILD123D_AVAILABLE = False
    return _BUILD123D_AVAILABLE


def _has_trimesh() -> bool:
    global _TRIMESH_AVAILABLE  # noqa: PLW0603
    if _TRIMESH_AVAILABLE is None:
        try:
            import trimesh  # noqa: F401

            _TRIMESH_AVAILABLE = True
        except ImportError:
            _TRIMESH_AVAILABLE = False
    return _TRIMESH_AVAILABLE


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

BOARD_MIN_MM = 1.0
BOARD_MAX_MM = 5000.0
FDM_MIN_WALL = 1.5
CLEARANCE_MIN_PRACTICAL = 0.5
POST_DIAMETER_MARGIN = 2.0  # CaseGenerator.POST_DIAMETER_MARGIN と同じ

# ---------------------------------------------------------------------------
# Level A: スキーマ検証
# ---------------------------------------------------------------------------


def check_board_dimensions(schema: FissionSchema) -> list[CheckResult]:
    """ボード寸法の妥当性を検証."""
    results: list[CheckResult] = []
    outline = schema.pcb.outline
    for dim_name, value in [("width", outline.width), ("length", outline.length)]:
        name = f"ボード寸法 ({dim_name})"
        if value < BOARD_MIN_MM:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"{value:.2f}mm — 小さすぎます (単位がmmか確認してください)",
            ))
        elif value > BOARD_MAX_MM:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"{value:.2f}mm — 大きすぎます",
            ))
        else:
            results.append(CheckResult(
                name=name, status=CheckStatus.PASS, message=f"{value:.1f}mm"
            ))
    return results


def check_wall_thickness(schema: FissionSchema) -> CheckResult:
    """壁厚がFDM最小値を満たすか検証."""
    wall = schema.enclosure.wall_thickness
    if wall < FDM_MIN_WALL:
        return CheckResult(
            name="壁厚 (FDM最小値)",
            status=CheckStatus.FAIL,
            message=f"{wall:.1f}mm < FDM最小値 {FDM_MIN_WALL}mm",
        )
    if wall < 2.0:
        return CheckResult(
            name="壁厚 (FDM最小値)",
            status=CheckStatus.WARN,
            message=f"{wall:.1f}mm — {FDM_MIN_WALL}mm以上だが2.0mm未満",
        )
    return CheckResult(
        name="壁厚 (FDM最小値)", status=CheckStatus.PASS, message=f"{wall:.1f}mm"
    )


def check_clearance(schema: FissionSchema) -> CheckResult:
    """クリアランスの実用性を検証."""
    clr = schema.enclosure.clearance
    if clr < CLEARANCE_MIN_PRACTICAL:
        return CheckResult(
            name="クリアランス",
            status=CheckStatus.WARN,
            message=f"{clr:.2f}mm < {CLEARANCE_MIN_PRACTICAL}mm — FDM印刷誤差で干渉リスク",
        )
    return CheckResult(
        name="クリアランス", status=CheckStatus.PASS, message=f"{clr:.2f}mm"
    )


def check_mount_holes_in_bounds(schema: FissionSchema) -> list[CheckResult]:
    """マウントホールが基板内にあるか検証."""
    results: list[CheckResult] = []
    outline = schema.pcb.outline
    for hole in schema.pcb.mount_holes:
        name = f"マウントホール境界 ({hole.x:.1f}, {hole.y:.1f})"
        in_bounds = 0 <= hole.x <= outline.width and 0 <= hole.y <= outline.length
        if in_bounds:
            results.append(CheckResult(name=name, status=CheckStatus.PASS))
        else:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"座標がボード外形外 [{outline.width}x{outline.length}mm]",
            ))
    if not schema.pcb.mount_holes:
        results.append(CheckResult(
            name="マウントホール境界",
            status=CheckStatus.WARN,
            message="マウントホールが定義されていません",
        ))
    return results


def check_mount_post_clearance(schema: FissionSchema) -> list[CheckResult]:
    """マウント柱が内壁に干渉しないか検証."""
    results: list[CheckResult] = []
    outline = schema.pcb.outline
    clr = schema.enclosure.clearance

    inner_half_w = (outline.width + clr * 2) / 2
    inner_half_l = (outline.length + clr * 2) / 2

    for hole in schema.pcb.mount_holes:
        post_radius = (hole.diameter + POST_DIAMETER_MARGIN) / 2

        # KiCad PCB座標 → ケース中心原点座標に変換
        cx = hole.x - outline.width / 2
        cy = -(hole.y - outline.length / 2)

        dist_to_x_wall = inner_half_w - abs(cx) - post_radius
        dist_to_y_wall = inner_half_l - abs(cy) - post_radius
        min_dist = min(dist_to_x_wall, dist_to_y_wall)

        name = f"マウント柱クリアランス ({hole.x:.1f}, {hole.y:.1f})"
        if dist_to_x_wall < 0 or dist_to_y_wall < 0:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"マウント柱が内壁に干渉 (X余裕:{dist_to_x_wall:.2f}mm, Y余裕:{dist_to_y_wall:.2f}mm)",
            ))
        elif min_dist < 0.5:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.WARN,
                message=f"マウント柱と内壁の余裕が小さい (最小:{min_dist:.2f}mm)",
            ))
        else:
            results.append(CheckResult(name=name, status=CheckStatus.PASS))
    return results


def check_connector_edge_assignment(schema: FissionSchema) -> list[CheckResult]:
    """コネクタにedgeが割り当てられているか確認."""
    results: list[CheckResult] = []
    for conn in schema.pcb.connectors:
        label = conn.reference or conn.type
        name = f"コネクタエッジ ({label})"
        if conn.edge is None:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.WARN,
                message="edge未設定 — コネクタ開口部がスキップされます",
            ))
        else:
            results.append(CheckResult(name=name, status=CheckStatus.PASS))
    return results


def check_connector_position_consistency(schema: FissionSchema) -> list[CheckResult]:
    """コネクタ位置が宣言edgeと整合するか検証."""
    results: list[CheckResult] = []
    outline = schema.pcb.outline
    margin_threshold = 5.0

    for conn in schema.pcb.connectors:
        if conn.edge is None:
            continue

        label = conn.reference or conn.type
        name = f"コネクタ位置整合 ({label})"

        dist_map = {
            EdgeSide.TOP: conn.position.y,
            EdgeSide.BOTTOM: outline.length - conn.position.y,
            EdgeSide.LEFT: conn.position.x,
            EdgeSide.RIGHT: outline.width - conn.position.x,
        }

        closest_edge = min(dist_map, key=lambda e: dist_map[e])
        declared_dist = dist_map[conn.edge]

        if conn.edge != closest_edge and declared_dist > margin_threshold:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.WARN,
                message=(
                    f"宣言edge={conn.edge.value}だが"
                    f"最近傍辺={closest_edge.value} (距離:{declared_dist:.1f}mm)"
                ),
            ))
        else:
            results.append(CheckResult(name=name, status=CheckStatus.PASS))
    return results


# ---------------------------------------------------------------------------
# Level B: ジオメトリ検証
# ---------------------------------------------------------------------------


def run_geometry_checks(schema: FissionSchema) -> list[CheckResult]:
    """build123d によるジオメトリ検証."""
    if not _has_build123d():
        return [CheckResult(
            name="ジオメトリ検証",
            status=CheckStatus.SKIP,
            message="build123d が見つかりません",
        )]

    from fission.case.generator import CaseGenerator

    results: list[CheckResult] = []
    gen = CaseGenerator(schema)

    # B-1: ケース全体の体積
    try:
        case = gen.generate()
        vol = case.volume
    except Exception as e:
        results.append(CheckResult(
            name="ケース体積",
            status=CheckStatus.FAIL,
            message=f"ジオメトリ生成エラー: {e}",
        ))
        return results

    if vol > 0:
        results.append(CheckResult(
            name="ケース体積",
            status=CheckStatus.PASS,
            message=f"{vol:.1f} mm³",
        ))
    else:
        results.append(CheckResult(
            name="ケース体積",
            status=CheckStatus.FAIL,
            message=f"体積が0以下 ({vol:.3f} mm³)",
        ))

    # B-2: 分割位置
    split_z = gen.split_z
    outer_h = gen.outer_h
    if 0 < split_z < outer_h:
        results.append(CheckResult(
            name="分割位置",
            status=CheckStatus.PASS,
            message=f"split_z={split_z:.2f}mm (outer_h={outer_h:.2f}mm)",
        ))
    else:
        results.append(CheckResult(
            name="分割位置",
            status=CheckStatus.FAIL,
            message=f"split_z={split_z:.2f}mm が範囲外 (0 < z < {outer_h:.2f}mm)",
        ))

    # B-3: top + bottom 体積整合
    import build123d as b3d

    top = b3d.split(
        case, bisect_by=b3d.Plane.XY.offset(split_z), keep=b3d.Keep.TOP
    )
    bottom = b3d.split(
        case, bisect_by=b3d.Plane.XY.offset(split_z), keep=b3d.Keep.BOTTOM
    )
    total = top.volume + bottom.volume
    rel_err = abs(total - vol) / vol if vol > 0 else float("inf")
    if rel_err < 0.01:
        results.append(CheckResult(
            name="Top+Bottom体積整合",
            status=CheckStatus.PASS,
            message=f"誤差 {rel_err * 100:.3f}%",
        ))
    else:
        results.append(CheckResult(
            name="Top+Bottom体積整合",
            status=CheckStatus.WARN,
            message=f"誤差 {rel_err * 100:.2f}%",
        ))

    # B-4: バウンディングボックス
    bb = case.bounding_box()
    actual_w = bb.max.X - bb.min.X
    actual_l = bb.max.Y - bb.min.Y
    actual_h = bb.max.Z - bb.min.Z
    tol = 0.5
    for axis, actual, expected in [
        ("W", actual_w, gen.outer_w),
        ("L", actual_l, gen.outer_l),
        ("H", actual_h, gen.outer_h),
    ]:
        diff = abs(actual - expected)
        name = f"バウンディングボックス ({axis})"
        if diff <= tol:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.PASS,
                message=f"実測:{actual:.2f}mm 期待:{expected:.2f}mm",
            ))
        else:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"実測:{actual:.2f}mm vs 期待:{expected:.2f}mm (差:{diff:.2f}mm)",
            ))

    return results


# ---------------------------------------------------------------------------
# Level C: メッシュ検証
# ---------------------------------------------------------------------------


def run_mesh_checks(
    schema: FissionSchema,
    stl_path: Path | None = None,
) -> list[CheckResult]:
    """trimesh によるSTLメッシュ検証."""
    if not _has_trimesh():
        return [CheckResult(
            name="メッシュ検証",
            status=CheckStatus.SKIP,
            message="trimesh が見つかりません",
        )]

    import trimesh

    # STLパスが指定されていない場合はビルドして一時ファイルに書き出す
    tmp_stl: Path | None = None
    if stl_path is None:
        if not _has_build123d():
            return [CheckResult(
                name="メッシュ検証",
                status=CheckStatus.SKIP,
                message="STLパス未指定かつbuild123dなし — --stl オプションでSTLを指定してください",
            )]
        from fission.case.generator import CaseGenerator

        gen = CaseGenerator(schema)
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".stl")
        tmp_stl = Path(tmp_name)
        import os

        os.close(tmp_fd)
        gen.export_stl(tmp_stl)
        stl_path = tmp_stl

    results: list[CheckResult] = []

    try:
        mesh: Any = trimesh.load(str(stl_path))
    except Exception as e:
        return [CheckResult(
            name="STL読み込み",
            status=CheckStatus.FAIL,
            message=f"STL読み込み失敗: {e}",
        )]
    finally:
        if tmp_stl is not None and tmp_stl.exists():
            tmp_stl.unlink()

    # C-1: Watertight
    if mesh.is_watertight:
        results.append(CheckResult(name="Watertight（水密）", status=CheckStatus.PASS))
    else:
        results.append(CheckResult(
            name="Watertight（水密）",
            status=CheckStatus.FAIL,
            message="メッシュが閉じていません — 3Dプリント不可",
        ))

    # C-2: 法線方向の一貫性
    if mesh.is_winding_consistent:
        results.append(CheckResult(name="法線方向の一貫性", status=CheckStatus.PASS))
    else:
        results.append(CheckResult(
            name="法線方向の一貫性",
            status=CheckStatus.FAIL,
            message="法線方向が一貫していません",
        ))

    # C-3: 体積 > 0
    vol = mesh.volume
    if vol > 0:
        results.append(CheckResult(
            name="メッシュ体積",
            status=CheckStatus.PASS,
            message=f"{vol:.1f} mm³",
        ))
    else:
        results.append(CheckResult(
            name="メッシュ体積",
            status=CheckStatus.FAIL,
            message=f"体積が0以下 ({vol:.1f} mm³) — 法線反転の可能性",
        ))

    # C-4: STL寸法と設計値の照合
    from fission.case.generator import CaseGenerator

    gen = CaseGenerator(schema)
    bounds = mesh.bounding_box.bounds
    actual_w = bounds[1][0] - bounds[0][0]
    actual_l = bounds[1][1] - bounds[0][1]
    actual_h = bounds[1][2] - bounds[0][2]
    tol = 1.0
    for axis, actual, expected in [
        ("W", actual_w, gen.outer_w),
        ("L", actual_l, gen.outer_l),
        ("H", actual_h, gen.outer_h),
    ]:
        diff = abs(actual - expected)
        name = f"STL寸法照合 ({axis})"
        if diff <= tol:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.PASS,
                message=f"実測:{actual:.2f}mm 期待:{expected:.2f}mm",
            ))
        else:
            results.append(CheckResult(
                name=name,
                status=CheckStatus.WARN,
                message=f"実測:{actual:.2f}mm vs 期待:{expected:.2f}mm (差:{diff:.2f}mm)",
            ))

    return results


# ---------------------------------------------------------------------------
# メインエントリポイント
# ---------------------------------------------------------------------------


def run_checks(
    schema: FissionSchema,
    levels: set[CheckLevel] | None = None,
    stl_path: Path | None = None,
) -> CheckReport:
    """全チェックを実行してCheckReportを返す."""
    if levels is None:
        levels = {CheckLevel.SCHEMA, CheckLevel.GEOMETRY, CheckLevel.MESH}

    report = CheckReport()

    if CheckLevel.SCHEMA in levels:
        report.results.extend(check_board_dimensions(schema))
        report.results.append(check_wall_thickness(schema))
        report.results.append(check_clearance(schema))
        report.results.extend(check_mount_holes_in_bounds(schema))
        report.results.extend(check_mount_post_clearance(schema))
        report.results.extend(check_connector_edge_assignment(schema))
        report.results.extend(check_connector_position_consistency(schema))

    if CheckLevel.GEOMETRY in levels:
        report.results.extend(run_geometry_checks(schema))

    if CheckLevel.MESH in levels:
        report.results.extend(run_mesh_checks(schema, stl_path=stl_path))

    return report
