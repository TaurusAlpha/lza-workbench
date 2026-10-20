"""Data models for LZA solution uninstallation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lza_workbench.errors import LzaError

if TYPE_CHECKING:
    from lza_workbench.workspace.context import WorkspaceContext


@dataclass(frozen=True)
class UninstallTarget:
    """Customer and environment target metadata for LZA uninstallation."""

    customer_name: str
    customer_slug: str
    accelerator_prefix: str = "AWSAccelerator"
    management_account_id: str | None = None
    home_region: str = "us-east-1"
    management_profile: str | None = None
    workspace_dir: Path | None = None
    config_dir: Path | None = None
    record_dir: Path | None = None

    @property
    def state_dir(self) -> Path | None:
        if self.record_dir is not None:
            return self.record_dir
        return (self.workspace_dir / ".lza") if self.workspace_dir is not None else None

    def require_record_dir(self) -> Path:
        if self.state_dir is None:
            raise LzaError(
                "Uninstall execution requires a durable record directory (record_dir or workspace_dir)."
            )
        return self.state_dir

    @classmethod
    def from_workspace(cls, context: WorkspaceContext) -> UninstallTarget:
        return cls(
            customer_name=context.config.customer.name,
            customer_slug=context.config.customer.slug,
            accelerator_prefix=context.config.lza.accelerator_prefix or "AWSAccelerator",
            management_account_id=(
                context.config.aws.account_id
                or (context.state.observed_account_id if context.state else None)
            ),
            home_region=context.config.aws.region or "us-east-1",
            management_profile=context.config.aws.profile,
            workspace_dir=context.workspace_dir,
            config_dir=context.config_dir,
        )


@dataclass(frozen=True)
class UninstallOptions:
    """User-specified options for the uninstall workflow."""

    dry_run: bool = False
    force: bool = False
    regions: list[str] = field(default_factory=list)
    all_regions: bool = False
    accounts: list[str] = field(default_factory=list)
    assume_role_name: str = "AWSAccelerator-PipelineRole"
    profiles_file: str | None = None
    delete_s3_buckets: bool = False
    delete_retained_resources: bool = False
    skip_installer: bool = False
    skip_pipeline: bool = False
    max_workers: int = 10


@dataclass(frozen=True)
class UninstallAccountTarget:
    """Target AWS account for uninstallation inspection and cleanup."""

    account_id: str
    name: str
    is_management: bool = False
    profile: str | None = None
    role_name: str | None = None


@dataclass
class UninstallStack:
    """CloudFormation stack identified for deletion."""

    stack_name: str
    account_id: str
    account_name: str
    region: str
    creation_time: datetime | None = None
    termination_protection: bool = False
    is_pipeline_or_installer: bool = False
    retained_resources: list[UninstallRetainedResource] = field(default_factory=list)


@dataclass
class UninstallRetainedResource:
    """Physical resource with DeletionPolicy: Retain."""

    account_id: str
    region: str
    stack_name: str
    logical_id: str
    physical_id: str
    resource_type: str
    action_status: str = "RETAINED"
    actually_deleted: bool = False


@dataclass
class UninstallS3Bucket:
    """LZA-managed S3 bucket identified for cleanup."""

    bucket_name: str
    account_id: str
    region: str
    action_status: str = "RETAINED"
    actually_deleted: bool = False


@dataclass
class UninstallPlan:
    """Consolidated inventory and ordered execution plan for uninstall."""

    customer_name: str
    customer_slug: str
    accelerator_prefix: str
    accounts: list[UninstallAccountTarget]
    regions: list[str]
    stacks: list[UninstallStack]
    retained_resources: list[UninstallRetainedResource]
    s3_buckets: list[UninstallS3Bucket]

    @property
    def total_stacks(self) -> int:
        return len(self.stacks)

    @property
    def protected_stacks(self) -> int:
        return sum(1 for s in self.stacks if s.termination_protection)

    @property
    def total_retained_resources(self) -> int:
        return len(self.retained_resources)

    @property
    def total_s3_buckets(self) -> int:
        return len(self.s3_buckets)


@dataclass
class UninstallProgress:
    """Execution progress tracker and audit record."""

    customer_slug: str
    started_at: str
    completed_at: str | None = None
    status: str = "NOT_STARTED"  # NOT_STARTED, IN_PROGRESS, COMPLETED, FAILED, INTERRUPTED
    deleted_stacks: list[str] = field(default_factory=list)
    failed_stacks: list[dict[str, str]] = field(default_factory=list)
    deleted_retained: list[dict[str, str]] = field(default_factory=list)
    failed_retained: list[dict[str, str]] = field(default_factory=list)
    deleted_buckets: list[str] = field(default_factory=list)
    failed_buckets: list[dict[str, str]] = field(default_factory=list)
    retained_resources_remaining: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None
