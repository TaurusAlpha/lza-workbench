"""Resolve configured LZA pipeline identities."""

from __future__ import annotations

from dataclasses import dataclass

from lza_workbench.workspace.schema import WorkspaceConfig


@dataclass(frozen=True)
class ResolvedPipeline:
    """Configured pipeline identity for an LZA workflow."""

    pipeline_type: str
    name: str

    def arn(self, *, region: str, account_id: str) -> str:
        return f"arn:aws:codepipeline:{region}:{account_id}:{self.name}"


def resolve_pipeline(
    config: WorkspaceConfig,
    *,
    pipeline_type: str = "configuration",
    pipeline_name: str | None = None,
) -> ResolvedPipeline:
    """Resolve an explicit or configured LZA pipeline name."""
    if pipeline_type not in {"installer", "configuration"}:
        raise ValueError(f"Unsupported pipeline type: {pipeline_type}")

    prefix = config.lza.accelerator_prefix or "AWSAccelerator"
    if pipeline_name and pipeline_name.strip():
        name = pipeline_name.strip()
    elif pipeline_type == "installer":
        name = config.pipelines.installer.name or f"{prefix}-Installer"
    else:
        name = config.pipelines.configuration.name or f"{prefix}-Pipeline"
    return ResolvedPipeline(pipeline_type=pipeline_type, name=name)
