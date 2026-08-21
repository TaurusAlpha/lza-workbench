"""Workflow for gathering configuration repository status data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lza_workbench.configuration.rendering import capture_init_values_snapshot
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
    initialized_at: datetime | None
    template_name: str | None
    template_source: str | None
    drifted_fields: tuple[str, ...]
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

    initialized_at = state.config_initialized_at if state else None
    template_name = state.config_template_name if state else None
    template_source = state.config_template_source if state else None
    drifted_fields: tuple[str, ...] = ()
    if state and state.config_initialized_at and state.config_init_values:
        current_snapshot = capture_init_values_snapshot(config)
        saved_snapshot = state.config_init_values
        drifted_fields = tuple(
            sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
        )

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
        initialized_at=initialized_at,
        template_name=template_name,
        template_source=template_source,
        drifted_fields=drifted_fields,
        uploaded_at=state.config_uploaded_at if state else None,
        downloaded_at=state.config_downloaded_at if state else None,
        has_state=state is not None,
    )
