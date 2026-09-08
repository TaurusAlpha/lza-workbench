"""CLI boundary tests for installer settings collection."""

from __future__ import annotations

from pathlib import Path

from lza_workbench.cli.commands import installer_init as command
from lza_workbench.workflows.installer_init import (
    InstallerForm,
    InstallerFormField,
    InstallerSettingsResult,
)
from lza_workbench.workspace.schema import AwsConfig, CustomerConfig, WorkspaceConfig


def _result() -> InstallerSettingsResult:
    return InstallerSettingsResult(
        workspace_dir=Path("/workspace"),
        config=WorkspaceConfig(
            customer=CustomerConfig(name="Acme", slug="acme"),
            aws=AwsConfig(profile="acme", region="us-east-1"),
        ),
        template_path=Path("/workspace/template.json"),
        resolved_parameters={},
        dry_run=False,
        no_save=False,
    )


def test_installer_init_cli_submits_explicit_values_without_prompting(
    monkeypatch,
) -> None:
    captured = []

    def apply(request):
        captured.append(request)
        return _result()

    monkeypatch.setattr(command, "apply_installer_settings", apply)

    command.installer_init_command(
        management_account_email="management@example.com",
        log_archive_account_email="log@example.com",
        audit_account_email="audit@example.com",
        accelerator_prefix="Acme",
        interactive=False,
    )

    assert captured[0].values == {
        "ManagementAccountEmail": "management@example.com",
        "LogArchiveAccountEmail": "log@example.com",
        "AuditAccountEmail": "audit@example.com",
        "AcceleratorPrefix": "Acme",
    }


def test_installer_init_cli_collects_form_fields(monkeypatch) -> None:
    field = InstallerFormField(
        name="CustomParameter",
        label="Custom parameter",
        default="default",
        required=False,
        allowed_values=(),
        allowed_pattern=None,
        description=None,
    )
    forms = [
        InstallerForm(Path("/workspace"), Path("/workspace/template.json"), (field,), {}),
        InstallerForm(Path("/workspace"), Path("/workspace/template.json"), (), {}),
    ]
    captured = []
    monkeypatch.setattr(command, "get_installer_parameters_schema", lambda **_kwargs: forms.pop(0))

    def apply(request):
        captured.append(request)
        return _result()

    monkeypatch.setattr(command, "apply_installer_settings", apply)
    monkeypatch.setattr(command, "value_or_prompt", lambda **_kwargs: "chosen")

    command.installer_init_command(interactive=True)

    assert captured[0].values == {"CustomParameter": "chosen"}
