"""Tests for Fission unified schema."""

import json

import pytest
from pydantic import ValidationError

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
    SplitType,
)


def _make_schema() -> FissionSchema:
    """テスト用の最小スキーマを生成."""
    return FissionSchema(
        project="test-board",
        pcb=PcbData(
            outline=BoardOutline(width=80.0, length=60.0, thickness=1.6),
            mount_holes=[
                MountHole(x=5.0, y=5.0, diameter=3.2),
                MountHole(x=75.0, y=55.0, diameter=3.2),
            ],
            connectors=[
                Connector(
                    type="USB-C",
                    reference="J1",
                    position=Position3D(x=40.0, y=60.0, z=1.6),
                    dimensions=Dimensions3D(width=9.0, height=3.2, depth=7.5),
                    edge=EdgeSide.TOP,
                ),
            ],
            max_component_height=ComponentHeight(top=12.0, bottom=2.5),
        ),
    )


def test_schema_roundtrip() -> None:
    """JSONシリアライズ→デシリアライズで情報が失われない."""
    schema = _make_schema()
    json_str = schema.model_dump_json()
    restored = FissionSchema.model_validate_json(json_str)
    assert restored == schema


def test_schema_defaults() -> None:
    """デフォルト値が正しく設定される."""
    schema = FissionSchema(
        project="minimal",
        pcb=PcbData(outline=BoardOutline(width=50.0, length=30.0)),
    )
    assert schema.schema_version == "1.0"
    assert schema.pcb.mount_holes == []
    assert schema.pcb.connectors == []
    assert schema.pcb.max_component_height.top == 0.0
    assert schema.pcb.max_component_height.bottom == 0.0
    assert schema.enclosure.wall_thickness == 2.0
    assert schema.enclosure.clearance == 1.0
    assert schema.enclosure.material == "PLA"
    assert schema.enclosure.split == SplitType.HORIZONTAL


def test_schema_validation_negative_width() -> None:
    """負のwidthでValidationError."""
    with pytest.raises(ValidationError):
        BoardOutline(width=-10.0, length=60.0)


def test_schema_validation_zero_diameter() -> None:
    """0のdiameterでValidationError."""
    with pytest.raises(ValidationError):
        MountHole(x=5.0, y=5.0, diameter=0.0)


def test_schema_validation_invalid_edge() -> None:
    """不正なedge値でValidationError."""
    with pytest.raises(ValidationError):
        Connector(
            type="USB-C",
            position=Position3D(x=0, y=0),
            dimensions=Dimensions3D(width=9.0, height=3.2, depth=7.5),
            edge="invalid",  # type: ignore[arg-type]
        )


def test_schema_json_output_readable() -> None:
    """JSON出力が人間とAIに読みやすい."""
    schema = _make_schema()
    json_str = schema.model_dump_json(indent=2)
    parsed = json.loads(json_str)
    assert parsed["project"] == "test-board"
    assert parsed["pcb"]["outline"]["width"] == 80.0
    assert len(parsed["pcb"]["mount_holes"]) == 2
    assert parsed["pcb"]["connectors"][0]["type"] == "USB-C"


def test_schema_json_schema_generation() -> None:
    """JSON Schemaが生成できる."""
    json_schema = FissionSchema.model_json_schema()
    assert "properties" in json_schema
    assert "project" in json_schema["properties"]


def test_enclosure_config_custom() -> None:
    """カスタムエンクロージャ設定."""
    schema = FissionSchema(
        project="custom",
        pcb=PcbData(outline=BoardOutline(width=50.0, length=30.0)),
        enclosure=EnclosureConfig(
            wall_thickness=3.0,
            clearance=0.5,
            material="ABS",
            split=SplitType.VERTICAL,
        ),
    )
    assert schema.enclosure.wall_thickness == 3.0
    assert schema.enclosure.split == SplitType.VERTICAL
