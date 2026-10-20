"""Installer operational state models, stack observations, and deployment records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from lza_workbench.workspace.schema import WorkspaceState


class InstallerTemplateState(BaseModel):
    """Local installer template artifact metadata and synchronization baseline."""

    model_config = ConfigDict(extra="forbid", strict=False)

    version: str | None = None
    digest: str | None = None
    downloaded_at: datetime | None = None


class InstallerStackObservation(BaseModel):
    """Last-known AWS CloudFormation observation for the customer installer stack."""

    model_config = ConfigDict(extra="forbid", strict=False)

    account_id: str | None = None
    stack_name: str | None = None
    stack_id: str | None = None
    stack_status: str | None = None
    deployed_version: str | None = None
    deployed_parameters: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime | None = None


class InstallerDeploymentRecord(BaseModel):
    """Recorded outcome of the most recent installer deployment operation."""

    model_config = ConfigDict(extra="forbid", strict=False)

    operation: str
    stack_name: str | None = None
    stack_id: str | None = None
    status: str
    template_version: str | None = None
    template_digest: str | None = None
    recorded_at: datetime
    error: str | None = None


class InstallerState(BaseModel):
    """Persisted installer template metadata, AWS stack observation, and deployment record."""

    model_config = ConfigDict(extra="forbid", strict=False)

    template: InstallerTemplateState = Field(default_factory=InstallerTemplateState)
    observation: InstallerStackObservation | None = None
    last_deployment: InstallerDeploymentRecord | None = None


def record_installer_template(
    state: WorkspaceState,
    *,
    version: str | None = None,
    digest: str | None = None,
    downloaded_at: datetime | None = None,
) -> None:
    """Record local installer template cache metadata."""
    now = datetime.now(UTC)
    if version is not None:
        state.installer.template.version = version
    if digest is not None:
        state.installer.template.digest = digest
    if downloaded_at is not None:
        state.installer.template.downloaded_at = downloaded_at
    state.touch(now)


def record_installer_observation(
    state: WorkspaceState,
    *,
    account_id: str | None = None,
    stack_name: str | None = None,
    stack_id: str | None = None,
    stack_status: str | None = None,
    deployed_version: str | None = None,
    deployed_parameters: dict[str, str] | None = None,
    observed_at: datetime | None = None,
) -> InstallerStackObservation:
    """Update the last-known AWS CloudFormation installer stack observation."""
    now = observed_at or datetime.now(UTC)
    existing = state.installer.observation
    same_stack = (
        existing is not None
        and (stack_id is None or existing.stack_id is None or existing.stack_id == stack_id)
    )
    resolved_parameters: dict[str, str]
    if deployed_parameters is not None:
        resolved_parameters = dict(deployed_parameters)
    elif existing is not None and same_stack:
        resolved_parameters = dict(existing.deployed_parameters)
    else:
        resolved_parameters = {}

    observation = InstallerStackObservation(
        account_id=account_id if account_id is not None else (existing.account_id if existing else None),
        stack_name=stack_name if stack_name is not None else (existing.stack_name if existing else None),
        stack_id=stack_id if stack_id is not None else (existing.stack_id if existing else None),
        stack_status=(
            stack_status
            if stack_status is not None
            else (existing.stack_status if existing and same_stack else None)
        ),
        deployed_version=(
            deployed_version
            if deployed_version is not None
            else (existing.deployed_version if existing and same_stack else None)
        ),
        deployed_parameters=resolved_parameters,
        observed_at=now,
    )
    state.installer.observation = observation
    state.touch(now)
    return observation


def record_installer_deployment(
    state: WorkspaceState,
    *,
    aws_identity: dict[str, str] | None = None,
    operation: str = "DEPLOY",
    stack_name: str | None = None,
    stack_id: str | None,
    stack_status: str,
    template_version: str,
    template_digest: str,
    deployed_parameters: dict[str, str] | None = None,
    downloaded_at: datetime | None = None,
) -> None:
    """Record a completed CloudFormation deployment and update the stack observation."""
    now = datetime.now(UTC)
    account_id = aws_identity.get("account") if aws_identity else None
    record_installer_template(
        state,
        version=template_version,
        digest=template_digest,
        downloaded_at=downloaded_at,
    )
    record_installer_observation(
        state,
        account_id=account_id,
        stack_name=stack_name,
        stack_id=stack_id,
        stack_status=stack_status,
        deployed_version=template_version,
        deployed_parameters=deployed_parameters,
        observed_at=now,
    )
    state.installer.last_deployment = InstallerDeploymentRecord(
        operation=operation,
        stack_name=stack_name,
        stack_id=stack_id,
        status=stack_status,
        template_version=template_version,
        template_digest=template_digest,
        recorded_at=now,
        error=None,
    )
    state.touch(now)


def record_installer_deployment_failure(
    state: WorkspaceState,
    *,
    aws_identity: dict[str, str] | None = None,
    operation: str = "DEPLOY",
    stack_name: str | None = None,
    stack_id: str | None,
    stack_status: str,
    template_version: str | None = None,
    template_digest: str | None = None,
    error: str | None = None,
) -> None:
    """Record a failed deployment operation without overwriting deployed version/template baselines."""
    now = datetime.now(UTC)
    account_id = aws_identity.get("account") if aws_identity else None
    state.installer.last_deployment = InstallerDeploymentRecord(
        operation=operation,
        stack_name=stack_name,
        stack_id=stack_id,
        status=stack_status,
        template_version=template_version,
        template_digest=template_digest,
        recorded_at=now,
        error=error,
    )
    if stack_id is not None or stack_status != "UNKNOWN":
        record_installer_observation(
            state,
            account_id=account_id,
            stack_name=stack_name,
            stack_id=stack_id,
            stack_status=stack_status,
            observed_at=now,
        )
    else:
        state.touch(now)


__all__ = [
    "InstallerDeploymentRecord",
    "InstallerStackObservation",
    "InstallerState",
    "InstallerTemplateState",
    "record_installer_deployment",
    "record_installer_deployment_failure",
    "record_installer_observation",
    "record_installer_template",
]
