"""Compatibility wrapper for installer plan command (to be removed in Step 16)."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.commands.installer_plan import (
    installer_plan_command,
    render_installer_plan_report,
)
from lza_workbench.cli.presentation import print_info
from lza_workbench.installer.planning import (
    InstallerPlanResult,
    prepare_installer_plan_result,
)
from lza_workbench.workflows.installer_plan import plan_installer_workflow


def _render_plan_report(plan: InstallerPlanResult) -> None:
    render_installer_plan_report(plan)


def run_installer_plan(
    *,
    dry_run: bool = False,
    no_save: bool = False,
    target_dir: Path | None = None,
) -> None:
    """Resolve installer config from workspace and show planned deployment actions."""
    if not no_save and not dry_run:
        print_info("Installer configuration verified in lza-workspace.yaml", dim=True)

    plan_result = plan_installer_workflow(
        target_dir=target_dir,
        dry_run=dry_run,
        no_save=no_save,
    )
    _render_plan_report(plan_result)


__all__ = [
    "InstallerPlanResult",
    "_render_plan_report",
    "installer_plan_command",
    "prepare_installer_plan_result",
    "render_installer_plan_report",
    "run_installer_plan",
]
