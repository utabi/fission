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
