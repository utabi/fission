"""Fission CLI."""

import shutil
import subprocess
import sys

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
