"""Build123dによるケース自動生成."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fission.schema import EdgeSide, FissionSchema

# Build123d は重いので遅延import
_b3d: Any = None


def _get_b3d() -> Any:
    """build123d モジュールを遅延ロード."""
    global _b3d  # noqa: PLW0603
    if _b3d is None:
        import build123d as b3d

        _b3d = b3d
    return _b3d


class CaseGenerator:
    """FissionスキーマからBuild123dでケースを生成する."""

    # マウント柱の外径マージン（穴径に対して片側+1mm = 直径+2mm）
    POST_DIAMETER_MARGIN = 2.0
    # コネクタ開口部のマージン（片側0.5mm）
    CUTOUT_MARGIN = 1.0

    def __init__(self, schema: FissionSchema) -> None:
        self.schema = schema
        self.pcb = schema.pcb
        self.encl = schema.enclosure

        # 寸法計算
        wall = self.encl.wall_thickness
        clr = self.encl.clearance
        outline = self.pcb.outline
        comp = self.pcb.max_component_height

        self.wall = wall
        self.clearance = clr

        # 外形寸法
        self.outer_w = outline.width + clr * 2 + wall * 2
        self.outer_l = outline.length + clr * 2 + wall * 2
        self.outer_h = (
            wall  # 底面壁
            + comp.bottom  # 裏面部品
            + outline.thickness  # 基板厚
            + comp.top  # 表面部品
            + clr  # 上面クリアランス
            + wall  # 天面壁
        )

        # PCB底面のZ位置（ケース底面内側から）
        self.pcb_bottom_z = wall + comp.bottom
        # 分割位置Z（基板中央、ケース底面=0基準）
        self.split_z = self.pcb_bottom_z + outline.thickness / 2

        # マウント柱高さ（底面壁上面からPCB底面まで）
        self.standoff_h = comp.bottom if comp.bottom > 0 else 2.0

    def generate(self) -> Any:
        """ケース全体のSolidを生成."""
        b3d = _get_b3d()

        # ケース原点 = ケース中心。Z軸はケース底面中央
        # Build123d の Box は中心原点で生成されるので、底面を z=0 にシフト
        outer = b3d.Pos(0, 0, self.outer_h / 2) * b3d.Box(
            self.outer_w, self.outer_l, self.outer_h
        )

        # 内部空洞
        inner_w = self.pcb.outline.width + self.clearance * 2
        inner_l = self.pcb.outline.length + self.clearance * 2
        inner_h = self.outer_h - self.wall  # 底面壁は残す、天面は開口
        inner = b3d.Pos(0, 0, self.wall + inner_h / 2) * b3d.Box(
            inner_w, inner_l, inner_h
        )

        case = outer - inner

        case = self._add_mount_posts(case)
        case = self._add_connector_cutouts(case)

        return case

    def generate_top(self) -> Any:
        """上半分を生成."""
        b3d = _get_b3d()
        case = self.generate()
        result = b3d.split(case, bisect_by=b3d.Plane.XY.offset(self.split_z), keep=b3d.Keep.TOP)
        return result

    def generate_bottom(self) -> Any:
        """下半分を生成."""
        b3d = _get_b3d()
        case = self.generate()
        result = b3d.split(
            case, bisect_by=b3d.Plane.XY.offset(self.split_z), keep=b3d.Keep.BOTTOM
        )
        return result

    def export_step(self, path: str | Path) -> None:
        """ケース全体をSTEP出力."""
        b3d = _get_b3d()
        case = self.generate()
        b3d.export_step(case, str(path))

    def export_stl(self, path: str | Path) -> None:
        """ケース全体をSTL出力."""
        b3d = _get_b3d()
        case = self.generate()
        b3d.export_stl(case, str(path))

    def export_split_stl(self, top_path: str | Path, bottom_path: str | Path) -> None:
        """top/bottom分割してSTL出力."""
        b3d = _get_b3d()
        top = self.generate_top()
        bottom = self.generate_bottom()
        b3d.export_stl(top, str(top_path))
        b3d.export_stl(bottom, str(bottom_path))

    # ------------------------------------------------------------------
    # 内部メソッド
    # ------------------------------------------------------------------

    def _pcb_to_case_xy(self, pcb_x: float, pcb_y: float) -> tuple[float, float]:
        """KiCad PCB座標 → ケース中心原点座標に変換.

        KiCad: 原点が左上、Y下向き
        ケース: 原点が中心、Y上向き
        PCBのバウンディングボックス中心をケース原点にマッピング。
        """
        outline = self.pcb.outline
        # PCB中心を原点に
        cx = pcb_x - outline.width / 2
        cy = -(pcb_y - outline.length / 2)  # Y軸反転
        return cx, cy

    def _add_mount_posts(self, case: Any) -> Any:
        """マウント柱を追加."""
        b3d = _get_b3d()

        for hole in self.pcb.mount_holes:
            cx, cy = self._pcb_to_case_xy(hole.x, hole.y)

            post_d = hole.diameter + self.POST_DIAMETER_MARGIN
            post_h = self.standoff_h

            # 柱（底面壁の上面から）
            post_z = self.wall + post_h / 2
            post = b3d.Pos(cx, cy, post_z) * b3d.Cylinder(
                post_d / 2, post_h
            )
            case = case + post

            # ネジ穴（柱を貫通）
            screw_hole = b3d.Pos(cx, cy, post_z) * b3d.Cylinder(
                hole.diameter / 2, post_h + 0.1
            )
            case = case - screw_hole

        return case

    def _add_connector_cutouts(self, case: Any) -> Any:
        """コネクタ開口部を追加."""
        b3d = _get_b3d()
        outline = self.pcb.outline
        margin = self.CUTOUT_MARGIN

        for conn in self.pcb.connectors:
            if conn.edge is None:
                continue

            cx, cy = self._pcb_to_case_xy(conn.position.x, conn.position.y)

            cut_w = conn.dimensions.width + margin * 2
            cut_h = conn.dimensions.height + margin * 2
            cut_depth = self.wall * 3  # 壁を確実に貫通

            # コネクタのZ位置（ケース内部でのPCB上面基準）
            conn_z = self.pcb_bottom_z + outline.thickness + conn.dimensions.height / 2

            edge = EdgeSide(conn.edge) if isinstance(conn.edge, str) else conn.edge

            if edge == EdgeSide.TOP:
                # Y+方向の壁（KiCadのY=0 = ケースのY+方向）
                wall_y = self.outer_l / 2
                cutout = b3d.Pos(cx, wall_y, conn_z) * b3d.Box(
                    cut_w, cut_depth, cut_h
                )
            elif edge == EdgeSide.BOTTOM:
                wall_y = -self.outer_l / 2
                cutout = b3d.Pos(cx, wall_y, conn_z) * b3d.Box(
                    cut_w, cut_depth, cut_h
                )
            elif edge == EdgeSide.RIGHT:
                wall_x = self.outer_w / 2
                cutout = b3d.Pos(wall_x, cy, conn_z) * b3d.Box(
                    cut_depth, cut_w, cut_h
                )
            elif edge == EdgeSide.LEFT:
                wall_x = -self.outer_w / 2
                cutout = b3d.Pos(wall_x, cy, conn_z) * b3d.Box(
                    cut_depth, cut_w, cut_h
                )
            else:
                continue

            case = case - cutout

        return case
