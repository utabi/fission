"""KiCad .kicad_pcb ファイルからFissionスキーマへの変換."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sexpdata
from sexpdata import Symbol

from fission.schema import (
    BoardOutline,
    ComponentHeight,
    Connector,
    Dimensions3D,
    EdgeSide,
    FissionSchema,
    MountHole,
    PcbData,
    Position3D,
)

# ---------------------------------------------------------------------------
# コネクタ種別推定
# ---------------------------------------------------------------------------

_CONNECTOR_PATTERNS: dict[str, list[str]] = {
    "USB-C": ["USB_C", "Type-C", "TypeC"],
    "USB-A": ["USB_A", "Type-A", "TypeA"],
    "USB-Micro": ["USB_Micro", "Micro_USB", "MicroUSB"],
    "USB-Mini": ["USB_Mini", "Mini_USB", "MiniUSB"],
    "HDMI": ["HDMI"],
    "RJ45": ["RJ45", "8P8C"],
    "DC-Jack": ["Jack_DC", "BarrelJack", "DC_Jack"],
    "Pin-Header": ["PinHeader", "Pin_Header"],
    "JST": ["JST"],
    "SD-Card": ["SD_Card", "microSD", "MicroSD"],
}

_DEFAULT_CONNECTOR_DIMENSIONS: dict[str, Dimensions3D] = {
    "USB-C": Dimensions3D(width=9.0, height=3.2, depth=7.5),
    "USB-A": Dimensions3D(width=14.0, height=6.5, depth=14.0),
    "USB-Micro": Dimensions3D(width=8.0, height=3.0, depth=5.5),
    "USB-Mini": Dimensions3D(width=7.0, height=4.0, depth=5.5),
    "HDMI": Dimensions3D(width=15.0, height=6.0, depth=11.2),
    "RJ45": Dimensions3D(width=16.0, height=13.5, depth=21.5),
    "DC-Jack": Dimensions3D(width=9.0, height=11.0, depth=14.0),
    "Pin-Header": Dimensions3D(width=2.54, height=8.5, depth=2.54),
    "JST": Dimensions3D(width=5.0, height=4.5, depth=6.0),
    "SD-Card": Dimensions3D(width=14.0, height=2.0, depth=15.0),
}

_FALLBACK_DIMENSIONS = Dimensions3D(width=10.0, height=5.0, depth=10.0)


# ---------------------------------------------------------------------------
# S式ツリー検索ヘルパー
# ---------------------------------------------------------------------------


def _symbol_name(node: Any) -> str | None:
    """sexpdata の Symbol からタグ名を取得."""
    if isinstance(node, Symbol):
        return str(node.value())
    return None


def _find_nodes(tree: list[Any], tag: str) -> list[list[Any]]:
    """S式ツリーから指定タグの子ノードを全て取得 (1階層)."""
    results: list[list[Any]] = []
    for item in tree:
        if isinstance(item, list) and len(item) > 0 and _symbol_name(item[0]) == tag:
            results.append(item)
    return results


def _find_node(tree: list[Any], tag: str) -> list[Any] | None:
    """S式ツリーから指定タグの子ノードを1つ取得."""
    for item in tree:
        if isinstance(item, list) and len(item) > 0 and _symbol_name(item[0]) == tag:
            return item
    return None


def _get_layer(node: list[Any]) -> str:
    """ノードの layer 属性を取得."""
    layer_node = _find_node(node, "layer")
    if layer_node is None or len(layer_node) < 2:
        return ""
    val = layer_node[1]
    return str(val).strip('"')


def _get_property_value(footprint: list[Any], prop_name: str) -> str:
    """フットプリントの property ノードから値を取得."""
    for node in _find_nodes(footprint, "property"):
        if len(node) >= 3 and str(node[1]).strip('"') == prop_name:
            return str(node[2]).strip('"')
    return ""


# ---------------------------------------------------------------------------
# 抽出ロジック
# ---------------------------------------------------------------------------


def _extract_board_thickness(tree: list[Any]) -> float:
    """基板厚を取得."""
    general = _find_node(tree, "general")
    if general is None:
        return 1.6
    thickness_node = _find_node(general, "thickness")
    if thickness_node is None or len(thickness_node) < 2:
        return 1.6
    return float(thickness_node[1])


def _extract_board_outline(tree: list[Any], thickness: float) -> BoardOutline:
    """Edge.Cutsからバウンディングボックスを計算."""
    points: list[tuple[float, float]] = []

    # gr_line: (gr_line (start X Y) (end X Y) ... (layer "Edge.Cuts"))
    for node in _find_nodes(tree, "gr_line"):
        if _get_layer(node) != "Edge.Cuts":
            continue
        start = _find_node(node, "start")
        end = _find_node(node, "end")
        if start and len(start) >= 3:
            points.append((float(start[1]), float(start[2])))
        if end and len(end) >= 3:
            points.append((float(end[1]), float(end[2])))

    # gr_rect: (gr_rect (start X Y) (end X Y) ... (layer "Edge.Cuts"))
    for node in _find_nodes(tree, "gr_rect"):
        if _get_layer(node) != "Edge.Cuts":
            continue
        start = _find_node(node, "start")
        end = _find_node(node, "end")
        if start and len(start) >= 3:
            points.append((float(start[1]), float(start[2])))
        if end and len(end) >= 3:
            points.append((float(end[1]), float(end[2])))

    # gr_arc: (gr_arc (start X Y) (mid X Y) (end X Y) ... (layer "Edge.Cuts"))
    for node in _find_nodes(tree, "gr_arc"):
        if _get_layer(node) != "Edge.Cuts":
            continue
        for tag in ("start", "mid", "end"):
            pt = _find_node(node, tag)
            if pt and len(pt) >= 3:
                points.append((float(pt[1]), float(pt[2])))

    # gr_poly: (gr_poly (pts (xy X Y) ...) ... (layer "Edge.Cuts"))
    for node in _find_nodes(tree, "gr_poly"):
        if _get_layer(node) != "Edge.Cuts":
            continue
        pts = _find_node(node, "pts")
        if pts:
            for xy in _find_nodes(pts, "xy"):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

    # gr_circle: (gr_circle (center X Y) (end X Y) ... (layer "Edge.Cuts"))
    for node in _find_nodes(tree, "gr_circle"):
        if _get_layer(node) != "Edge.Cuts":
            continue
        center = _find_node(node, "center")
        end = _find_node(node, "end")
        if center and end and len(center) >= 3 and len(end) >= 3:
            cx, cy = float(center[1]), float(center[2])
            ex, ey = float(end[1]), float(end[2])
            r = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            points.extend([(cx - r, cy - r), (cx + r, cy + r)])

    if not points:
        raise ValueError("Edge.Cutsレイヤーにボード外形が見つかりません")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(xs) - min(xs)
    length = max(ys) - min(ys)

    if width <= 0 or length <= 0:
        raise ValueError(f"ボード外形の寸法が不正です: {width} x {length}")

    return BoardOutline(width=width, length=length, thickness=thickness)


def _extract_mount_holes(tree: list[Any]) -> list[MountHole]:
    """MountingHoleフットプリントからホール位置・径を抽出."""
    holes: list[MountHole] = []

    for fp in _find_nodes(tree, "footprint"):
        if len(fp) < 2:
            continue
        fp_name = str(fp[1]).strip('"')

        if "MountingHole" not in fp_name and "mountinghole" not in fp_name.lower():
            continue

        at_node = _find_node(fp, "at")
        if at_node is None or len(at_node) < 3:
            continue
        fp_x, fp_y = float(at_node[1]), float(at_node[2])

        # パッドからドリル径を取得
        diameter = 0.0
        for pad in _find_nodes(fp, "pad"):
            drill = _find_node(pad, "drill")
            if drill and len(drill) >= 2:
                diameter = float(drill[1])
                break

        if diameter > 0:
            holes.append(MountHole(x=fp_x, y=fp_y, diameter=diameter))

    return holes


def _guess_connector_type(fp_name: str) -> str | None:
    """フットプリント名からコネクタ種別を推定."""
    for conn_type, patterns in _CONNECTOR_PATTERNS.items():
        if any(p.lower() in fp_name.lower() for p in patterns):
            return conn_type
    if "connector" in fp_name.lower():
        return "Unknown"
    return None


def _estimate_edge(
    x: float, y: float, outline: BoardOutline, min_x: float, min_y: float
) -> EdgeSide | None:
    """コネクタがボードのどの辺に近いかを推定."""
    # ボード外形のmin座標からの相対位置で判定
    rel_x = x - min_x
    rel_y = y - min_y

    margin = 3.0  # 辺から3mm以内をエッジとみなす
    distances = {
        EdgeSide.TOP: rel_y,  # KiCadではY=0が上
        EdgeSide.BOTTOM: outline.length - rel_y,
        EdgeSide.LEFT: rel_x,
        EdgeSide.RIGHT: outline.width - rel_x,
    }
    closest = min(distances, key=distances.get)  # type: ignore[arg-type]
    if distances[closest] <= margin:
        return closest
    return None


def _extract_connectors(tree: list[Any], outline: BoardOutline) -> list[Connector]:
    """コネクタフットプリントから情報を抽出."""
    connectors: list[Connector] = []

    # Edge.Cutsの原点を求める（_extract_board_outlineと同じロジック）
    xs: list[float] = []
    ys: list[float] = []
    for node in _find_nodes(tree, "gr_line"):
        if _get_layer(node) != "Edge.Cuts":
            continue
        start = _find_node(node, "start")
        end = _find_node(node, "end")
        if start and len(start) >= 3:
            xs.append(float(start[1]))
            ys.append(float(start[2]))
        if end and len(end) >= 3:
            xs.append(float(end[1]))
            ys.append(float(end[2]))

    min_x = min(xs) if xs else 0.0
    min_y = min(ys) if ys else 0.0

    for fp in _find_nodes(tree, "footprint"):
        if len(fp) < 2:
            continue
        fp_name = str(fp[1]).strip('"')

        # MountingHoleはスキップ
        if "MountingHole" in fp_name or "mountinghole" in fp_name.lower():
            continue

        conn_type = _guess_connector_type(fp_name)
        if conn_type is None:
            continue

        at_node = _find_node(fp, "at")
        if at_node is None or len(at_node) < 3:
            continue
        fp_x, fp_y = float(at_node[1]), float(at_node[2])

        reference = _get_property_value(fp, "Reference")
        layer = _get_layer(fp)
        z = outline.thickness if "F." in layer else 0.0

        dimensions = _DEFAULT_CONNECTOR_DIMENSIONS.get(conn_type, _FALLBACK_DIMENSIONS)
        edge = _estimate_edge(fp_x, fp_y, outline, min_x, min_y)

        connectors.append(
            Connector(
                type=conn_type,
                reference=reference,
                position=Position3D(x=fp_x, y=fp_y, z=z),
                dimensions=dimensions,
                edge=edge,
            )
        )

    return connectors


def _extract_max_component_height(tree: list[Any]) -> ComponentHeight:
    """フットプリントの配置面から最大部品高さを推定."""
    top_has_components = False
    bottom_has_components = False

    for fp in _find_nodes(tree, "footprint"):
        if len(fp) < 2:
            continue
        fp_name = str(fp[1]).strip('"')

        # MountingHoleはスキップ
        if "MountingHole" in fp_name or "mountinghole" in fp_name.lower():
            continue

        layer = _get_layer(fp)
        if "F." in layer:
            top_has_components = True
        elif "B." in layer:
            bottom_has_components = True

    # ヒューリスティクス: 部品がある面にデフォルト高さを設定
    top = 2.5 if top_has_components else 0.0
    bottom = 1.0 if bottom_has_components else 0.0

    return ComponentHeight(top=top, bottom=bottom)


# ---------------------------------------------------------------------------
# メインAPI
# ---------------------------------------------------------------------------


def parse_kicad_pcb(pcb_path: str | Path) -> FissionSchema:
    """KiCad PCBファイルを読み込んでFissionSchemaに変換する.

    Args:
        pcb_path: .kicad_pcb ファイルのパス

    Returns:
        FissionSchema オブジェクト

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        ValueError: パース不能なファイルの場合
    """
    path = Path(pcb_path)
    if not path.exists():
        raise FileNotFoundError(f"PCBファイルが見つかりません: {path}")
    if path.suffix != ".kicad_pcb":
        raise ValueError(f"KiCad PCBファイル (.kicad_pcb) を指定してください: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        tree: list[Any] = sexpdata.loads(text)
    except Exception as e:
        raise ValueError(f"S式のパースに失敗しました: {e}") from e

    # トップレベルが kicad_pcb であることを確認
    if not (isinstance(tree, list) and len(tree) > 0 and _symbol_name(tree[0]) == "kicad_pcb"):
        raise ValueError("有効な .kicad_pcb ファイルではありません")

    thickness = _extract_board_thickness(tree)
    outline = _extract_board_outline(tree, thickness)
    mount_holes = _extract_mount_holes(tree)
    connectors = _extract_connectors(tree, outline)
    component_height = _extract_max_component_height(tree)

    project_name = path.stem

    return FissionSchema(
        project=project_name,
        pcb=PcbData(
            outline=outline,
            mount_holes=mount_holes,
            connectors=connectors,
            max_component_height=component_height,
        ),
    )
