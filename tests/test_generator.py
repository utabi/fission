"""Tests for case generator."""

from pathlib import Path

import pytest

from fission.case.generator import CaseGenerator
from fission.schema import (
    BoardOutline,
    ComponentHeight,
    Connector,
    Dimensions3D,
    EdgeSide,
    EnclosureConfig,
    FissionSchema,
    MountHole,
    PcbData,
    Position3D,
)


def _make_schema() -> FissionSchema:
    """テスト用スキーマ."""
    return FissionSchema(
        project="test-case",
        pcb=PcbData(
            outline=BoardOutline(width=80.0, length=60.0, thickness=1.6),
            mount_holes=[
                MountHole(x=5.0, y=5.0, diameter=3.2),
                MountHole(x=75.0, y=5.0, diameter=3.2),
                MountHole(x=5.0, y=55.0, diameter=3.2),
                MountHole(x=75.0, y=55.0, diameter=3.2),
            ],
            connectors=[
                Connector(
                    type="USB-C",
                    reference="J1",
                    position=Position3D(x=40.0, y=0.0, z=1.6),
                    dimensions=Dimensions3D(width=9.0, height=3.2, depth=7.5),
                    edge=EdgeSide.TOP,
                ),
            ],
            max_component_height=ComponentHeight(top=2.5, bottom=1.0),
        ),
        enclosure=EnclosureConfig(wall_thickness=2.0, clearance=1.0),
    )


def test_basic_case_generation() -> None:
    """スキーマからSolidが生成される."""
    gen = CaseGenerator(_make_schema())
    case = gen.generate()
    assert case.volume > 0


def test_case_dimensions() -> None:
    """外形寸法が正しい."""
    schema = _make_schema()
    gen = CaseGenerator(schema)
    # outer = 80 + 1*2 + 2*2 = 86
    assert gen.outer_w == pytest.approx(86.0)
    # outer = 60 + 1*2 + 2*2 = 66
    assert gen.outer_l == pytest.approx(66.0)
    # height = 2 + 1.0 + 1.6 + 2.5 + 1.0 + 2 = 10.1
    assert gen.outer_h == pytest.approx(10.1)


def test_case_bounding_box() -> None:
    """生成されたケースのバウンディングボックスが寸法と一致."""
    gen = CaseGenerator(_make_schema())
    case = gen.generate()
    bb = case.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(86.0, abs=0.1)
    assert bb.max.Y - bb.min.Y == pytest.approx(66.0, abs=0.1)


def test_mount_posts_add_volume() -> None:
    """マウント柱でケースの体積が増加する."""
    schema = _make_schema()
    schema_no_holes = schema.model_copy(
        update={"pcb": schema.pcb.model_copy(update={"mount_holes": []})}
    )
    gen_with = CaseGenerator(schema)
    gen_without = CaseGenerator(schema_no_holes)
    assert gen_with.generate().volume > gen_without.generate().volume


def test_connector_cutout_reduces_volume() -> None:
    """コネクタ開口部でケースの体積が減少する."""
    schema = _make_schema()
    schema_no_conn = schema.model_copy(
        update={"pcb": schema.pcb.model_copy(update={"connectors": []})}
    )
    gen_with = CaseGenerator(schema)
    gen_without = CaseGenerator(schema_no_conn)
    assert gen_with.generate().volume < gen_without.generate().volume


def test_split_top_bottom() -> None:
    """top/bottom分割が動作する."""
    gen = CaseGenerator(_make_schema())
    top = gen.generate_top()
    bottom = gen.generate_bottom()
    assert top.volume > 0
    assert bottom.volume > 0
    full = gen.generate().volume
    # top + bottom ≒ full（分割面の微小誤差を許容）
    assert top.volume + bottom.volume == pytest.approx(full, rel=0.01)


def test_export_step(tmp_path: Path) -> None:
    """STEPファイルが出力される."""
    gen = CaseGenerator(_make_schema())
    out = tmp_path / "case.step"
    gen.export_step(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_stl(tmp_path: Path) -> None:
    """STLファイルが出力される."""
    gen = CaseGenerator(_make_schema())
    out = tmp_path / "case.stl"
    gen.export_stl(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_split_stl(tmp_path: Path) -> None:
    """分割STLファイルが出力される."""
    gen = CaseGenerator(_make_schema())
    top = tmp_path / "top.stl"
    bottom = tmp_path / "bottom.stl"
    gen.export_split_stl(top, bottom)
    assert top.exists()
    assert bottom.exists()
    assert top.stat().st_size > 0
    assert bottom.stat().st_size > 0
