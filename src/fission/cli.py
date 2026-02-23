"""Fission CLI."""

import shutil
import subprocess
import sys
from pathlib import Path

import click

from fission import __version__


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Fission: AI-native hardware design environment."""


@main.command()
def doctor() -> None:
    """Check that all dependencies are installed and working."""
    checks: list[tuple[str, str, bool]] = []

    # Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(("Python", py_version, sys.version_info >= (3, 10)))

    # build123d
    try:
        import build123d

        ver = getattr(build123d, "__version__", "unknown")
        checks.append(("build123d", ver, True))
    except ImportError:
        checks.append(("build123d", "not installed", False))

    # skidl
    try:
        import skidl

        ver = getattr(skidl, "__version__", "unknown")
        checks.append(("skidl", ver, True))
    except ImportError:
        checks.append(("skidl", "not installed", False))

    # trimesh
    try:
        import trimesh

        ver = getattr(trimesh, "__version__", "unknown")
        checks.append(("trimesh", ver, True))
    except ImportError:
        checks.append(("trimesh", "not installed", False))

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
            ver = result.stdout.strip()
            checks.append(("kicad-cli", ver, True))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            checks.append(("kicad-cli", "error", False))
    else:
        checks.append(("kicad-cli", "not found", False))

    # FreeCAD (optional)
    freecad = shutil.which("freecad") or shutil.which("FreeCAD")
    if freecad:
        checks.append(("FreeCAD", "found (optional)", True))
    else:
        checks.append(("FreeCAD", "not found (optional)", True))

    # Print results
    all_ok = True
    for name, ver, ok in checks:
        symbol = click.style("✓", fg="green") if ok else click.style("✗", fg="red")
        if not ok and "optional" not in ver:
            all_ok = False
        click.echo(f"  {symbol} {name} {ver}")

    click.echo()
    if all_ok:
        click.echo(click.style("All checks passed.", fg="green"))
    else:
        click.echo(click.style("Some checks failed. See INSTALL.md for setup instructions.", fg="red"))
        raise SystemExit(1)


@main.command()
@click.argument("pcb_file", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="出力先JSONファイル (省略時はstdout)")
@click.option("--pretty/--compact", default=True, help="JSON出力のインデント")
def extract(pcb_file: str, output: str | None, pretty: bool) -> None:
    """KiCad PCBファイルから基板情報を抽出してFissionスキーマJSONを出力する.

    PCB_FILE: .kicad_pcb ファイルのパス
    """
    from fission.kicad.parser import parse_kicad_pcb

    try:
        schema = parse_kicad_pcb(pcb_file)
    except (FileNotFoundError, ValueError) as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1)

    indent = 2 if pretty else None
    json_str = schema.model_dump_json(indent=indent)

    if output:
        Path(output).write_text(json_str + "\n", encoding="utf-8")
        click.echo(f"Written to {output}")
    else:
        click.echo(json_str)


@main.command("generate-case")
@click.argument("schema_file", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default="enclosure.step", help="出力ファイル (.step or .stl)")
@click.option("--split/--no-split", default=False, help="top/bottom分割出力")
def generate_case(schema_file: str, output: str, split: bool) -> None:
    """FissionスキーマJSONからケースを生成する.

    SCHEMA_FILE: fission extract で出力したJSONファイル
    """
    from fission.case.generator import CaseGenerator
    from fission.schema import FissionSchema

    try:
        json_text = Path(schema_file).read_text(encoding="utf-8")
        schema = FissionSchema.model_validate_json(json_text)
    except Exception as e:
        click.echo(click.style(f"Error: スキーマの読み込みに失敗: {e}", fg="red"), err=True)
        raise SystemExit(1)

    gen = CaseGenerator(schema)
    out_path = Path(output)
    is_stl = out_path.suffix.lower() == ".stl"

    try:
        if split and is_stl:
            stem = out_path.with_suffix("")
            top_path = Path(f"{stem}_top.stl")
            bottom_path = Path(f"{stem}_bottom.stl")
            gen.export_split_stl(top_path, bottom_path)
            click.echo(f"Written to {top_path} and {bottom_path}")
        elif is_stl:
            gen.export_stl(out_path)
            click.echo(f"Written to {out_path}")
        else:
            gen.export_step(out_path)
            click.echo(f"Written to {out_path}")
    except Exception as e:
        click.echo(click.style(f"Error: ケース生成に失敗: {e}", fg="red"), err=True)
        raise SystemExit(1)


@main.command("export")
@click.argument("pcb_file", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default="output", help="出力ディレクトリ")
@click.option("--no-case", is_flag=True, help="ケース生成をスキップ")
@click.option("--no-gerbers", is_flag=True, help="Gerber/Drill/PnP生成をスキップ")
def export(pcb_file: str, output: str, no_case: bool, no_gerbers: bool) -> None:
    """PCBファイルから製造ファイルを一括生成する.

    PCB_FILE: .kicad_pcb ファイルのパス
    """
    from fission.export import run_full_export

    pcb_path = Path(pcb_file)
    output_dir = Path(output)

    click.echo(f"Exporting to {output_dir}/")
    click.echo()

    result = run_full_export(
        pcb_path,
        output_dir,
        skip_gerbers=no_gerbers,
        skip_case=no_case,
    )

    for step in result.steps:
        if step.success:
            symbol = click.style("✓", fg="green")
            detail = ", ".join(step.files) if step.files else "done"
            click.echo(f"  {symbol} {step.name}: {detail}")
        else:
            symbol = click.style("✗", fg="red")
            click.echo(f"  {symbol} {step.name}: {step.message}")

    click.echo()
    if result.all_ok:
        click.echo(click.style("Export complete.", fg="green"))
    else:
        click.echo(click.style("Some steps failed.", fg="yellow"))
        raise SystemExit(1)


@main.command("check")
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--level",
    type=click.Choice(["schema", "geometry", "mesh", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="実行するチェックレベル",
)
@click.option(
    "--stl",
    "stl_path",
    type=click.Path(exists=True),
    default=None,
    help="メッシュ検証に使用する既存STLファイル",
)
def check_cmd(input_file: str, level: str, stl_path: str | None) -> None:
    """PCBスキーマのレイヤー整合性を検証する.

    INPUT_FILE: .kicad_pcb ファイルまたは fission スキーマ JSON
    """
    from fission.check import CheckLevel, CheckStatus, run_checks
    from fission.schema import FissionSchema

    path = Path(input_file)

    if path.suffix == ".kicad_pcb":
        from fission.kicad.parser import parse_kicad_pcb

        try:
            schema = parse_kicad_pcb(path)
        except (FileNotFoundError, ValueError) as e:
            click.echo(click.style(f"Error: {e}", fg="red"), err=True)
            raise SystemExit(1)
    elif path.suffix == ".json":
        try:
            schema = FissionSchema.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as e:
            click.echo(
                click.style(f"Error: スキーマ読み込み失敗: {e}", fg="red"), err=True
            )
            raise SystemExit(1)
    else:
        click.echo(
            click.style(
                "Error: .kicad_pcb または .json ファイルを指定してください", fg="red"
            ),
            err=True,
        )
        raise SystemExit(1)

    if level == "all":
        levels = {CheckLevel.SCHEMA, CheckLevel.GEOMETRY, CheckLevel.MESH}
    else:
        levels = {CheckLevel(level)}

    stl = Path(stl_path) if stl_path else None

    click.echo(f"Checking {path.name}...")
    click.echo()

    report = run_checks(schema, levels=levels, stl_path=stl)

    for result in report.results:
        if result.status == CheckStatus.PASS:
            symbol = click.style("✓", fg="green")
            line = f"  {symbol} {result.name}"
            if result.message:
                line += f": {result.message}"
        elif result.status == CheckStatus.WARN:
            symbol = click.style("△", fg="yellow")
            line = f"  {symbol} {result.name}: {result.message}"
        elif result.status == CheckStatus.FAIL:
            symbol = click.style("✗", fg="red")
            line = f"  {symbol} {result.name}: {result.message}"
        else:  # SKIP
            symbol = click.style("-", fg="cyan")
            line = f"  {symbol} {result.name}: {result.message}"
        click.echo(line)

    click.echo()
    parts = [f"{report.pass_count} passed", f"{report.fail_count} failed"]
    if report.warn_count:
        parts.append(f"{report.warn_count} warnings")
    if report.skip_count:
        parts.append(f"{report.skip_count} skipped")
    summary = ", ".join(parts)

    if report.has_failures:
        click.echo(click.style(f"FAIL — {summary}", fg="red"))
        raise SystemExit(1)
    elif report.has_warnings:
        click.echo(click.style(f"PASS (with warnings) — {summary}", fg="yellow"))
    else:
        click.echo(click.style(f"All checks passed — {summary}", fg="green"))
