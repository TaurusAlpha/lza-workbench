"""Tests for package-level behavior and architectural import boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SOURCE_ROOT = PROJECT_ROOT / "src" / "lza_workbench"


def test_smoke() -> None:
    assert True


def test_cli_main_returns_success() -> None:
    from lza_workbench.cli import main

    assert main([]) == 0


def test_cli_version_option(capsys) -> None:
    from lza_workbench import __version__
    from lza_workbench.cli import main

    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_domain_and_aws_modules_do_not_import_cli_presentation_frameworks() -> None:
    """Keep domain and AWS layers independent from Typer and Rich."""
    layer_directories = ("aws", "core", "installer", "workspace")
    forbidden_imports = {"rich", "typer"}
    violations: list[tuple[str, int, str]] = []

    for directory in layer_directories:
        for path in (SOURCE_ROOT / directory).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            violations.append(
                                (str(path.relative_to(PROJECT_ROOT)), node.lineno, alias.name)
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden_imports:
                        violations.append(
                            (str(path.relative_to(PROJECT_ROOT)), node.lineno, node.module)
                        )

    assert not violations, f"Domain/AWS modules import presentation frameworks: {violations}"


def test_command_modules_do_not_import_other_command_modules() -> None:
    """Keep command workflows independent rather than sharing private command helpers."""
    violations: list[tuple[str, int, str]] = []
    commands_dir = SOURCE_ROOT / "commands"

    for path in commands_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("lza_workbench.commands."):
                    violations.append(
                        (str(path.relative_to(PROJECT_ROOT)), node.lineno, node.module)
                    )

    assert not violations, f"Command modules import other command modules: {violations}"
