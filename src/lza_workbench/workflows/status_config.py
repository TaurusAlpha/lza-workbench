"""Workflow for gathering configuration repository status data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context


@dataclass(frozen=True)
class ConfigurationStatusResult:
    """All data needed to render configuration-source status."""

    workspace_dir: Path
    customer_name: str
    lza_version: str
    config_dir: Path
    config_dir_exists: bool
    yaml_files: tuple[str, ...]
    repository_type: str
    repository_bucket: str | None
    repository_prefix: str
    repository_key: str
    repository_name: str | None
    repository_branch: str | None
    uploaded_at: object | None
    downloaded_at: object | None
    has_state: bool


def get_config_status_workflow(
    *,
    target_dir: Path | None = None,
) -> ConfigurationStatusResult:
    """Query workspace configuration metadata and return configuration status result."""
    ctx = load_workspace_context(target_dir, min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED)
    workspace_dir, config, state = ctx.workspace_dir, ctx.config, ctx.state

    config_dir = workspace_dir / config.configuration.local_path
    yaml_files = (
        tuple(
            sorted(
                file.name
                for file in config_dir.iterdir()
                if file.is_file() and file.suffix in (".yaml", ".yml")
            )
        )
        if config_dir.exists()
        else ()
    )
    repo = config.configuration.repository
    return ConfigurationStatusResult(
        workspace_dir=workspace_dir,
        customer_name=config.customer.name,
        lza_version=config.lza.version,
        config_dir=config_dir,
        config_dir_exists=config_dir.exists(),
        yaml_files=yaml_files,
        repository_type=repo.type,
        repository_bucket=repo.bucket,
        repository_prefix=repo.prefix,
        repository_key=repo.key,
        repository_name=repo.repository_name,
        repository_branch=repo.branch,
        uploaded_at=state.config_uploaded_at if state else None,
        downloaded_at=state.config_downloaded_at if state else None,
        has_state=state is not None,
    )
