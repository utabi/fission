"""Tests for layer integrity verification."""

from pathlib import Path

from click.testing import CliRunner

from fission.check import (
    CheckLevel,
    CheckReport,
    CheckResult,
    CheckStatus,
    check_board_dimensions,
    check_clearance,
    check_connector_edge_assignment,
    check_connector_position_consistency,
    check_mount_holes_in_bounds,
    check_mount_post_clearance,
    check_wall_thickness,
    run_checks,
    run_geometry_checks,
    run_mesh_checks,
)
from fission.cli import main
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

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PCB = FIXTURES / "sample.kicad_pcb"


def _make_valid_schema() -> FissionSchema:
    """全チェックをパスする正常系スキーマ."""
    return FissionSchema(
        project="test-check",
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


# ---------------------------------------------------------------------------
# Level A: スキーマ検証
# ---------------------------------------------------------------------------


class TestBoardDimensions:
    """ボード寸法チェック."""

    def test_normal_passes(self) -> None:
        schema = _make_valid_schema()
        results = check_board_dimensions(schema)
        assert len(results) == 2
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_too_small_fails(self) -> None:
        schema = _make_valid_schema()
        schema.pcb.outline.width = 0.5
        results = check_board_dimensions(schema)
        assert results[0].status == CheckStatus.FAIL
        assert "小さすぎます" in results[0].message

    def test_too_large_fails(self) -> None:
        schema = _make_valid_schema()
        schema.pcb.outline.length = 6000.0
        results = check_board_dimensions(schema)
        assert results[1].status == CheckStatus.FAIL
        assert "大きすぎます" in results[1].message


class TestWallThickness:
    """壁厚チェック."""

    def test_normal_passes(self) -> None:
        schema = _make_valid_schema()
        result = check_wall_thickness(schema)
        assert result.status == CheckStatus.PASS

    def test_too_thin_fails(self) -> None:
        schema = _make_valid_schema()
        schema.enclosure.wall_thickness = 1.0
        result = check_wall_thickness(schema)
        assert result.status == CheckStatus.FAIL

    def test_borderline_warns(self) -> None:
        schema = _make_valid_schema()
        schema.enclosure.wall_thickness = 1.8
        result = check_wall_thickness(schema)
        assert result.status == CheckStatus.WARN


class TestClearance:
    """クリアランスチェック."""

    def test_normal_passes(self) -> None:
        schema = _make_valid_schema()
        result = check_clearance(schema)
        assert result.status == CheckStatus.PASS

    def test_too_small_warns(self) -> None:
        schema = _make_valid_schema()
        schema.enclosure.clearance = 0.2
        result = check_clearance(schema)
        assert result.status == CheckStatus.WARN


class TestMountHolesInBounds:
    """マウントホール境界チェック."""

    def test_all_in_bounds(self) -> None:
        schema = _make_valid_schema()
        results = check_mount_holes_in_bounds(schema)
        assert len(results) == 4
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_out_of_bounds_fails(self) -> None:
        schema = _make_valid_schema()
        schema.pcb.mount_holes.append(MountHole(x=-5.0, y=30.0, diameter=3.2))
        results = check_mount_holes_in_bounds(schema)
        failed = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(failed) == 1
        assert "座標がボード外形外" in failed[0].message

    def test_no_holes_warns(self) -> None:
        schema = _make_valid_schema()
        schema.pcb.mount_holes = []
        results = check_mount_holes_in_bounds(schema)
        assert len(results) == 1
        assert results[0].status == CheckStatus.WARN


class TestMountPostClearance:
    """マウント柱と内壁の干渉チェック."""

    def test_normal_passes(self) -> None:
        schema = _make_valid_schema()
        results = check_mount_post_clearance(schema)
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_post_too_large_fails(self) -> None:
        """巨大なマウント穴径で柱が内壁に干渉."""
        schema = _make_valid_schema()
        # 端に近い穴を大きくする
        schema.pcb.mount_holes = [MountHole(x=1.0, y=1.0, diameter=10.0)]
        results = check_mount_post_clearance(schema)
        assert any(r.status == CheckStatus.FAIL for r in results)


class TestConnectorEdge:
    """コネクタedge割り当てチェック."""

    def test_edge_assigned_passes(self) -> None:
        schema = _make_valid_schema()
        results = check_connector_edge_assignment(schema)
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_no_edge_warns(self) -> None:
        schema = _make_valid_schema()
        schema.pcb.connectors[0].edge = None
        results = check_connector_edge_assignment(schema)
        assert results[0].status == CheckStatus.WARN
        assert "edge未設定" in results[0].message


class TestConnectorPositionConsistency:
    """コネクタ位置とedgeの整合チェック."""

    def test_consistent_passes(self) -> None:
        schema = _make_valid_schema()
        results = check_connector_position_consistency(schema)
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_inconsistent_warns(self) -> None:
        schema = _make_valid_schema()
        # J1はy=0 (TOP辺) だがedge=BOTTOMに変更
        schema.pcb.connectors[0].edge = EdgeSide.BOTTOM
        results = check_connector_position_consistency(schema)
        assert results[0].status == CheckStatus.WARN
        assert "最近傍辺" in results[0].message

    def test_no_edge_skipped(self) -> None:
        """edge=Noneのコネクタはスキップされる."""
        schema = _make_valid_schema()
        schema.pcb.connectors[0].edge = None
        results = check_connector_position_consistency(schema)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Level B: ジオメトリ検証
# ---------------------------------------------------------------------------


class TestGeometryChecks:
    """build123d によるジオメトリ検証."""

    def test_valid_schema_passes(self) -> None:
        schema = _make_valid_schema()
        results = run_geometry_checks(schema)
        passed = [r for r in results if r.status == CheckStatus.PASS]
        assert len(passed) >= 4  # 体積, 分割位置, top+bottom, BB×3

    def test_skipped_without_build123d(self) -> None:
        import fission.check as check_module

        original = check_module._BUILD123D_AVAILABLE
        try:
            check_module._BUILD123D_AVAILABLE = False
            results = run_geometry_checks(_make_valid_schema())
            assert len(results) == 1
            assert results[0].status == CheckStatus.SKIP
        finally:
            check_module._BUILD123D_AVAILABLE = original


# ---------------------------------------------------------------------------
# Level C: メッシュ検証
# ---------------------------------------------------------------------------


class TestMeshChecks:
    """trimesh によるメッシュ検証."""

    def test_valid_stl_passes(self, tmp_path: Path) -> None:
        from fission.case.generator import CaseGenerator

        schema = _make_valid_schema()
        gen = CaseGenerator(schema)
        stl_file = tmp_path / "test.stl"
        gen.export_stl(stl_file)

        results = run_mesh_checks(schema, stl_path=stl_file)
        passed = [r for r in results if r.status == CheckStatus.PASS]
        assert len(passed) >= 4  # watertight, winding, volume, dims×3

    def test_auto_generate_stl(self) -> None:
        """STLパス未指定時に自動生成して検証."""
        schema = _make_valid_schema()
        results = run_mesh_checks(schema, stl_path=None)
        passed = [r for r in results if r.status == CheckStatus.PASS]
        assert len(passed) >= 4

    def test_skipped_without_trimesh(self) -> None:
        import fission.check as check_module

        original = check_module._TRIMESH_AVAILABLE
        try:
            check_module._TRIMESH_AVAILABLE = False
            results = run_mesh_checks(_make_valid_schema())
            assert len(results) == 1
            assert results[0].status == CheckStatus.SKIP
        finally:
            check_module._TRIMESH_AVAILABLE = original


# ---------------------------------------------------------------------------
# run_checks 統合テスト
# ---------------------------------------------------------------------------


class TestRunChecks:
    """run_checks メインエントリポイント."""

    def test_schema_level_only(self) -> None:
        schema = _make_valid_schema()
        report = run_checks(schema, levels={CheckLevel.SCHEMA})
        assert report.pass_count > 0
        assert report.fail_count == 0

    def test_all_levels(self) -> None:
        schema = _make_valid_schema()
        report = run_checks(schema)
        assert report.pass_count > 10
        assert not report.has_failures


class TestCheckReport:
    """CheckReportのプロパティ."""

    def test_has_failures(self) -> None:
        report = CheckReport(results=[
            CheckResult(name="A", status=CheckStatus.PASS),
            CheckResult(name="B", status=CheckStatus.FAIL, message="bad"),
        ])
        assert report.has_failures
        assert report.pass_count == 1
        assert report.fail_count == 1

    def test_no_failures(self) -> None:
        report = CheckReport(results=[
            CheckResult(name="A", status=CheckStatus.PASS),
            CheckResult(name="B", status=CheckStatus.WARN, message="hmm"),
        ])
        assert not report.has_failures
        assert report.has_warnings
        assert report.warn_count == 1

    def test_skip_count(self) -> None:
        report = CheckReport(results=[
            CheckResult(name="A", status=CheckStatus.SKIP, message="no lib"),
        ])
        assert report.skip_count == 1


# ---------------------------------------------------------------------------
# CLI テスト
# ---------------------------------------------------------------------------


class TestCheckCli:
    """CLI: fission check."""

    def test_check_kicad_pcb(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(SAMPLE_PCB), "--level", "schema"])
        assert result.exit_code == 0
        assert "passed" in result.output

    def test_check_json_input(self, tmp_path: Path) -> None:
        schema = _make_valid_schema()
        json_file = tmp_path / "test.json"
        json_file.write_text(schema.model_dump_json(indent=2), encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(json_file), "--level", "schema"])
        assert result.exit_code == 0
        assert "passed" in result.output

    def test_check_invalid_extension(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "test.txt"
        bad_file.write_text("hello")
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(bad_file)])
        assert result.exit_code != 0

    def test_check_all_levels(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(SAMPLE_PCB)])
        assert "passed" in result.output

    def test_check_with_failures_exits_nonzero(self, tmp_path: Path) -> None:
        """FAILがあるとexit code 1."""
        # 極端に小さいボードでFAILを発生させる
        schema = _make_valid_schema()
        schema.pcb.outline.width = 0.5
        json_file = tmp_path / "bad.json"
        json_file.write_text(schema.model_dump_json(indent=2), encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(json_file), "--level", "schema"])
        assert result.exit_code != 0
        assert "FAIL" in result.output
