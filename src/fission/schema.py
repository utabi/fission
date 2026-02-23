"""Fission Unified Schema — PCBとエンクロージャの中間表現."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 共通型
# ---------------------------------------------------------------------------


class Position2D(BaseModel):
    """2D座標 (mm単位)."""

    x: float
    y: float


class Position3D(BaseModel):
    """3D座標 (mm単位)."""

    x: float
    y: float
    z: float = 0.0


class Dimensions3D(BaseModel):
    """3D寸法 (mm単位)."""

    width: float = Field(gt=0, description="X方向の寸法")
    height: float = Field(gt=0, description="Z方向の寸法")
    depth: float = Field(gt=0, description="Y方向の寸法")


# ---------------------------------------------------------------------------
# PCB データ
# ---------------------------------------------------------------------------


class BoardOutline(BaseModel):
    """基板外形 (バウンディングボックス)."""

    width: float = Field(gt=0, description="X方向の最大寸法 (mm)")
    length: float = Field(gt=0, description="Y方向の最大寸法 (mm)")
    thickness: float = Field(default=1.6, gt=0, description="基板厚 (mm)")


class MountHole(BaseModel):
    """マウントホール."""

    x: float = Field(description="中心X座標 (mm)")
    y: float = Field(description="中心Y座標 (mm)")
    diameter: float = Field(gt=0, description="穴径 (mm)")


class EdgeSide(str, Enum):
    """基板のどの辺にコネクタがあるか."""

    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class Connector(BaseModel):
    """コネクタ情報."""

    type: str = Field(description="コネクタの種類 (例: USB-C, USB-A, HDMI)")
    reference: str = Field(default="", description="KiCadのリファレンス (例: J1)")
    position: Position3D = Field(description="コネクタ中心位置")
    dimensions: Dimensions3D = Field(description="コネクタ外形寸法")
    edge: EdgeSide | None = Field(
        default=None,
        description="基板のどの辺に面しているか",
    )


class ComponentHeight(BaseModel):
    """部品の最大高さ (基板面からの高さ)."""

    top: float = Field(default=0.0, ge=0, description="表面の最大部品高さ (mm)")
    bottom: float = Field(default=0.0, ge=0, description="裏面の最大部品高さ (mm)")


class PcbData(BaseModel):
    """PCBから抽出されたデータ."""

    outline: BoardOutline
    mount_holes: list[MountHole] = Field(default_factory=list)
    connectors: list[Connector] = Field(default_factory=list)
    max_component_height: ComponentHeight = Field(default_factory=ComponentHeight)


# ---------------------------------------------------------------------------
# エンクロージャ設定
# ---------------------------------------------------------------------------


class SplitType(str, Enum):
    """ケースの分割方式."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class EnclosureConfig(BaseModel):
    """エンクロージャの設定 (ケース設計パラメータ)."""

    wall_thickness: float = Field(default=2.0, gt=0)
    clearance: float = Field(default=1.0, ge=0)
    material: str = Field(default="PLA")
    split: SplitType = Field(default=SplitType.HORIZONTAL)


# ---------------------------------------------------------------------------
# ルートスキーマ
# ---------------------------------------------------------------------------


class FissionSchema(BaseModel):
    """Fission統一スキーマのルートオブジェクト."""

    schema_version: str = Field(default="1.0", description="スキーマバージョン")
    project: str = Field(description="プロジェクト名")
    pcb: PcbData
    enclosure: EnclosureConfig = Field(default_factory=EnclosureConfig)
