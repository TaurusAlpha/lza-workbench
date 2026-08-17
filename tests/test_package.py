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
    """Keep domain, workflow, and AWS layers independent from Typer and Rich."""
    layer_directories = ("aws", "config", "installer", "workspace", "workflows")
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

    assert (
        not violations
    ), f"Domain/AWS/Workflow modules import presentation frameworks: {violations}"


def test_lower_layers_do_not_import_higher_layers() -> None:
    """Enforce strict dependency layering: cli -> workflows -> features/AWS."""
    feature_and_aws_dirs = ("aws", "config", "installer", "workspace")
    forbidden_for_features = {"lza_workbench.cli", "lza_workbench.workflows"}
    forbidden_for_workflows = {"lza_workbench.cli"}

    violations: list[tuple[str, int, str]] = []

    for directory in feature_and_aws_dirs:
        for path in (SOURCE_ROOT / directory).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for forbidden in forbidden_for_features:
                        if node.module == forbidden or node.module.startswith(f"{forbidden}."):
                            violations.append(
                                (str(path.relative_to(PROJECT_ROOT)), node.lineno, node.module)
                            )

    for path in (SOURCE_ROOT / "workflows").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in forbidden_for_workflows:
                    if node.module == forbidden or node.module.startswith(f"{forbidden}."):
                        violations.append(
                            (str(path.relative_to(PROJECT_ROOT)), node.lineno, node.module)
                        )

    assert not violations, f"Layering violations detected: {violations}"
