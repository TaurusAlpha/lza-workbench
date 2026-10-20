"""Resolve configured LZA pipeline identities."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.workspace.schema import CustomerEnvironmentTarget, WorkspaceConfig


@dataclass(frozen=True)
class ResolvedPipeline:
    """Configured pipeline identity for an LZA workflow."""

    pipeline_type: str
    name: str

    def arn(self, *, region: str, account_id: str) -> str:
        return f"arn:aws:codepipeline:{region}:{account_id}:{self.name}"


def resolve_pipeline(
    target: CustomerEnvironmentTarget | WorkspaceConfig | None = None,
    *,
    pipeline_type: str = "configuration",
    pipeline_name: str | None = None,
    accelerator_prefix: str = "AWSAccelerator",
) -> ResolvedPipeline:
    """Resolve an explicit, configured, or prefix-derived LZA pipeline name."""
    if pipeline_type not in {"installer", "configuration"}:
        raise ValueError(f"Unsupported pipeline type: {pipeline_type}")

    env_target = (
        target.environment_target if isinstance(target, WorkspaceConfig) else target
    )
    prefix = (
        (env_target.lza.accelerator_prefix if env_target is not None else accelerator_prefix)
        or "AWSAccelerator"
    )
    if pipeline_name and pipeline_name.strip():
        name = pipeline_name.strip()
    elif pipeline_type == "installer":
        configured = env_target.installer_pipeline_name if env_target is not None else None
        name = configured or f"{prefix}-Installer"
    else:
        configured = env_target.configuration_pipeline_name if env_target is not None else None
        name = configured or f"{prefix}-Pipeline"
    return ResolvedPipeline(pipeline_type=pipeline_type, name=name)
