"""Tests for shared CLI presentation utilities."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC

import pytest

from lza_workbench.cli.input import validate_email, value_or_prompt
from lza_workbench.cli.output import (
    print_diff_summary,
    print_dry_run_header,
    print_error,
    print_info,
    print_kv,
    print_notice,
    print_section,
    print_success,
    print_warning,
)
from lza_workbench.errors import LzaError


@pytest.mark.parametrize(
    ("print_fn", "message"),
    [
        (print_success, "Operation completed"),
        (print_warning, "Resource exists"),
        (print_notice, "Downloading template..."),
        (print_error, "Fatal problem"),
        (print_info, "Normal message"),
    ],
)
def test_print_helpers(
    print_fn: Callable[[str], None],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_fn(message)
    captured = capsys.readouterr().out
    assert message in captured


def test_print_info_dimmed(capsys: pytest.CaptureFixture[str]) -> None:
    print_info("Dimmed message", dim=True)
    assert "Dimmed message" in capsys.readouterr().out


def test_print_dry_run_header(capsys: pytest.CaptureFixture[str]) -> None:
    print_dry_run_header("lza init")
    captured = capsys.readouterr().out
    assert "Dry run: lza init" in captured


def test_print_section(capsys: pytest.CaptureFixture[str]) -> None:
    print_section(1, "CloudFormation Planning")
    captured = capsys.readouterr().out
    assert "1. CloudFormation Planning" in captured


def test_print_kv(capsys: pytest.CaptureFixture[str]) -> None:
    print_kv("Workspace", "/tmp/workspace")
    captured = capsys.readouterr().out
    assert "Workspace: /tmp/workspace" in captured

    print_kv("Profile", "dev-root", bold_value=True)
    captured = capsys.readouterr().out
    assert "Profile: dev-root" in captured


def test_print_diff_summary_no_changes(capsys: pytest.CaptureFixture[str]) -> None:
    print_diff_summary([], [], [])
    captured = capsys.readouterr().out
    assert "No file changes detected" in captured


def test_print_diff_summary_with_changes(capsys: pytest.CaptureFixture[str]) -> None:
    print_diff_summary(["file1.yaml"], ["file2.yaml"], ["file3.yaml"])
    captured = capsys.readouterr().out
    assert "Changes: 1 added, 1 modified, 1 removed" in captured
    assert "+ file1.yaml" in captured
    assert "~ file2.yaml" in captured
    assert "- file3.yaml" in captured


def test_value_or_prompt_non_interactive() -> None:
    assert value_or_prompt("Name", "explicit", None, interactive=False) == "explicit"
    assert (
        value_or_prompt("Name", "  explicit_padded  ", None, interactive=False)
        == "explicit_padded"
    )
    assert value_or_prompt("Name", None, "default_val", interactive=False) == "default_val"
    with pytest.raises(LzaError, match="Name is required"):
        value_or_prompt("Name", None, None, interactive=False)
    with pytest.raises(LzaError, match="Name is required"):
        value_or_prompt("Name", "   ", None, interactive=False)


def test_value_or_prompt_email_validation() -> None:
    assert validate_email("  user@example.com  ") == "user@example.com"
    with pytest.raises(ValueError, match="Must be a valid email address"):
        validate_email("invalid-email")
    with pytest.raises(ValueError, match="Must be a valid email address"):
        validate_email("   ")


def test_format_timestamp() -> None:
    from datetime import datetime

    from lza_workbench.cli.output import format_timestamp

    assert format_timestamp(None) is None
    assert format_timestamp("") is None
    assert format_timestamp("None") is None

    # Datetime object (UTC)
    dt_utc = datetime(2026, 8, 30, 12, 34, 56, tzinfo=UTC)
    assert format_timestamp(dt_utc) == "2026-08-30 12:34:56 UTC"

    # Datetime object naive (assumed UTC)
    dt_naive = datetime(2026, 8, 30, 12, 34, 56)
    assert format_timestamp(dt_naive) == "2026-08-30 12:34:56 UTC"

    # ISO string with Z
    assert format_timestamp("2026-08-30T12:34:56Z") == "2026-08-30 12:34:56 UTC"

    # ISO string with fractional seconds
    assert format_timestamp("2026-08-30T12:34:56.789012+00:00") == "2026-08-30 12:34:56 UTC"

    # Already formatted UTC string
    assert format_timestamp("2026-08-30 12:34:56 UTC") == "2026-08-30 12:34:56 UTC"


def test_format_status() -> None:
    from lza_workbench.cli.output import format_status

    assert "Update Complete" in format_status("UPDATE_COMPLETE")
    assert "green" in format_status("UPDATE_COMPLETE")

    assert "Create Complete" in format_status("CREATE_COMPLETE")
    assert "green" in format_status("Succeeded")
    assert "yellow" in format_status("InProgress")
    assert "red" in format_status("Failed")
    assert "red" in format_status("ROLLBACK_FAILED")
    assert "dim" in format_status("Unknown")


def test_render_workspace_header(capsys: pytest.CaptureFixture[str]) -> None:
    from lza_workbench.cli.output import render_workspace_header

    render_workspace_header(
        "LZA Test Status",
        customer_name="Acme Corp",
        workspace_dir="/path/to/acme",
        lza_version="1.10.0",
        profile="acme-prod",
        region="eu-west-1",
        aws_identity={"account": "123456789012"},
    )
    captured = capsys.readouterr().out
    assert "LZA Test Status - Acme Corp" in captured
    assert "Workspace: /path/to/acme" in captured
    assert "Configured LZA Version: 1.10.0" in captured
    assert "AWS Profile: acme-prod" in captured
    assert "AWS Region: eu-west-1" in captured
    assert "AWS Account ID: 123456789012" in captured


def test_render_failure_section(capsys: pytest.CaptureFixture[str]) -> None:
    from dataclasses import dataclass

    from lza_workbench.cli.output import render_failure_section

    @dataclass
    class DummyAction:
        action_name: str
        stage_name: str | None = None
        failed_resource: str | None = None
        diagnostic_details: list[str] | None = None
        error_message: str | None = None
        summary: str | None = None
        external_execution_url: str | None = None
        raw_diagnostic_details: list[str] | None = None

    fa = DummyAction(
        action_name="SynthAction",
        stage_name="SynthStage",
        failed_resource="AWSAccelerator-PrepareStack",
        diagnostic_details=["ValidationError: Stack cannot be deleted"],
        external_execution_url="https://console.aws.amazon.com/codebuild/build-123",
    )

    render_failure_section(2, [fa])
    captured = capsys.readouterr().out
    assert "2. Failure" in captured
    assert "Stage: SynthStage" in captured
    assert "Action: SynthAction" in captured
    assert "Resource: AWSAccelerator-PrepareStack" in captured
    assert "Error: ValidationError: Stack cannot be deleted" in captured
    assert "Build Console: https://console.aws.amazon.com/codebuild/build-123" in captured

