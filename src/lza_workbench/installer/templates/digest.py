"""Installer CloudFormation template digest and change detection."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from lza_workbench.errors import LzaError
from lza_workbench.infrastructure.aws.cloudformation import CfnDeploymentPlanResult


def get_installer_template_digest(template_path: Path) -> str:
    """Return a stable digest for a resolved installer template."""
    try:
        return sha256(template_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise LzaError(f"Unable to read installer template {template_path}: {exc}") from exc


def include_template_digest_change(
    plan: CfnDeploymentPlanResult,
    *,
    template_digest: str,
    deployed_template_digest: str | None,
) -> CfnDeploymentPlanResult:
    """Mark a parameter-stable stack for update when its template changed."""
    if plan.operation != "NO_CHANGE" or deployed_template_digest == template_digest:
        return plan
    return replace(plan, operation="UPDATE")


__all__ = [
    "get_installer_template_digest",
    "include_template_digest_change",
]
