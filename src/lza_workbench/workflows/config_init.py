"""Workflow for initializing local LZA configuration from a template."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lza_workbench.configuration.git import (
    configure_codecommit_credential_helper,
    create_initial_commit,
    init_git_repository,
    is_git_repository,
    is_git_root,
    is_inside_parent_git_repo,
)
from lza_workbench.configuration.rendering import (
    capture_init_values_snapshot,
    compute_config_directory_digest,
)
from lza_workbench.configuration.templates import (
    DEFAULT_TEMPLATE_SOURCE,
    ResolvedTemplateSource,
    render_and_copy_template,
    resolve_template_source,
    validate_template,
)
from lza_workbench.errors import LzaError
from lza_workbench.workspace.config import write_workspace_config
from lza_workbench.workspace.context import WorkspaceReadinessLevel, load_workspace_context
from lza_workbench.workspace.schema import WorkspaceConfig
from lza_workbench.workspace.state import write_workspace_state


@dataclass(frozen=True)
class ConfigInitResult:
    """Structured result of configuration initialization workflow."""

    workspace_dir: Path
    config_dir: Path
    template_source: ResolvedTemplateSource
    written_paths: list[Path]
    unresolved_placeholders: list[str]
    dry_run: bool
    config: WorkspaceConfig
    skipped: bool = False
    is_managed: bool = False
    initialized_at: datetime | None = None
    drifted_fields: tuple[str, ...] = ()
    git_initialized: bool = False
    git_committed: bool = False
    git_skipped: bool = False
    git_skip_reason: str | None = None


def init_config_workflow(
    *,
    target_dir: Path | None = None,
    template_name: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> ConfigInitResult:
    """Execute configuration initialization and return structured result."""
    context = load_workspace_context(
        target_dir=target_dir,
        min_readiness=WorkspaceReadinessLevel.CORE_CONFIGURED,
    )
    workspace_dir = context.workspace_dir
    config = context.config
    state = context.state

    # Resolve template
    template_to_resolve = (
        template_name
        or config.configuration.template.name
        or DEFAULT_TEMPLATE_SOURCE
    )
    resolved_template = resolve_template_source(template_to_resolve)
    validate_template(resolved_template.config_dir)

    target_config_dir = workspace_dir / config.configuration.local_path

    # Check if target exists
    if target_config_dir.exists():
        if not target_config_dir.is_dir():
            raise LzaError(
                f"Target configuration path exists and is not a directory: {target_config_dir}"
            )
        # Check if directory has existing contents
        has_contents = any(target_config_dir.iterdir())
        if has_contents and not force:
            if state and state.config_initialized_at:
                current_snapshot = capture_init_values_snapshot(config)
                saved_snapshot = state.config_init_values or {}
                drifted = tuple(
                    sorted(k for k, v in current_snapshot.items() if saved_snapshot.get(k) != v)
                )
                return ConfigInitResult(
                    workspace_dir=workspace_dir,
                    config_dir=target_config_dir,
                    template_source=resolved_template,
                    written_paths=[],
                    unresolved_placeholders=[],
                    dry_run=dry_run,
                    config=config,
                    skipped=True,
                    is_managed=True,
                    initialized_at=state.config_initialized_at,
                    drifted_fields=drifted,
                    git_skipped=True,
                    git_skip_reason="Configuration directory already exists",
                )
            return ConfigInitResult(
                workspace_dir=workspace_dir,
                config_dir=target_config_dir,
                template_source=resolved_template,
                written_paths=[],
                unresolved_placeholders=[],
                dry_run=dry_run,
                config=config,
                skipped=True,
                is_managed=False,
                git_skipped=True,
                git_skip_reason="Configuration directory already exists",
            )

    if not dry_run and force and target_config_dir.exists():
        # Scoped cleanup of target directory to prevent orphaned files, preserving .git
        for child in target_config_dir.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    written_paths, unresolved = render_and_copy_template(
        template_config_dir=resolved_template.config_dir,
        target_config_dir=target_config_dir,
        config=config,
        dry_run=dry_run,
    )

    git_initialized = False
    git_committed = False
    git_skipped = False
    git_skip_reason: str | None = None

    repo_type = config.configuration.repository.type
    if repo_type == "s3":
        if is_git_root(target_config_dir):
            git_skipped = True
            git_skip_reason = "Directory already has a Git repository"
        elif is_inside_parent_git_repo(target_config_dir):
            git_skipped = True
            git_skip_reason = "Directory is inside an existing parent Git repository"
        elif not dry_run:
            init_git_repository(target_config_dir)
            create_initial_commit(target_config_dir, "Initial LZA configuration")
            git_initialized = True
            git_committed = True
    else:
        git_skipped = True
        git_skip_reason = f"Remote configuration repository is '{repo_type}'"

    if not dry_run:
        validate_template(target_config_dir)

        # Update provenance in lza-workspace.yaml if template changed
        template_source_type = (
            "packaged"
            if resolved_template.source_type == "bundled"
            else resolved_template.source_type
        )
        current_template = config.configuration.template
        if (
            current_template.name != resolved_template.source
            or current_template.source != template_source_type
        ):
            current_template.name = resolved_template.source
            current_template.source = template_source_type  # type: ignore[assignment]
            write_workspace_config(workspace_dir, config)

        if (
            repo_type == "codecommit"
            and config.aws.profile
            and (is_git_repository(target_config_dir) or (target_config_dir / ".git").exists())
        ):
            configure_codecommit_credential_helper(target_config_dir, config.aws.profile)

        if state:
            state.config_initialized_at = datetime.now(UTC)
            state.config_template_name = resolved_template.source
            state.config_template_source = template_source_type
            state.config_init_values = capture_init_values_snapshot(config)
            state.config_init_digest = compute_config_directory_digest(target_config_dir)
            state.config_files_count = len(written_paths)
            write_workspace_state(workspace_dir, state)

    return ConfigInitResult(
        workspace_dir=workspace_dir,
        config_dir=target_config_dir,
        template_source=resolved_template,
        written_paths=written_paths,
        unresolved_placeholders=unresolved,
        dry_run=dry_run,
        config=config,
        skipped=False,
        git_initialized=git_initialized,
        git_committed=git_committed,
        git_skipped=git_skipped,
        git_skip_reason=git_skip_reason,
    )
