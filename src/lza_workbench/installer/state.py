"""Operational state updates for installer deployments."""

from __future__ import annotations

from datetime import UTC, datetime

from lza_workbench.workspace.schema import WorkspaceState


def record_installer_deployment(
    state: WorkspaceState,
    *,
    aws_identity: dict[str, str],
    stack_id: str,
    stack_status: str,
    template_version: str,
    template_digest: str,
    downloaded_at: datetime | None = None,
) -> None:
    """Update operational state after a successful CloudFormation deployment."""
    now = datetime.now(UTC)
    state.management_account_id = aws_identity.get("account")
    state.caller_arn = aws_identity.get("arn")
    state.installer_stack_id = stack_id
    state.installer_stack_status = stack_status
    state.installer_template_version = template_version
    state.installer_template_digest = template_digest
    if downloaded_at:
        state.installer_downloaded_at = downloaded_at
    state.installer_stack_updated_at = now
    state.updated_at = now


def record_installer_deployment_failure(
    state: WorkspaceState,
    *,
    aws_identity: dict[str, str],
    stack_id: str | None,
    stack_status: str,
) -> None:
    """Record an observed terminal installer stack failure without claiming success."""
    now = datetime.now(UTC)
    state.management_account_id = aws_identity.get("account")
    state.caller_arn = aws_identity.get("arn")
    if stack_id:
        state.installer_stack_id = stack_id
    state.installer_stack_status = stack_status
    state.installer_stack_updated_at = now
    state.updated_at = now


__all__ = ["record_installer_deployment", "record_installer_deployment_failure"]
