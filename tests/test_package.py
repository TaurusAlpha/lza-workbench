"""Tests for package-level behavior and architectural import boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SOURCE_ROOT = PROJECT_ROOT / "src" / "lza_workbench"


def test_cli_main_returns_success() -> None:
    from lza_workbench.interfaces.cli import main

    assert main([]) == 0


def test_cli_version_option(capsys) -> None:
    from lza_workbench import __version__
    from lza_workbench.interfaces.cli import main

    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_domain_and_infrastructure_modules_do_not_import_cli_presentation_frameworks() -> None:
    """Keep domain, application, and infrastructure layers independent from Typer and Rich."""
    layer_directories = (
        "infrastructure/aws",
        "configuration",
        "installer",
        "workspace",
        "pipeline",
        "status",
    )
    forbidden_imports = {"rich", "typer"}
    violations: list[tuple[str, int, str]] = []

    for directory in layer_directories:
        for path in (SOURCE_ROOT / directory).rglob("*.py"):
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

    assert not violations, (
        f"Domain/Infrastructure modules import presentation frameworks: {violations}"
    )


def test_lower_layers_do_not_import_higher_layers() -> None:
    """Enforce strict dependency layering: interfaces -> feature applications -> domain -> infrastructure."""
    domain_and_infra_dirs = ("infrastructure", "configuration", "installer", "workspace", "pipeline")
    forbidden_for_domain = {"lza_workbench.interfaces"}

    violations: list[tuple[str, int, str]] = []

    for directory in domain_and_infra_dirs:
        for path in (SOURCE_ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for forbidden in forbidden_for_domain:
                        if node.module == forbidden or node.module.startswith(f"{forbidden}."):
                            violations.append(
                                (str(path.relative_to(PROJECT_ROOT)), node.lineno, node.module)
                            )

    assert not violations, f"Layering violations detected: {violations}"


def test_aws_adapters_do_not_import_workspace_or_features() -> None:
    """AWS adapters must remain thin boto3 wrappers without domain policy dependencies."""
    forbidden = {
        "lza_workbench.workspace",
        "lza_workbench.installer",
        "lza_workbench.config",
        "lza_workbench.configuration",
        "lza_workbench.pipeline",
        "lza_workbench.status",
        "lza_workbench.interfaces",
    }
    violations: list[tuple[str, int, str]] = []

    for path in (SOURCE_ROOT / "infrastructure" / "aws").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for f in forbidden:
                    if node.module == f or node.module.startswith(f"{f}."):
                        violations.append(
                            (str(path.relative_to(PROJECT_ROOT)), node.lineno, node.module)
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for f in forbidden:
                        if alias.name == f or alias.name.startswith(f"{f}."):
                            violations.append(
                                (str(path.relative_to(PROJECT_ROOT)), node.lineno, alias.name)
                            )

    assert not violations, f"AWS layer imports domain/workspace packages: {violations}"


def test_no_direct_boto3_session_or_client_outside_factory() -> None:
    """Verify no file in infrastructure/aws/ except session.py calls boto3.Session/client."""
    aws_dir = SOURCE_ROOT / "infrastructure" / "aws"
    forbidden_calls = []

    for path in aws_dir.glob("*.py"):
        if path.name == "session.py":
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "boto3" and node.func.attr in ("Session", "client"):
                        forbidden_calls.append((path.name, node.lineno, f"boto3.{node.func.attr}"))
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "session" and node.func.attr == "client":
                        forbidden_calls.append((path.name, node.lineno, "session.client"))

    assert not forbidden_calls, (
        f"Direct boto3 session/client calls outside session.py: {forbidden_calls}"
    )
