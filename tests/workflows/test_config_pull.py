"""S3 synchronization and declarative destination persistence regressions."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from lza_workbench.errors import LzaError
from lza_workbench.workflows.config_pull import pull_configuration_workflow
from lza_workbench.workflows.config_push import push_configuration_workflow
from lza_workbench.workspace.config import load_workspace_config, write_workspace_config
from lza_workbench.workspace.state import load_workspace_state, write_workspace_state


@pytest.mark.parametrize("operation", ["push", "pull"])
@pytest.mark.parametrize("explicit_bucket", [False, True])
@pytest.mark.parametrize("dry_run", [False, True])
def test_s3_destination_persistence(
    configured_workspace,
    monkeypatch,
    mock_aws_execution_context,
    sample_config_zip,
    operation,
    explicit_bucket,
    dry_run,
):
    config = load_workspace_config(configured_workspace)
    expected_bucket = config.configuration.repository.bucket
    if not explicit_bucket:
        config.configuration.repository.bucket = None
    # Exercise the existing imported/runtime account fallback in both workflows.
    config.aws.account_id = None
    write_workspace_config(configured_workspace, config)
    state = load_workspace_state(configured_workspace)
    state.management_account_id = "123456789012"
    write_workspace_state(configured_workspace, state)
    before = {
        p.relative_to(configured_workspace): p.read_bytes()
        for p in configured_workspace.rglob("*")
        if p.is_file()
    }
    resolver = Mock(return_value=mock_aws_execution_context)
    monkeypatch.setattr(
        f"lza_workbench.workflows.config_{operation}.resolve_aws_execution_context", resolver
    )
    client = mock_aws_execution_context.factory.get_client.return_value
    client.head_object.return_value = {}
    client.download_file.side_effect = lambda bucket, key, filename: sample_config_zip(
        Path(filename)
    )
    workflow = push_configuration_workflow if operation == "push" else pull_configuration_workflow
    result = workflow(target_dir=configured_workspace, dry_run=dry_run, force=True)
    assert result.s3_bucket == expected_bucket
    saved_bucket = load_workspace_config(configured_workspace).configuration.repository.bucket
    assert saved_bucket == (expected_bucket if explicit_bucket or not dry_run else None)
    if dry_run:
        resolver.assert_not_called()
        after = {
            p.relative_to(configured_workspace): p.read_bytes()
            for p in configured_workspace.rglob("*")
            if p.is_file()
        }
        assert before == after
    else:
        resolver.assert_called_once()
        if operation == "push":
            assert client.upload_file.call_args.args[1] == expected_bucket
        else:
            assert client.download_file.call_args.args[0] == expected_bucket


@pytest.mark.parametrize("extract", [False, True])
def test_imported_s3_pull_then_push(
    configured_workspace,
    monkeypatch,
    mock_aws_execution_context,
    sample_config_zip,
    extract,
):
    state = load_workspace_state(configured_workspace)
    state.imported = True
    write_workspace_state(configured_workspace, state)
    monkeypatch.setattr(
        "lza_workbench.workflows.config_pull.resolve_aws_execution_context",
        lambda **kwargs: mock_aws_execution_context,
    )
    client = mock_aws_execution_context.factory.get_client.return_value
    client.download_file.side_effect = lambda bucket, key, filename: sample_config_zip(
        Path(filename)
    )
    client.head_object.return_value = {}
    pull_configuration_workflow(target_dir=configured_workspace, force=True, extract=extract)
    state = load_workspace_state(configured_workspace)
    assert state.config_downloaded_at
    if extract:
        assert state.config_sync_digest
        push_configuration_workflow(
            target_dir=configured_workspace,
            aws_context=mock_aws_execution_context,
        )
        client.upload_file.assert_called_once()
    else:
        # Downloading an archive alone does not verify the local configuration.
        assert state.config_sync_digest is None
        with pytest.raises(LzaError, match="has not been verified"):
            push_configuration_workflow(
                target_dir=configured_workspace,
                aws_context=mock_aws_execution_context,
            )
        client.upload_file.assert_not_called()
