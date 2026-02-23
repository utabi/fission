"""Tests for KiCad PCB parser."""

from pathlib import Path

import pytest

from fission.kicad.parser import parse_kicad_pcb

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PCB = FIXTURES / "sample.kicad_pcb"


def test_parse_sample_pcb() -> None:
    """サンプルPCBファイルをパースして基本項目が取得できる."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    assert schema.project == "sample"
    assert schema.schema_version == "1.0"


def test_board_outline_dimensions() -> None:
    """Edge.Cutsから正しいバウンディングボックスが得られる."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    assert schema.pcb.outline.width == pytest.approx(80.0)
    assert schema.pcb.outline.length == pytest.approx(60.0)


def test_board_thickness() -> None:
    """基板厚がgeneral.thicknessから正しく取得される."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    assert schema.pcb.outline.thickness == pytest.approx(1.6)


def test_mount_holes_detected() -> None:
    """MountingHoleフットプリントが正しく検出される."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    holes = schema.pcb.mount_holes
    assert len(holes) == 4
    # 全て3.2mmドリル
    for hole in holes:
        assert hole.diameter == pytest.approx(3.2)
    # 四隅の座標確認
    coords = {(h.x, h.y) for h in holes}
    assert (5.0, 5.0) in coords
    assert (75.0, 5.0) in coords
    assert (5.0, 55.0) in coords
    assert (75.0, 55.0) in coords


def test_usb_connector_detected() -> None:
    """USB-Cコネクタが正しく検出される."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    usb = [c for c in schema.pcb.connectors if c.type == "USB-C"]
    assert len(usb) == 1
    assert usb[0].reference == "J1"
    assert usb[0].position.x == pytest.approx(40.0)
    assert usb[0].position.y == pytest.approx(0.0)
    assert usb[0].edge == "top"


def test_pin_header_detected() -> None:
    """ピンヘッダコネクタが検出される."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    headers = [c for c in schema.pcb.connectors if c.type == "Pin-Header"]
    assert len(headers) == 1
    assert headers[0].reference == "J2"


def test_component_height() -> None:
    """部品高さが推定される."""
    schema = parse_kicad_pcb(SAMPLE_PCB)
    assert schema.pcb.max_component_height.top > 0
    assert schema.pcb.max_component_height.bottom > 0


def test_json_roundtrip() -> None:
    """パース結果をJSON化→復元できる."""
    from fission.schema import FissionSchema

    schema = parse_kicad_pcb(SAMPLE_PCB)
    json_str = schema.model_dump_json()
    restored = FissionSchema.model_validate_json(json_str)
    assert restored.pcb.outline.width == schema.pcb.outline.width
    assert len(restored.pcb.mount_holes) == len(schema.pcb.mount_holes)


def test_nonexistent_file() -> None:
    """存在しないファイルでFileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        parse_kicad_pcb("/nonexistent/board.kicad_pcb")


def test_wrong_extension(tmp_path: Path) -> None:
    """拡張子が違うファイルでValueError."""
    bad_file = tmp_path / "board.txt"
    bad_file.write_text("hello")
    with pytest.raises(ValueError, match="kicad_pcb"):
        parse_kicad_pcb(bad_file)


def test_invalid_content(tmp_path: Path) -> None:
    """不正な内容のファイルでValueError."""
    bad_file = tmp_path / "board.kicad_pcb"
    bad_file.write_text("not s-expression content !!!")
    with pytest.raises(ValueError):
        parse_kicad_pcb(bad_file)


def test_no_edge_cuts(tmp_path: Path) -> None:
    """Edge.CutsがないファイルでValueError."""
    pcb = tmp_path / "no_outline.kicad_pcb"
    pcb.write_text('(kicad_pcb (version 20240108) (general (thickness 1.6)))')
    with pytest.raises(ValueError, match="Edge.Cuts"):
        parse_kicad_pcb(pcb)
